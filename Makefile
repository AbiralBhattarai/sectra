.PHONY: up down logs migrate test lint models music whisper poster poster-schedule

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
	curl -sSfL -o backend/models/face_detection_yunet.onnx \
		https://github.com/opencv/opencv_zoo/raw/f12e12798e8314f7c074a6656816c048dcc95b7a/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
	docker build -f backend/Dockerfile.worker --target asd-model -o backend/models backend

# Default background-music library (90 CC0 tracks, ~600 MB) listed in assets/music/manifest.json.
music:
	python3 scripts/fetch_music.py

# Native Whisper on the Apple GPU (MLX). Run it next to Ollama; the worker reaches it at
# host.docker.internal:9000 when STT_PROVIDER=openai_compat (see .env.example).
whisper:
	cd whisper-server && uv run uvicorn app:app --host 127.0.0.1 --port 9000

# Posts clips sent with the clip card's Post button right away (host, real Chrome). Log in
# once per platform first: cd poster && uv run poster login <youtube|tiktok|instagram|x>
poster:
	cd poster && uv run poster serve

# Posts the automatic outbox (AUTO_EXPORT) on a schedule instead.
poster-schedule:
	cd poster && uv run poster run
