# CLAUDE.md — Sectra

Repo-specific facts. The full design is in the approved plan; this file records
what is true _here_ and is expensive to rediscover.

## What this is

Local, single-user web app: download long-form video → Silero VAD → Whisper
transcription → LLM picks highlight clips → edit in the browser → export
captioned MP4. Everything runs in `docker compose`.

| Service    | Entrypoint                          | Port (host) |
| ---------- | ----------------------------------- | ----------- |
| `api`      | `src.api_main:create_app` (factory) | 8000        |
| `worker`   | `python -m src.worker_main`         | —           |
| `web`      | Vite dev server (`frontend/`)       | 5173        |
| `postgres` | —                                   | 5433        |
| `redis`    | —                                   | 6380        |

Host ports 5433/6380 avoid clashing with other projects' Postgres/Redis on the
defaults. `migrate` runs `alembic upgrade head` once before `api`/`worker` start.

## Architecture

Hexagonal, modelled on `~/Documents/veel/Reva`. **Dependency rule: adapters →
application → ports → domain.** The domain imports nothing outward.

```
backend/src/
├── api_main.py / worker_main.py   # entrypoints
├── domain/        # models, enums, services (pure logic), exceptions
├── ports/         # Protocols: input/ (use cases), output/ (repos, queue, progress, providers)
├── application/   # services implementing input ports, dto/, prompts/
├── adapters/
│   ├── input/     # rest/ (FastAPI routers, SSE), worker/ (Redis stream consumer)
│   └── output/    # persistence/, queue/, events/, (later: llm/, stt/, vad/, media/, …)
├── config/        # settings.py, container.py (API + shared), worker_container.py
└── utils/
```

ruff `TID251` bans importing `src.adapters` outside composition roots
(`config/container.py`, `config/worker_container.py`, the two entrypoints,
`alembic/`). Adapters may import each other. **Add to `per-file-ignores` rather
than working around the rule.**

## Jobs

- Every pipeline stage is a `Job` row in Postgres plus a message `{job_id}` on a
  Redis stream (`JobType.stream`). Consumer group `workers`.
- `PipelineDispatcher.run_job` never raises for a failure inside a job — it
  records `failed` + `error` — so the consumer always acks after it returns.
- Crash recovery: the worker has a **stable consumer name** (`WORKER_NAME`). On
  start it replays its own un-acked messages (`XREADGROUP … 0`) before reading new
  ones. `attempts` counts deliveries; past `JOB_MAX_ATTEMPTS` the job is failed.
  (Single worker, so no `XAUTOCLAIM`; add it if a second worker is ever run.)
- **Redis reads must not time out client-side**: the shared client has
  `socket_timeout=None` (redis-py 8 defaults to 5 s, and a briefly busy loop then killed
  the whole worker mid-XREADGROUP). A consumer catches Redis timeouts/connection errors
  and retries with backoff (1→30 s) instead of dying; `worker_main` still exits if any
  consumer task ends, and compose restarts `worker`/`api` (`restart: unless-stopped`).
- Keep CPU work off the event loop in the worker: ANALYZE parses the transcript, selects
  clips and builds 50 EDLs (+ auto zooms) in `asyncio.to_thread`.
- Shutdown: SIGTERM drains in-flight jobs for up to 30s, then cancels them
  (they stay pending → replayed). `stop_grace_period: 40s` in compose.
- Deleting a video cascades to its jobs; a running job notices its row is gone (the
  dispatcher polls every 3 s), cancels its handler (ffmpeg/Rhubarb are killed, Kokoro stops
  between sentences), acks, and deletes whatever it re-created under `data/videos/<id>/`.
  Before this, a deleted story kept narrating and blocked the next one on `jobs:analysis`.
- Progress: dispatcher saves + publishes `JobEvent` on Redis pub/sub
  `job-events`; `GET /api/events` relays it as SSE (`event: job`).

## Pipeline (so far)

`INGEST` (yt-dlp, URL only) → `NORMALIZE` → `PREPARE` → `VAD` → `TRANSCRIBE` →
`ANALYZE`; `JobType.next_stage` chains
them, and the dispatcher queues the next stage / marks the video `ready` or
`failed`. Uploads skip `INGEST` (the API streams the raw request body — no
multipart — to `raw.<ext>`). Retrying a failed job reuses the same job row.

Files live in `data/videos/<video_id>/` (`VideoFile` enum): `raw.*` exists only
until normalization; `source.mp4` (short side ≤ 1080, H.264/AAC/yuv420p — stream
copied when already compliant; **the editor plays it directly** — there is no proxy
any more: encoding one took ~1 h on a 6 h video), `audio.wav`
(16 kHz mono), `peaks.json` (20/s, 0..1), `thumbnail.jpg`, `speech.json` (VAD
segments), `transcript.json` (segments → words, seconds on the source timeline).
Sizing rules are pure functions in `domain/services/media_rules.py`.

Speech → text:
- `SileroOnnxAdapter` only yields per-frame probabilities (32 ms frames, v5+
  interface: 64-sample context prepended, state `[2,1,128]`); turning them into
  segments is `domain/services/speech_detection.py`. Model pinned to Silero
  v6.2.3 (checksummed in `Dockerfile.worker`; `make models` for the host).
- `vad_chunking.build_chunks` packs padded segments into ≤ 30 s, non-overlapping
  chunks that break in pauses; silences > 2 s are skipped. Chunks are
  transcribed concurrently (TaskGroup) under the STT semaphore.
- STT adapters return timestamps relative to the chunk; `transcript_merging`
  shifts them onto the source timeline and moves each chunk's first word to the
  VAD onset (Whisper always stamps the first word from 0).
- **Default STT is the native GPU sidecar** `whisper-server/` (mlx-whisper, Metal;
  `make whisper`, 127.0.0.1:9000). Docker on macOS can't reach the GPU, so it runs on
  the host; the worker calls it through `openai_compat` at
  `host.docker.internal:9000/v1`. It implements only what `OpenAICompatSTTAdapter`
  sends (multipart file/model/language) and answers verbose_json with words flattened
  out of mlx's `segments[].words`; one GPU job at a time (asyncio lock). Own uv
  project + tests (`cd whisper-server && uv run pytest`). faster-whisper in the worker
  remains the CPU fallback (`STT_PROVIDER=faster_whisper`).
- Timings on a 5.5 h video, old → new: download 27 min (now yt-dlp
  `concurrent_fragment_downloads=8`), proxy 64 min (removed), CPU Whisper 68 min (GPU).
- STT provider is env-only (`STT_PROVIDER`, `STT_MODEL`, `STT_BASE_URL`, …);
  `Settings` validates it at startup. faster-whisper loads lazily on first use
  and caches weights in the `hf-cache` volume.
- Paths that differ between host and container (`DATABASE_URL`, `VAD_MODEL_PATH`,
  …) are set in compose `environment:`, which overrides `.env`. Don't put them
  back in `.env.example`.

- yt-dlp's `format_sort` `res:1080` uses the **shorter side**, so portrait videos
  are capped correctly. YouTube needs a JS runtime: the worker image ships Deno.
- Dependency groups: the API image installs only main deps; the worker adds
  `--group worker` (yt-dlp, numpy) and apt `ffmpeg`. Locally `uv sync` installs
  every group (`default-groups`). Never import worker-only libs outside
  adapters that only `worker_container.py` builds.
- ffmpeg runs as an async subprocess under the shared ffmpeg semaphore; it's
  killed if the job task is cancelled. Progress comes from `-progress pipe:1`.

Clips (ANALYZE):
- `transcript_windowing` splits the transcript into overlapping windows of whole
  segments. `.env` uses `LLM_WINDOW_SECONDS=600`, which needs an 8k context; the
  OpenAI-compatible endpoint can't set `num_ctx` and Ollama defaults to 4k (silently
  truncating), so `.env` points at a derived model `qwen2.5:7b-8k` (Modelfile
  `PARAMETER num_ctx 8192`; check with `ollama ps` → CONTEXT). Windows are sent
  concurrently under the LLM semaphore.
- The LLM answers with **segment ids**, never seconds (`application/prompts/
  highlight_prompt.py`). `clip_candidates.select_clips` resolves ids to
  first-word/last-word times, grows/shrinks on segment boundaries to fit
  `CLIP_MIN/MAX_SECONDS`, drops IoU > 0.5 duplicates (higher score wins), keeps
  `CLIP_MAX_COUNT`.
- Scoring (`domain/services/virality.py`): the LLM rates hook/emotion/payoff/
  standalone/shareability 0-10 and the score is **computed** (weights in
  `RUBRIC_WEIGHTS`) — asked for one 0-100 number, models put everything at 85-95.
  The loudest 20% of segments (mean `peaks.json` level) are marked `‼` in the
  prompt. The top `2 × CLIP_MAX_COUNT` (≤ 20) candidates then get one head-to-head
  ranking request; final score = ½ rubric + ½ rank; malformed ranking → rubric order.
- `POST /api/videos/{id}/analyze` ("Find clips again") re-runs ANALYZE and
  **replaces** the clips, edits included (the UI's form warns first).
- User guidance: `Video.clip_prompt` (migration `0005`; whitespace collapsed, ≤ 1000
  chars) — set on `POST /api/videos` (`clip_prompt`), upload (`?clip_prompt=`) or the
  optional body of `/analyze` (replaces it). It lives on the video because the dispatcher
  creates ANALYZE with no payload. `system_prompt(..., guidance)` /
  `rank_system_prompt(guidance)` add it before "Reply with JSON only."; **empty ⇒ the
  default prompts byte-for-byte** (tested).
- Malformed JSON is retried once per window; if *every* window is malformed the
  stage fails. Provider errors fail it immediately. Re-analysis replaces the
  video's clips (`ClipRepository.replace_for_video`).
- Each clip gets a default `Edl` (`domain/models/edl.py`): one range, 9:16, centre
  crop, caption words copied from the transcript (source time).
- LLM adapters: `openai_compat` asks for `response_format: json_schema` and parses
  leniently (`<think>` blocks, code fences); `anthropic` forces a single tool whose
  `input_schema` is the schema. **The Anthropic SDK v2 is built on `httpx2`** —
  test mocks must use `httpx2.MockTransport`, not `httpx`.

Overlays & music:
- `Edl.overlays` times are on the **output** (clip) timeline, unlike everything
  else; the timeline lane maps them with `outputToSource`. Styles: `OverlayStyle`
  (`title`, `label`).
- Built-in music: 90 CC0 tracks in `assets/music/manifest.json` (source + license
  per track); `make music` (`scripts/fetch_music.py`, stdlib, host Python 3.9-safe)
  downloads them; mp3s are gitignored. Mounted read-only at `/opt/music`
  (`DEFAULT_MUSIC_DIR`). `music_path()` tries uploads first, then built-ins — so
  `save_music` must write to the uploads dir explicitly (it once wrote into the
  built-in folder).
- Music library: `data/music/<8 hex>-<slug>.<ext>`, managed by
  `MusicLibraryService` (`/api/music`, raw-body upload). `Edl.music.file` must
  match a safe-name pattern, and saving a clip checks the file exists. Music time
  = clip output time, looped; the preview approximates ducking with the VAD
  speech map (the render will use a sidechain compressor).

Export (EXPORT job, `jobs:render` stream):
- An export **is** a job: `clip_id` set, `video_id` left null (so a failed render
  never fails the video), payload snapshots the EDL + title. Files go to
  `data/videos/<video_id>/exports/<job_id>.{mp4,srt}`; downloads at
  `/api/exports/<job_id>/{video,subtitles}`. No exports table.
- `domain/services/render_planning.plan_render` resolves the EDL to output
  pixels/time (`framing`, `caption_pages`, `edl_timing` are exact ports of the
  frontend's `crop.ts`, `captions.ts`, `edlOps.ts` — tests mirror the TS cases).
- `adapters/output/renderer/`: `ass_builder` (captions + overlays for libass),
  `srt_builder`, `ffmpeg_command` (one `-ss/-t` input per range → concat → crop →
  scale → subtitles; music `-stream_loop`ed, `sidechaincompress`ed by the voice).
- **libass sizes fonts by Windows ascent+descent**, not the em: ASS size = CSS em
  × 1.562 for Montserrat (measured). Change fonts → re-measure `ASS_SIZE_PER_EM`.
- Inline ASS colours are `\c&HBBGGRR&`; style colours are `&HAABBGGRR`.
- **Host Homebrew ffmpeg has no libass** — the real-render test skips on the host;
  the worker image (Debian ffmpeg) has it. Fonts reach the worker via the
  `./assets/fonts:/opt/fonts` mount (`FONTS_DIR`).
- ffmpeg subprocess handling lives in `adapters/output/media/ffmpeg_process.py`,
  shared by media prep and rendering; both use one ffmpeg semaphore.

Zoom-ins:
- `Edl.zooms` (source time, sorted, non-overlapping): `scale` 1–2 over the framed picture,
  centred on the crop (so on the tracked face); `ramp` 0 = hard punch-in, > 0 = linear push.
  Ignored with `split_screen`. `framing.zoom_at` ≡ `crop.ts zoomAt` (mirrored tests).
- Render: `RenderPlan.zooms` (output time) → after `crop,scale=W:H` the pane gets
  `scale=w='2*trunc(W*Z(t)/2)':…:eval=frame,crop=W:H` with `Z(t)` written flat (one
  `gte*lt` term per zoom, `clip()` ramp for pushes). `subtitles=` comes after, so captions
  never zoom. Needs ffmpeg ≥ 5 (`t` in `scale` with `eval=frame`).
- `domain/services/auto_zoom.py` (pure) places them: hook push, punches alternating on
  sentence changes every 3–6 s, ×1.3 on loud stretches (`peaks.json`, clearly above the
  clip's median), ×1.25 on the payoff (last sentence). Priority energy > payoff > hook >
  beats; pieces < 0.8 s dropped. `POST /api/clips/{id}/auto-zoom` returns them unsaved
  (the editor's "Auto zoom" applies them as one undo step).

Automatic edit → outbox (`AUTO_ZOOM`, `AUTO_TRACK`, `AUTO_EXPORT`):
- ANALYZE adds zooms to each clip, then hands clips on best first with `rank = i+1`:
  `request_tracking(auto_rank=…)` (never reuses a job) or `request_export(outbox_rank=…)`.
- An `auto_rank` TRACK job applies the shots to the clip **in the worker** (nobody has it
  open) and queues the export; if tracking fails (no faces, tracker error) it exports
  centre-cropped anyway.
- An `outbox_rank` EXPORT also copies the mp4 to
  `<OUTBOX_DIR>/<video title> [<id8>]/<NN> <caption>.mp4` + `.json` sidecar (caption,
  rank, score, ids, `posted`, `failures`). Names via `domain/services/outbox_naming.py`
  (Windows-safe, ≤ 120 chars, ` (2)` on collision); the **sidecar holds the exact
  caption** and is written last. Default `OUTBOX_DIR` = `<DATA_DIR>/outbox` = `./data/outbox`.
- `Clip.caption` (LLM: hook line + 3–5 hashtags; editable in the Export tab, sent as
  `caption` on `PUT /api/clips/{id}`, omitted = unchanged). Migration `0004`.
- 50 clips: `CLIP_MAX_COUNT=50`, `LLM_CLIPS_PER_WINDOW=5`, `CLIP_MAX_OVERLAP=0.2`. Only the
  top 20 (by rubric) go to the head-to-head ranking (context size); the rest follow in rubric
  order and are never scored above a ranked clip.

Poster (`poster/`, host only, like `whisper-server/`):
- Own uv project (`cd poster && uv run pytest`). Playwright with the installed Chrome
  (`BROWSER_CHANNEL=chrome`), one persistent profile per platform in `poster/profiles/`
  (gitignored — logged-in sessions).
- `uv run poster login <platform>` opens **plain Chrome** (not Playwright-driven) on that
  profile for a by-hand login; `poster serve [--dry-run]` (`make poster`) posts Post-button
  clips right away; `poster run [--dry-run] [--once]` (`make poster-schedule`) posts the
  automatic outbox on schedule; `poster status`.
- Platforms: youtube, tiktok, instagram, **x**, facebook (`PLATFORMS` in `poster/.env`;
  default the first four). X text is cut to 280 chars (`platforms/x.py fit_text`).
- **Post button**: `POST /api/clips/{id}/post` = an EXPORT with `outbox_rank=0` plus
  `post_now`, `description` (= clip **title** + `Clip.post_caption`, joined by
  `outbox_naming.post_description`) and `platforms` (`POST_PLATFORMS`) in the
  payload and sidecar. `post_caption` (migration `0006`) is the card's free-text field
  ("#lacy"); the optional body `{post_caption}` saves it on the clip, omitted = keep. `serve` polls every 5 s and posts each `post_now` clip to each
  named platform it has enabled (no schedule/cap); `run` skips `post_now` clips.
  `GET /api/clips/{id}/post` reads the sidecar back (204 if never posted); the card polls it.
- The sidecars are the queue's state (`posted`/`failures`/`blocked` per platform);
  `state.json` only keeps each platform's planned next slot and a `paused` reason.
  Login/captcha pages pause the platform (no evasion) and, for Post clicks, write
  `blocked[platform].reason`; errors **after** the upload starts count as a failure
  (`MAX_FAILURES` → `gave_up`), errors before it (site slow, browser won't start) don't.
  Failures back off (serve: 1 min doubling; run: 15 min).
- `schedule.py` (pure): `POSTS_PER_DAY` (10) spread over `ACTIVE_HOURS` (9-23) with ±25%
  jitter; cap reached → next day's opening.
- `poster delete [--platform P] [--check | --yes] [--limit N]` (`deleting.py`) takes down
  only what the sidecars record as posted: YouTube/X by the saved link (Studio "Delete
  forever"; X caret → Delete), TikTok by caption in Studio's content list (skipped unless
  exactly one row matches). Default lists only; `--check` opens each delete dialog and
  cancels; `--yes` deletes and writes `deleted[platform]` (keeps `posted`, so nothing is
  re-uploaded). Its selectors were written without a live check — verify with `--check`.
- Selectors live at the top of each `platforms/*.py`; failures save a screenshot to
  `poster/logs/`. They will need updating when the sites change.

Face tracking (TRACK job, `jobs:tracking` stream):
- "Face tracking" checkbox → `POST /api/clips/{id}/tracking` → a TRACK job over the clip's
  bounds ± 2 s. A queued/running/succeeded job that covers the ranges is **reused**.
  The worker writes `data/videos/<video_id>/tracking/<job_id>.json`; the **editor**
  applies it to the EDL (`GET /api/tracking/{job_id}` → `mergeTracking`), so autosave
  can't clobber it. Trimming past `tracking.span` re-tracks and keeps the old shots.
- `OnnxFaceTrackerAdapter`: ffmpeg streams 25 fps `bgr24` (long side ≤ 1280) → YuNet
  faces → greedy IoU tracker → Light-ASD scores per frame from 112 px grayscale crops +
  MFCC (`python_speech_features`, must match training). It holds its own semaphore, not
  the ffmpeg one (the decode lasts the whole job). ~0.6–1.2× realtime on CPU.
- Light-ASD is PyTorch-only upstream: `Dockerfile.worker`'s `asd-export` stage converts
  it with `scripts/export_light_asd.py` (pinned commit, checksummed weights, ONNX vs torch
  check), so torch never reaches the runtime image. Its audio encoder's `MaxPool3d` on
  4-D input doesn't export; the script swaps in the equivalent `MaxPool2d`.
- `speaker_shots.build_shots` (pure): joins track pieces of one person, picks the top
  positive score per frame (held through silence), merges shots < 1.5 s.
- `Edl.tracking.shots` are source time with x/y only; **zoom is shared** (`edl.crop.scale`)
  so the crop size never changes and the render switches position with a step
  expression in the crop filter (`RenderPlan.crop_moves`) — no extra inputs.
  `framing.crop_at` ≡ `crop.ts cropAt`. Tracking on ⇒ `split_screen` is ignored.
- The first shot starts **exactly** at `span.start` (other shot times are rounded to ms)
  and the span start is rounded to ms; `edl_rules` allows 1 ms. (A rounded first shot vs
  an unrounded span once made every autosave of a tracked clip 422.)
- The editor waits for autosave (`whenSaved`) before `POST …/tracking`, since the server
  tracks the clip's *saved* bounds. A queued job shows "waiting for the worker…".

Streamer mode (`Edl.facecam`):
- `Facecam(x, y, scale)` = the source window (4:3, centre + zoom) shown in a fixed box at
  the bottom right: 40% of the frame's shorter side wide, 4% inset (`framing.pip_box` ≡
  `crop.ts pipBox`, `facecam_window` ≡ `facecamWindow`, mirrored tests). Main frame =
  the normal `crop` (gameplay); zooms apply to it only.
- Facecam set ⇒ split and tracking are ignored (`tracking_on` is false); the toolbar keeps
  the three exclusive. Render: `[cut]split=2[main][cam]` → gameplay pane, `crop,scale`
  facecam → `overlay` → `subtitles` (captions stay on top). `RenderPlan.pip`; not part of
  `crops` (the pane height divides by `len(crops)`).
- Preview: a `.pip` canvas fed from the one `<video>` (like the split's bottom pane); its
  pointer handlers `stopPropagation` so dragging it pans the facecam, not the gameplay.

## Narrator (stories)

The UI has two tabs: **Clipper** (everything above) and **Narrator**. A story is a `Video`
with `kind = "story"` and `story: StorySpec` (JSONB, migration `0007`); its `source.mp4`
is *built*, then it joins the clipping pipeline, so the editor/render/outbox/poster are
shared. The frontend filters `GET /api/videos` by `kind` per tab.

- Pipeline: `NARRATE` → `COMPOSE` → `PREPARE` → `VAD` → `TRANSCRIBE` → `ANALYZE`
  (`_NEXT_STAGE`; all on `jobs:analysis`). `AnalysisRouter` (the ANALYZE handler) sends
  stories to `StoryClipService` instead of clip finding. `POST /api/stories` queues NARRATE.
- NARRATE (`StoryNarrationService`): `story_text.clean_for_speech` → optional LLM polish →
  Kokoro → `narration.wav` (24 kHz) → Rhubarb → `lipsync.json` (only with a character).
  Saves the narration length in `video.duration`; COMPOSE cuts `source.mp4` to exactly that.
- **Polish is shaped for a 7B model**: ~500-word chunks rewritten as *plain text*
  (`LLMPort.complete_text`, not JSON), each kept only if `rewrite_ok` (70–140% of the
  words); title/caption is a separate tiny JSON call. Any LLM failure falls back to the
  user's text — the stage never fails because of the LLM.
- COMPOSE: black 1080×1920 (`-f lavfi color`, `-tune stillimage`) or a gameplay clip from
  the library (chosen file / random in category / random), random offset, looped if short.
- Story ANALYZE: `story_parts.split_parts` cuts at pauses into parts ≤
  `STORY_PART_MAX_SECONDS` (140: X without Premium; Reels/Shorts allow 180) that tile the timeline. Each
  part: `Edl.for_span` + title overlay (Part 1: title, else "Part N") + `edl.character` +
  `captions.y` just above the head. One 7B JSON call per 60 lines picks expressions
  (`moods`), merged by `character_timeline.merge_moods`; malformed ⇒ neutral. Parts go to
  the outbox in order (`outbox_rank = part`) when AUTO_EXPORT/AUTO_TRACK is on.
- **Captions `y`** (`Captions.y`, `RenderPlan.caption_y`): bottom edge of the caption block
  as a fraction of the height; ASS `\an2\pos`, CSS `padding-bottom: (1-y)·100cqh`. None =
  the style's own spot (so clipper clips are unchanged).
- Kokoro: `kokoro-onnx` int8 model + voices, checksummed in `Dockerfile.worker`,
  `make models` for the host. Voices in `domain/models/story.py VOICES` (the API image
  validates without Kokoro). Rhubarb 1.14.0 (Linux zip, checksummed) lives in
  `/opt/rhubarb` with its `res/` folder; it runs with `--dialogFile` (the known text).

Characters (`assets/characters/<name>/`, drawn by `scripts/make_characters.py`, stdlib):
- Layers on one 1000×1500 canvas (`CANVAS_ASPECT` 2:3): `base/<emotion>.svg` (figure +
  eyes, no mouth), `mouth/{A..H,X}.svg` (Rhubarb shapes), `blink.svg`, `preview.svg`.
  White figures with near-black outlines; the guy's dark hair/beard have a grey rim so
  they read on black. Change the script and re-run `make characters`.
- `domain/services/character_timeline.py` ≡ `editor/character.ts` (mirrored tests): box
  geometry, mouth at t (binary search), moods, **deterministic blinks** (Park–Miller, exact
  in JS doubles), idle bob. All source time; the render maps output→source with
  `edl_timing.output_to_source`.
- Render: `character_frames.write_character_video` rasterises each layer once with
  `resvg-py` (cv2 decodes the PNG), composites BGRA frames at 30 fps and pipes them into
  ffmpeg (`run_ffmpeg_fed`) → `<export>.character.mov` (qtrle, alpha); the main command
  overlays it after crop/zoom and before `subtitles=` (`bob_margin` rows pad the box).
- Preview: `CharacterLayer` mounts every layer once and toggles `visibility` (no flicker);
  drag moves it. Mouth cues come from `lipsync.json` (editor assets `mouthCues`).

Background library (gameplay for stories): `data/backgrounds/<category>/<8hex>-<slug>.mp4`,
video only, short side ≤ 1080. `BACKGROUND` jobs (`jobs:ingest`, no video/clip id) download
via yt-dlp or take an upload from `data/backgrounds/.incoming/<job_id>/`, re-encode to
`.partial.mp4`, then rename (a story never picks a half-written clip). A failed upload keeps
its scratch file so Retry works. `GET /api/backgrounds` lists ready clips + unfinished jobs
(`JobRepository.list_by_type`).

## Things that will bite you

- **Frame-evaluated zoom must centre by hand:** after `scale=…:eval=frame`, `crop`'s
  `iw/ih` (and its default centring) keep the configured size, so a plain `crop=W:H`
  cropped the **top-left**. `_zoom` writes `x/y` from `t` with the same factor as the scale.
- **SSE and shutdown:** `/api/events` never ends, so uvicorn must run with
  `--timeout-graceful-shutdown` (set in compose and `Dockerfile.api`); without it
  every reload/stop hangs while a browser tab is open.
- **Redis pub/sub ignores the db number:** tests on db 15 still share channels with
  the running app. Give pub/sub tests their own channel
  (`RedisPubSubProgressAdapter(redis, channel)`).

## Conventions

- ruff: `E,F,I,N,UP,B,SIM,TID`, line 100, py312; N818 ignored (`App*Exception` names).
- pytest: `asyncio_mode = "auto"`, session-scoped loop, `pythonpath = ["."]`.
- App code only calls `logging.getLogger(__name__)`; setup is in `config/logging_config.py`.
- Async everywhere. Blocking libs go through a thread pool; each external
  resource gets an `asyncio.Semaphore` inside its adapter.

## Tests

`make test` (or `docker compose up -d postgres redis && cd backend && uv run pytest`).
Persistence/Redis tests hit the compose services: Postgres db `sectra_test`
(created by `tests/conftest.py`, schema from ORM metadata, tables truncated per
test) and Redis db 15 (flushed per test). Application tests use the in-memory
fakes in `tests/unit/fakes.py`. Media tests generate clips with the host's
`ffmpeg` (`tests/unit/media_samples.py`).

## Frontend

Editor (`frontend/src/editor/`, `timeline/`):
- One zustand store (`editor/store.ts`) shared by the middle panel and the bottom
  timeline; zundo tracks **only `edl`**. Every edit goes through `edit(fn)` = one
  undo step, so drags (trim handles, crop pan, zoom slider) keep a local draft
  and commit once on release.
- Pure logic lives in `edlOps.ts`, `captions.ts`, `crop.ts` with vitest tests
  (`docker compose exec web npx vitest run`). `captions.paginate` and
  `crop.cropWindow` define what the export must reproduce — the backend renderer
  has to port them exactly.
- `Edl.split_screen` ("OmeTV split"): left half of the source over the right half;
  `crop` frames each half identically (`crop_window(..., split=True)`). The preview's
  bottom pane is a `<canvas>` drawn from the one `<video>` every frame — a second
  `<video>` would drift. The render does `split → crop ×2 → vstack`.
- Captions follow the ranges (`withRanges`): edited words that stay kept are
  preserved; newly kept stretches are filled from the transcript.
- `useAutosave` PUTs the EDL 800 ms after the last change, one request at a time,
  and flushes when switching clips. The backend re-validates (`edl_rules.py`).
- Caption presets size text in `cqmin` (fraction of the frame's shorter side) with
  the bundled Montserrat files from `assets/fonts` (mounted at `/fonts`).
- The timeline is custom (canvas waveform + lanes on one time→px scale), not
  wavesurfer.js. `Timeline` only mounts `TimelineView` once the clip is loaded:
  measuring the track (ResizeObserver) before it exists threw and — with no error
  boundary — unmounted the whole app. Editor and timeline are now wrapped in
  `ErrorBoundary`, so a panel crash shows an error instead of a blank page.
- Zoom lane in the timeline (select a zoom to drag its edges; `crop.updateZoom` keeps it
  between its neighbours) and a **Zoom** side-panel tab. The preview scales a `.zoomer`
  wrapper around the `<video>` inside the pane, so captions/overlays don't zoom.
- Sources take several URLs at once (one per line); each is a separate `POST /api/videos`.
- Clip cards have one-click **Post** (`panels/useClipPosting.ts`): render into the
  outbox, then per-platform chips (✓ posted with link, ✗ gave up, 🔒 needs `poster
  login`, … waiting) from polling `GET /api/clips/{id}/post`. Blocked while the open clip
  has unsaved edits. Download lives in the editor's Export tab.
- Sources has a "What kind of clips?" field sent with every URL/upload; "Find clips
  again" opens a form prefilled with the video's `clip_prompt`.

UI checks without a desktop browser: run Playwright headless in Docker on the web
container's network (so `localhost:5173` is Vite and its host check passes):
`docker run --rm --network container:sectra-web-1 -v <dir>:/ui
mcr.microsoft.com/playwright/python:v1.64.1-noble sh -c 'pip install
--break-system-packages playwright==1.64.1 && python /ui/script.py'`. Its
Chromium plays the H.264 proxy fine.

Node is **not** installed on the host; run npm inside the `web` container
(`docker compose exec web npm …`). `node_modules` lives in an anonymous volume,
so after changing dependencies run `docker compose up -d --build web`.
