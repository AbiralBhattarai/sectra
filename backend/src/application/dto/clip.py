from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from src.domain.models.clip import Clip
from src.domain.models.edl import Edl
from src.domain.models.speech import TimeSpan


class ClipDTO(BaseModel):
    id: UUID
    video_id: UUID
    title: str
    hook: str
    score: int
    reason: str
    caption: str
    post_caption: str
    start: float
    end: float
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, clip: Clip) -> "ClipDTO":
        return cls.model_validate(clip.model_dump(exclude={"edl"}))


class ClipDetailDTO(ClipDTO):
    edl: Edl

    @classmethod
    def from_domain(cls, clip: Clip) -> "ClipDetailDTO":
        return cls.model_validate(clip.model_dump())


class UpdateClipRequest(BaseModel):
    edl: Edl
    #: Left out: the caption is unchanged.
    caption: str | None = Field(default=None, max_length=2200)


class PostClipRequest(BaseModel):
    """Optional body of ``POST /api/clips/{id}/post``."""

    #: Text posted after the title (saved on the clip). Left out: the saved one is used.
    post_caption: str | None = Field(default=None, max_length=2000)


class AutoZoomRequest(BaseModel):
    """Generate zooms for these ranges (the editor's current, maybe unsaved, edit)."""

    ranges: list[TimeSpan] = Field(min_length=1)
