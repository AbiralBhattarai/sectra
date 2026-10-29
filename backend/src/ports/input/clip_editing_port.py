"""Input port: browse and edit clips."""

from typing import Protocol
from uuid import UUID

from src.domain.models.clip import Clip
from src.domain.models.edl import Edl


class ClipEditingPort(Protocol):
    async def list_for_video(self, video_id: UUID) -> list[Clip]:
        """Raises ``NotFoundException`` when the video doesn't exist."""
        ...

    async def get(self, clip_id: UUID) -> Clip: ...

    async def update_edl(self, clip_id: UUID, edl: Edl) -> Clip:
        """Replace the clip's edit. Raises ``AppValidationException`` for edits that
        can't be rendered (empty, overlapping or out-of-bounds ranges)."""
        ...
