"""Output port for probing and transcoding media."""

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol

from src.domain.models.media import MediaInfo, NormalizePlan

OnProgress = Callable[[float], Awaitable[None]]


class MediaPort(Protocol):
    """All methods raise ``MediaProcessingException`` on failure."""

    async def probe(self, path: Path) -> MediaInfo: ...

    async def normalize(
        self, src: Path, dst: Path, plan: NormalizePlan, duration: float, on_progress: OnProgress
    ) -> None:
        """Write ``src`` to ``dst`` as an MP4 following ``plan`` (stream copy where allowed)."""
        ...

    async def extract_audio(self, src: Path, dst: Path) -> None:
        """16 kHz mono 16-bit PCM WAV."""
        ...

    async def make_thumbnail(self, src: Path, dst: Path, at_seconds: float) -> None: ...

    async def compute_peaks(self, wav: Path, dst: Path, per_second: int) -> None:
        """Write the waveform as JSON ``{"per_second": n, "peaks": [0..1, ...]}``."""
        ...
