"""Output port for persisting source videos."""

from typing import Protocol
from uuid import UUID

from src.domain.models.video import Video


class VideoRepository(Protocol):
    async def add(self, video: Video) -> None: ...

    async def get(self, video_id: UUID) -> Video | None: ...

    async def list(self) -> list[Video]:
        """All videos, newest first."""
        ...

    async def save(self, video: Video) -> None:
        """Persist every mutable field of an existing video."""
        ...

    async def delete(self, video_id: UUID) -> None:
        """Delete the video and, by cascade, its jobs."""
        ...
