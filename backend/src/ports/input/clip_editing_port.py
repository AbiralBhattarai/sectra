"""Input port: browse and edit clips."""

from typing import Protocol
from uuid import UUID

from src.domain.models.clip import Clip
from src.domain.models.edl import Edl, Zoom
from src.domain.models.speech import TimeSpan


class ClipEditingPort(Protocol):
    async def list_for_video(self, video_id: UUID) -> list[Clip]:
        """Raises ``NotFoundException`` when the video doesn't exist."""
        ...

    async def get(self, clip_id: UUID) -> Clip: ...

    async def update_edl(self, clip_id: UUID, edl: Edl, caption: str | None = None) -> Clip:
        """Replace the clip's edit (and its social caption, unless None). Raises
        ``AppValidationException`` for edits that can't be rendered (empty, overlapping
        or out-of-bounds ranges or zooms)."""
        ...

    async def auto_zoom(self, clip_id: UUID, ranges: list[TimeSpan]) -> list[Zoom]:
        """Automatic zoom-ins for the clip cut to ``ranges`` (not saved)."""
        ...
