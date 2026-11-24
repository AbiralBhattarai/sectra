"""Input port: the gameplay background library."""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Protocol

from src.domain.models.background import Background, PendingBackground
from src.domain.models.job import Job


class BackgroundLibraryPort(Protocol):
    async def add_from_url(self, url: str, category: str) -> Job:
        """Queue a download into ``category``."""
        ...

    async def add_upload(self, filename: str, category: str, chunks: AsyncIterator[bytes]) -> Job:
        """Store an uploaded clip and queue its re-encode."""
        ...

    async def list(self) -> tuple[list[Background], list[PendingBackground]]:
        """Finished clips, and recent BACKGROUND jobs that haven't succeeded."""
        ...

    async def path(self, category: str, file: str) -> Path: ...

    async def delete(self, category: str, file: str) -> None: ...
