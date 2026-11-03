"""Output port for finding faces and scoring who is speaking."""

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol

from src.domain.models.face_track import FaceTrack
from src.domain.models.speech import TimeSpan


class FaceTrackerPort(Protocol):
    async def track(
        self,
        source: Path,
        audio: Path,
        span: TimeSpan,
        source_size: tuple[int, int],
        on_progress: Callable[[float], Awaitable[None]],
    ) -> list[FaceTrack]:
        """Faces in ``span`` of ``source`` (``source_size`` pixels), sampled at
        ``FRAME_RATE``, each with a speaking score per frame from the video and the
        16 kHz mono ``audio``."""
        ...
