"""Output port for fetching a video from a URL."""

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel


class DownloadResult(BaseModel):
    path: Path
    title: str | None
    duration: float | None


class DownloaderPort(Protocol):
    async def download(
        self, url: str, dest_dir: Path, on_progress: Callable[[float], Awaitable[None]]
    ) -> DownloadResult:
        """Download ``url`` into ``dest_dir`` as ``raw.<ext>``, preferring formats whose
        short side is ≤ 1080. Raises ``DownloadException`` on failure."""
        ...
