from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from src.domain.enums.video_kind_enum import VideoKind
from src.domain.enums.video_status_enum import VideoStatus
from src.domain.models.story import StorySpec


def _now() -> datetime:
    return datetime.now(UTC)


class Video(BaseModel):
    """A long-form source video, downloaded from a URL or uploaded; or a narrated story,
    whose ``source.mp4`` the worker builds from the narration."""

    id: UUID = Field(default_factory=uuid4)
    title: str
    source_url: str | None = None
    status: VideoStatus = VideoStatus.PROCESSING
    duration: float | None = None
    width: int | None = None
    height: int | None = None
    #: What kind of clips the user wants (added to the clip-finding prompt); "" = default.
    clip_prompt: str = ""
    kind: VideoKind = VideoKind.SOURCE
    #: Set for stories only.
    story: StorySpec | None = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
