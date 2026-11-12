from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from src.domain.enums.video_kind_enum import VideoKind
from src.domain.enums.video_status_enum import VideoStatus


def _now() -> datetime:
    return datetime.now(UTC)


class Video(BaseModel):
    """A video downloaded from a URL or uploaded: a long-form source to find clips in,
    or an asset (B-roll, intro…) to edit with."""

    id: UUID = Field(default_factory=uuid4)
    title: str
    kind: VideoKind = VideoKind.SOURCE
    source_url: str | None = None
    status: VideoStatus = VideoStatus.PROCESSING
    duration: float | None = None
    width: int | None = None
    height: int | None = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
