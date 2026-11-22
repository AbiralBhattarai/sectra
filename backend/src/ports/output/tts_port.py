"""Output port for text-to-speech."""

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol


class TTSPort(Protocol):
    async def narrate(
        self,
        sentences: list[str],
        voice: str,
        speed: float,
        pause_seconds: float,
        dst: Path,
        on_progress: Callable[[float], Awaitable[None]],
    ) -> float:
        """Speak ``sentences`` one after another (``pause_seconds`` of silence between)
        into ``dst`` as a mono 16-bit WAV; returns its length in seconds. Raises
        ``SpeechSynthesisException``."""
        ...
