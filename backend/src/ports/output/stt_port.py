"""Output port for speech-to-text."""

from pathlib import Path
from typing import Protocol

from src.domain.models.speech import TimeSpan
from src.domain.models.transcript import Transcript


class STTPort(Protocol):
    async def transcribe(self, wav: Path, span: TimeSpan, language: str | None) -> Transcript:
        """Transcribe ``span`` of a 16 kHz mono WAV with word timestamps. Timestamps
        in the result are relative to ``span.start``. Raises ``TranscriptionException``."""
        ...
