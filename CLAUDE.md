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
- Shutdown: SIGTERM drains in-flight jobs for up to 30s, then cancels them
  (they stay pending → replayed). `stop_grace_period: 40s` in compose.
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
  **replaces** the clips, edits included (the UI confirms first).
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

## Things that will bite you

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
- Clip cards have one-click **Download** (`panels/useClipDownloads.ts`): reuse an
  export newer than the clip's `updated_at`, else render and auto-download on the
  SSE success event. Blocked while the open clip has unsaved edits.

UI checks without a desktop browser: run Playwright headless in Docker on the web
container's network (so `localhost:5173` is Vite and its host check passes):
`docker run --rm --network container:sectra-web-1 -v <dir>:/ui
mcr.microsoft.com/playwright/python:v1.64.1-noble sh -c 'pip install
--break-system-packages playwright==1.64.1 && python /ui/script.py'`. Its
Chromium plays the H.264 proxy fine.

Node is **not** installed on the host; run npm inside the `web` container
(`docker compose exec web npm …`). `node_modules` lives in an anonymous volume,
so after changing dependencies run `docker compose up -d --build web`.
