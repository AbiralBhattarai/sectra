# Sectra

Sectra turns long videos into short, captioned clips, and runs on your own machine.
Paste a YouTube URL or drop in a file. Sectra finds the speech, transcribes it,
asks an LLM for the best standalone moments, and lets you polish each clip in a
browser editor. It exports vertical (or square or landscape) MP4s with captions
burned in.

Every model can run locally or in the cloud: the LLM through **Ollama** or any
OpenAI-compatible/Anthropic API, and speech-to-text through **faster-whisper** or
any OpenAI-compatible transcription API.

## Features

- **Ingest:** YouTube (or anything yt-dlp supports) or a local upload. Every source
  is stored with its short side capped at 1080 px.
- **Speech detection:** Silero VAD (ONNX) finds speech, so only speech is transcribed.
- **Transcription:** word-level timestamps from local faster-whisper or a cloud API.
- **Highlight finding:** the LLM reads the transcript in overlapping windows and
  proposes clips. Sectra snaps them to sentence boundaries, keeps them 15–60 s,
  removes duplicates and keeps the best 10.
- **Editor:**
  - live preview with trim, split and delete
  - 9:16, 1:1 or 16:9 output with a draggable crop and zoom
  - editable caption words and timing, with style presets
  - text overlays and background music with automatic ducking
  - undo/redo and autosave
- **Timeline:** waveform, kept ranges with trim handles, speech, captions and overlays.
- **Export:** 1080p H.264 MP4 with captions and overlays burned in (rendered with the
  same fonts as the preview), plus an `.srt` file. Each clip card also has a one-click
  **Download** that renders the clip if needed.
- **Built-in music:** 90 public-domain (CC0) tracks grouped by mood, with preview, plus
  your own uploads.

## How it works

```
URL / upload ─▶ ingest ─▶ normalize ─▶ prepare ─▶ VAD ─▶ transcribe ─▶ analyze ─▶ clips
               (yt-dlp)   (≤1080p)    (proxy,     (Silero)  (Whisper)    (LLM)
                                       audio,
                                       waveform)
clip ─▶ editor (edit decision list, autosaved) ─▶ export (ffmpeg + libass) ─▶ MP4 + SRT
```

Each stage is a background job on a Redis Stream, processed by an async worker.
Progress streams to the browser over Server-Sent Events. A failed stage can be
retried from the UI.

| Service    | What it is                                                     | Host port |
| ---------- | -------------------------------------------------------------- | --------- |
| `web`      | React + TypeScript (Vite)                                      | 5173      |
| `api`      | FastAPI (async), REST + SSE, serves media                       | 8000      |
| `worker`   | Async job runner: yt-dlp, ffmpeg, Silero, Whisper, LLM, render | —         |
| `whisper-server` (native, `make whisper`) | Whisper on the Apple GPU (MLX), outside Docker | 9000 |
| `postgres` | Postgres 17                                                    | 5433      |
| `redis`    | Redis (job queue + progress pub/sub)                           | 6380      |

Postgres and Redis use non-default host ports so they don't clash with other local
instances.

## Requirements

- **Docker** with Compose v2 (Docker Desktop on macOS/Windows). Everything runs in
  containers; no local Python or Node is needed to use the app.
- An **LLM**: either [Ollama](https://ollama.com) running natively, or an API key for a
  cloud provider.
- With the GPU Whisper service, 6 GB of RAM for Docker is enough (Docker Desktop →
  Settings → Resources). That leaves room for Whisper and the LLM on a 16 GB Mac.

## Quick start

```bash
cp .env.example .env      # then pick your LLM, see below
make music                # one-time: download the built-in CC0 music library (~560 MB)
make whisper              # in its own terminal: GPU speech-to-text (Apple Silicon), keep it running
make up                   # = docker compose up -d --build
```

Open **http://localhost:5173**, paste a YouTube URL in the left panel, and watch it
go through the stages. When the clips appear on the right, click one to edit it, and
use the **Export** tab to render it.

```bash
make logs                 # follow the api + worker logs
make down                 # stop (data is kept)
```

The first transcription downloads the Whisper model (~500 MB for `small`) into a
Docker volume, so it is slower than later runs.

## Choosing the LLM

All provider settings come from `.env`. Restart the worker after changing them
(`docker compose up -d worker`).

### Ollama (local, the default)

Ollama should run **natively** (not in Docker) so it can use your GPU / Apple Silicon.
The containers reach it at `host.docker.internal`.

```bash
ollama pull qwen2.5:14b
```

```env
LLM_PROVIDER=openai_compat
LLM_BASE_URL=http://host.docker.internal:11434/v1
LLM_MODEL=qwen2.5:14b
LLM_CONCURRENCY=1
```

Sectra sends 10 minutes of transcript per request (`LLM_WINDOW_SECONDS=600`), which
needs an **8k context**, but Ollama defaults to 4k and would silently cut the transcript.
The simplest fix is an 8k variant of your model. It shares the same weights, so it costs
no extra disk:

```bash
printf 'FROM qwen2.5:7b\nPARAMETER num_ctx 8192\n' > Modelfile
ollama create qwen2.5:7b-8k -f Modelfile     # then LLM_MODEL=qwen2.5:7b-8k
```

Alternatively, keep the 4k context and set `LLM_WINDOW_SECONDS=300`. On Linux, start
Ollama with `OLLAMA_HOST=0.0.0.0` so containers can reach it.

### OpenAI-compatible cloud (OpenAI, Groq, OpenRouter, LM Studio, vLLM, …)

```env
LLM_PROVIDER=openai_compat
LLM_BASE_URL=https://api.openai.com/v1      # or https://api.groq.com/openai/v1, …
LLM_MODEL=<model-name>                      # any chat model the provider offers
LLM_API_KEY=sk-...
LLM_CONCURRENCY=4
```

### Anthropic (Claude)

```env
LLM_PROVIDER=anthropic
LLM_MODEL=claude-sonnet-5-5
LLM_API_KEY=sk-ant-...
LLM_CONCURRENCY=4
```

## Choosing speech-to-text

### Local on the Apple GPU (default, fastest)

Docker on macOS can't use the GPU, so Sectra includes a small native Whisper service
(`whisper-server/`, [mlx-whisper](https://pypi.org/project/mlx-whisper/)) that runs next
to Ollama. Start it with `make whisper` and keep it running. The first request downloads
`whisper-large-v3-turbo` (~1.6 GB) into your Hugging Face cache.

```env
STT_PROVIDER=openai_compat
STT_BASE_URL=http://host.docker.internal:9000/v1
STT_MODEL=mlx-community/whisper-large-v3-turbo
STT_CONCURRENCY=2
```

If it isn't running, transcription fails with a connection error. Start it, then press
*Retry* on the video.

### Local on the CPU, inside Docker (no extra service, much slower)

```env
# Sizes: tiny, base, small, medium, large-v3.
STT_PROVIDER=faster_whisper
STT_MODEL=small
STT_CONCURRENCY=1

# Or any OpenAI-compatible /audio/transcriptions API that returns word timestamps:
STT_PROVIDER=openai_compat
STT_BASE_URL=https://api.groq.com/openai/v1
STT_MODEL=whisper-large-v3
STT_API_KEY=gsk_...
STT_CONCURRENCY=4
```

For long videos, use the GPU service or a cloud provider. Set `STT_LANGUAGE=en` (or
another ISO code) to skip language detection.

## How clips are picked

The LLM reads the transcript in overlapping windows. Lines where the audio is among the
loudest 20% of the video are flagged, because shouting, celebrating and reactions are
often the best moments. For each clip it proposes, the LLM rates five qualities from
0 to 10, and Sectra computes the score from them with fixed weights:

| Quality      | Weight | Question                                   |
| ------------ | ------ | ------------------------------------------ |
| Hook         | 30%    | Do the first seconds stop the scroll?      |
| Emotion      | 25%    | Hype, anger, laughter, shock, tension      |
| Payoff       | 20%    | Is there a punchline, reveal or result?    |
| Standalone   | 15%    | Does it make sense with no context?        |
| Shareability | 10%    | Is it quotable, or would people send it on? |

The best ~20 candidates from the whole video then go to the LLM in one request, which
ranks them against each other. That ranking counts for half of the final score.

A bigger model picks noticeably better clips than a small local one. If results feel
flat, try a larger Ollama model or a cloud LLM, then use **Find clips again** in the
clips panel. Note that it replaces the video's clips, including your edits.

## Built-in music

`make music` downloads 90 tracks listed in `assets/music/manifest.json` into
`assets/music/`. They show up in the editor's **Music** tab, grouped by mood. Every
track is **CC0 1.0 (public domain)**: you can use, modify and redistribute it,
commercially too, with no attribution. They come from:

- [FreePD](https://archive.org/details/abook-music-freepd-cc0): 40 tracks, via an
  attributed CC0 mirror (the FreePD site has closed).
- [Loyalty Freak Music](https://archive.org/search?query=creator%3A%22Loyalty+Freak+Music%22): 25 tracks.
- [Komiku](https://archive.org/search?query=creator%3AKomiku): 16 tracks.
- [Monplaisir](https://archive.org/details/Monplaisir-Power_Animal): 9 tracks.

The manifest records each track's exact source page and license. Moods are a best
guess from titles and albums. Tracks you upload are stored in `data/music/` and are
listed after the built-in ones.

## Configuration reference

All settings are environment variables in `.env`; `.env.example` documents each one.
The app checks them at startup and refuses to start with a clear message when a
combination is invalid.

| Variable                                          | Default                                | Meaning                                                          |
| ------------------------------------------------- | -------------------------------------- | ---------------------------------------------------------------- |
| `LLM_PROVIDER`                                    | `openai_compat`                        | `openai_compat` or `anthropic`                                   |
| `LLM_BASE_URL`                                    | `http://host.docker.internal:11434/v1` | Required for `openai_compat`                                     |
| `LLM_MODEL` / `LLM_API_KEY`                       | `qwen2.5:14b` / –                      | API key required for cloud providers and `anthropic`             |
| `LLM_CONCURRENCY`                                 | `2`                                    | LLM requests in flight at once                                   |
| `LLM_WINDOW_SECONDS`                              | `300`                                  | Seconds of transcript per LLM request                            |
| `STT_PROVIDER`                                    | `faster_whisper`                       | `faster_whisper` or `openai_compat`                              |
| `STT_MODEL` / `STT_BASE_URL` / `STT_API_KEY`      | `small` / – / –                        | Base URL required for `openai_compat`                            |
| `STT_CONCURRENCY`                                 | `1`                                    | Speech chunks transcribed at once                                |
| `STT_LANGUAGE`                                    | auto                                   | ISO language code                                                |
| `CLIP_MIN_SECONDS` / `CLIP_MAX_SECONDS`           | `15` / `60`                            | Clip length bounds                                               |
| `CLIP_MAX_COUNT`                                  | `10`                                   | Clips kept per video                                             |
| `DOWNLOAD_CONCURRENCY`                            | `2`                                    | Parallel yt-dlp downloads                                        |
| `FFMPEG_CONCURRENCY`                              | `2`                                    | Parallel ffmpeg processes (preparation + export)                 |
| `VAD_CONCURRENCY`                                 | `2`                                    | Files scored by Silero at once                                   |
| `JOB_CONCURRENCY` / `JOB_MAX_ATTEMPTS`            | `4` / `3`                              | Jobs per queue at once; retries for a job that crashes the worker |
| `YTDLP_COOKIES_FILE`                              | –                                      | Netscape cookies file for videos that need a login; put it in `data/` and use `/data/cookies.txt` |

`DATABASE_URL`, `REDIS_URL`, `DATA_DIR`, `VAD_MODEL_PATH` and `FONTS_DIR` are set by
`docker-compose.yaml` for the containers. The values in `.env` only apply when you
run the backend on the host.

## Using the editor

| Action                          | How                                                       |
| ------------------------------- | --------------------------------------------------------- |
| Play / pause                    | `Space`, or click the preview                             |
| Trim                            | Drag a range's edge handle on the timeline                |
| Cut a section out               | Put the playhead in it, press `S` twice, select the middle range, press `Delete` |
| Undo / redo                     | `⌘Z` / `⇧⌘Z` (`Ctrl` on Windows/Linux)                    |
| Reframe                         | Drag the picture; use the Zoom slider                     |
| Zoom / pan the timeline         | `⌘`/`Ctrl` + scroll / scroll                              |
| Fix a caption                   | **Captions** tab → click a word → edit text or timing     |
| Add a text overlay              | **Text** tab → *Add text at playhead*, then drag it on the preview |
| Background music                | **Music** tab → upload or pick a track, set volume and ducking |
| Render                          | **Export** tab → *Export MP4 + captions* → download       |

Edits save automatically shortly after you stop. The toolbar shows the save state,
and export is enabled once everything is saved.

## Development

The compose stack is set up for development. The API reloads when `backend/src`
changes, the worker reads the same mounted source (restart it with
`docker compose restart worker`), and Vite hot-reloads the frontend.

### Backend on the host

```bash
cd backend
uv sync                      # Python 3.12 + all dependency groups
make -C .. models            # Silero VAD model for host runs/tests
docker compose up -d postgres redis
uv run alembic upgrade head
uv run uvicorn src.api_main:create_app --factory --reload
uv run python -m src.worker_main
```

### Tests and lint

```bash
make test                                   # backend: pytest (needs postgres + redis up)
make lint                                   # ruff check + format check
docker compose exec web npx vitest run      # frontend logic tests
docker compose exec web npx tsc -b          # frontend type-check
```

Backend tests use a separate `sectra_test` database and Redis db 15. Media tests need
`ffmpeg` on the host. The speech tests use macOS `say`. The real-render test skips
when the host ffmpeg has no libass (the worker image has it).

### Migrations

```bash
backend/scripts/make_migration.sh "describe the change"   # autogenerate
make migrate                                              # apply in the stack
```

### Architecture

The backend is hexagonal (ports and adapters), and dependencies point inwards:

```
backend/src/
├── domain/        # models, enums, pure services (VAD chunking, clip selection, framing, captions)
├── ports/         # Protocols — input/ (use cases), output/ (repos, queue, LLM, STT, VAD, media, renderer)
├── application/   # services implementing the use cases, DTOs, prompts
├── adapters/
│   ├── input/     # rest/ (FastAPI + SSE), worker/ (Redis Streams consumer)
│   └── output/    # persistence/, queue/, events/, llm/, stt/, vad/, downloader/, media/, renderer/, storage/
└── config/        # settings, composition roots (container.py, worker_container.py)
```

Ruff (`TID251`) enforces that only composition roots import adapters. Everything is
async. Blocking libraries run in a thread pool, and every external resource
(downloads, ffmpeg, VAD, STT, LLM) is guarded by its own semaphore. `CLAUDE.md` has
the deeper notes.

```
frontend/src/
├── panels/        # sources (left) and clips (right)
├── editor/        # store (zustand + zundo), preview, captions/overlay/music/export tabs, pure EDL logic
└── timeline/      # canvas waveform + lanes
```

## Data

Everything lives in `./data` (bind-mounted) and in Docker volumes:

```
data/videos/<id>/   source.mp4 (also what the editor plays), audio.wav, peaks.json, thumbnail.jpg,
                    speech.json, transcript.json, exports/<export-id>.{mp4,srt}
data/music/         uploaded background tracks
assets/music/       built-in CC0 library (manifest committed, mp3s from `make music`)
```

Deleting a video in the UI removes its files, clips and exports. To start completely
fresh, run `docker compose down -v && rm -rf data`.

## Troubleshooting

- **The "find clips" stage fails with a connection error:** the LLM isn't reachable.
  Check that Ollama is running (`curl localhost:11434/api/version`) or that your cloud
  key is set, then press *Retry* on the video.
- **A YouTube download fails:** update the worker image (`make up` rebuilds it with the
  latest yt-dlp). For videos that need a login, export your browser cookies to
  `data/cookies.txt` and set `YTDLP_COOKIES_FILE=/data/cookies.txt`.
- **Transcription is slow:** check that `make whisper` is running and `.env` points at
  it (see *Choosing speech-to-text*). On the CPU path, use a smaller `STT_MODEL`.
- **"Video has no audio track":** clips are found from speech, so silent videos are
  rejected.

## Licenses and responsible use

The caption fonts are Montserrat, under the SIL Open Font License
(`assets/fonts/OFL.txt`). The built-in music is CC0. Sources are in
`assets/music/manifest.json`. Only download and republish videos you have the rights to.
