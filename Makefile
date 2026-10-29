.PHONY: up down logs migrate test lint models music whisper

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f api worker

migrate:
	docker compose run --rm migrate

test:
	docker compose up -d postgres redis
	cd backend && uv run pytest

lint:
	cd backend && uv run ruff check . && uv run ruff format --check .

# Silero VAD model for running the worker/tests on the host (the worker image has its own).
models:
	mkdir -p backend/models
	curl -sSfL -o backend/models/silero_vad.onnx \
		https://github.com/snakers4/silero-vad/raw/v6.2.3/src/silero_vad/data/silero_vad.onnx

# Default background-music library (90 CC0 tracks, ~600 MB) listed in assets/music/manifest.json.
music:
	python3 scripts/fetch_music.py

# Native Whisper on the Apple GPU (MLX). Run it next to Ollama; the worker reaches it at
# host.docker.internal:9000 when STT_PROVIDER=openai_compat (see .env.example).
whisper:
	cd whisper-server && uv run uvicorn app:app --host 127.0.0.1 --port 9000
