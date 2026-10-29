"""Whisper on the Apple GPU (MLX) behind the slice of OpenAI's transcription API that
Sectra's `openai_compat` STT adapter uses. Runs natively on the Mac (Docker can't reach
the GPU); the worker container calls it at http://host.docker.internal:9000/v1."""

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, UploadFile

logger = logging.getLogger("sectra-whisper")

DEFAULT_MODEL = "mlx-community/whisper-large-v3-turbo"

app = FastAPI(title="Sectra Whisper (MLX)")
# One transcription on the GPU at a time; concurrent requests queue here.
_gpu = asyncio.Lock()


def transcribe(path: str, model: str, language: str | None) -> dict[str, Any]:
    """mlx-whisper call, isolated so tests can replace it. Imported lazily so the
    module loads (and tests run) without pulling MLX in."""
    import mlx_whisper

    return mlx_whisper.transcribe(
        path,
        path_or_hf_repo=model,
        word_timestamps=True,
        language=language,
        # Sectra sends independent ≤30 s chunks; conditioning invites repetition loops.
        condition_on_previous_text=False,
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/audio/transcriptions")
async def transcriptions(
    file: Annotated[UploadFile, File()],
    model: Annotated[str, Form()] = DEFAULT_MODEL,
    language: Annotated[str | None, Form()] = None,
    response_format: Annotated[str, Form()] = "verbose_json",
) -> dict[str, Any]:
    """Always answers verbose_json with word timestamps (what Sectra asks for)."""
    suffix = Path(file.filename or "audio.wav").suffix or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp.flush()
        async with _gpu:
            result = await asyncio.to_thread(transcribe, tmp.name, model, language or None)
    return to_verbose_json(result)


def to_verbose_json(result: dict[str, Any]) -> dict[str, Any]:
    """mlx-whisper nests words inside segments; OpenAI's verbose_json lists them
    separately, which is what Sectra parses."""
    segments = result.get("segments") or []
    words = [
        {"word": w["word"].strip(), "start": float(w["start"]), "end": float(w["end"])}
        for s in segments
        for w in s.get("words") or []
        if w.get("word", "").strip()
    ]
    return {
        "task": "transcribe",
        "language": result.get("language"),
        "text": (result.get("text") or "").strip(),
        "duration": float(segments[-1]["end"]) if segments else 0.0,
        "segments": [
            {"id": i, "start": float(s["start"]), "end": float(s["end"]), "text": s["text"]}
            for i, s in enumerate(segments)
        ],
        "words": words,
    }
