"""Output port for persisting clips."""

from typing import Protocol
from uuid import UUID

from src.domain.models.clip import Clip


class ClipRepository(Protocol):
    async def replace_for_video(self, video_id: UUID, clips: list[Clip]) -> None:
        """Atomically swap the video's clips for ``clips`` (re-analysis starts over)."""
        ...

    async def list_for_video(self, video_id: UUID) -> list[Clip]:
        """The video's clips, best score first."""
        ...

    async def get(self, clip_id: UUID) -> Clip | None: ...

    async def save(self, clip: Clip) -> None:
        """Persist every mutable field of an existing clip."""
        ...
