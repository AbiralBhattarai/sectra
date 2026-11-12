"""Output port for persisting clips and their edit history."""

from typing import Protocol
from uuid import UUID

from src.domain.models.clip import Clip, ClipRevision
from src.domain.models.edl import Edl


class ClipRepository(Protocol):
    async def replace_for_video(self, video_id: UUID, clips: list[Clip]) -> None:
        """Atomically swap the video's clips for ``clips`` (re-analysis starts over)."""
        ...

    async def list_for_video(self, video_id: UUID) -> list[Clip]:
        """The video's clips, best score first."""
        ...

    async def get(self, clip_id: UUID) -> Clip | None: ...

    async def commit_edit(self, clip: Clip, base_revision: int, label: str, actor: str) -> bool:
        """Store ``clip`` (its new EDL and bounds) as revision ``base_revision + 1``,
        dropping any redo history after ``base_revision``; ``clip.revision`` is set.
        Returns False, changing nothing, when the clip is no longer at ``base_revision``
        (someone else edited it first)."""
        ...

    async def revision_edl(self, clip_id: UUID, revision: int) -> Edl | None:
        """The EDL saved as ``revision``, if it is still in the history."""
        ...

    async def move_to_revision(self, clip: Clip, from_revision: int) -> bool:
        """Undo/redo: point the clip at ``clip.revision`` (whose EDL ``clip`` carries)
        without touching the history. False when it is no longer at ``from_revision``."""
        ...

    async def history(self, clip_id: UUID) -> list[ClipRevision]:
        """The kept history, oldest first."""
        ...
