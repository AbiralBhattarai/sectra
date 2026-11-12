"""Input port: browse and edit clips. Every edit goes through here (the browser editor
and, later, an MCP server), is validated, and becomes one undoable revision."""

from typing import Protocol
from uuid import UUID

from src.domain.models.clip import Clip, ClipRevision
from src.domain.models.edit_command import EditCommand
from src.domain.models.edl import Edl, Tracking
from src.domain.models.timeline import TimelineView


class ClipEditingPort(Protocol):
    async def list_for_video(self, video_id: UUID) -> list[Clip]:
        """Raises ``NotFoundException`` when the video doesn't exist."""
        ...

    async def get(self, clip_id: UUID) -> Clip: ...

    async def apply_edits(
        self,
        clip_id: UUID,
        commands: list[EditCommand],
        base_revision: int | None = None,
        dry_run: bool = False,
        actor: str = "editor",
    ) -> Clip:
        """Apply ``commands`` in order as one revision. Raises ``AppValidationException``
        (naming the failing command) for edits that can't be rendered, and
        ``AppConflictException`` when ``base_revision`` is given but stale. With
        ``dry_run`` the result is returned without being saved."""
        ...

    async def update_edl(
        self, clip_id: UUID, edl: Edl, base_revision: int | None = None, actor: str = "editor"
    ) -> Clip:
        """Replace the whole EDL (one revision)."""
        ...

    async def undo(self, clip_id: UUID, actor: str = "editor") -> Clip:
        """Raises ``AppValidationException`` when there's nothing to undo."""
        ...

    async def redo(self, clip_id: UUID, actor: str = "editor") -> Clip: ...

    async def describe(self, clip_id: UUID) -> TimelineView: ...

    async def history(self, clip_id: UUID) -> list[ClipRevision]: ...

    async def apply_tracking(self, clip_id: UUID, tracking: Tracking) -> Clip:
        """Merge a face-tracking result into the clip's EDL."""
        ...
