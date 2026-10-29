import asyncio
from concurrent.futures import Executor
from pathlib import Path
from typing import Any

from openai import APIError, AsyncOpenAI

from src.adapters.output.stt.wav_span import to_wav_bytes
from src.domain.exceptions import TranscriptionException
from src.domain.models.speech import TimeSpan
from src.domain.models.transcript import Segment, Transcript, Word
from src.utils.concurrency import run_blocking


class OpenAICompatSTTAdapter:
    """Any server implementing OpenAI's ``/audio/transcriptions`` with
    ``verbose_json`` + word timestamps (OpenAI whisper-1, Groq, local whisper servers).
    The SDK retries 429/5xx with backoff, honouring ``Retry-After``."""

    def __init__(
        self,
        client: AsyncOpenAI,
        model: str,
        semaphore: asyncio.Semaphore,
        executor: Executor,
    ) -> None:
        self._client = client
        self._model = model
        self._semaphore = semaphore
        self._executor = executor

    async def transcribe(self, wav: Path, span: TimeSpan, language: str | None) -> Transcript:
        audio = await run_blocking(self._executor, to_wav_bytes, wav, span)
        options: dict[str, Any] = {"language": language} if language else {}
        async with self._semaphore:
            try:
                response = await self._client.audio.transcriptions.create(
                    file=("chunk.wav", audio, "audio/wav"),
                    model=self._model,
                    response_format="verbose_json",
                    timestamp_granularities=["word", "segment"],
                    **options,
                )
            except APIError as exc:
                raise TranscriptionException(f"Speech-to-text request failed: {exc}") from exc
        return to_transcript(response.model_dump())


def to_transcript(data: dict[str, Any]) -> Transcript:
    """Build a transcript from a verbose_json body, where words and segments are
    separate lists: each word goes to the segment its midpoint falls in."""
    words = [Word(text=w["word"], start=w["start"], end=w["end"]) for w in data.get("words") or []]
    raw_segments = data.get("segments") or []
    if not raw_segments and words:
        # Some servers return only words; treat the chunk as one segment.
        raw_segments = [
            {"start": words[0].start, "end": words[-1].end, "text": data.get("text", "")}
        ]

    segments = [
        Segment(id=index, start=s["start"], end=s["end"], text=s.get("text", ""), words=[])
        for index, s in enumerate(raw_segments)
    ]
    for word in words:
        midpoint = (word.start + word.end) / 2
        owner = next(
            (s for s in reversed(segments) if s.start <= midpoint),
            segments[0] if segments else None,
        )
        if owner is not None:
            owner.words.append(word)
    return Transcript(language=data.get("language"), segments=segments)
