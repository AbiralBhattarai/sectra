"""Output port for voice activity detection."""

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel


class FrameProbabilities(BaseModel):
    """Speech probability for each consecutive frame of the audio."""

    frame_seconds: float
    probabilities: list[float]


class VADPort(Protocol):
    async def frame_probabilities(
        self, wav: Path, on_progress: Callable[[float], Awaitable[None]]
    ) -> FrameProbabilities:
        """Score every frame of a 16 kHz mono WAV."""
        ...
