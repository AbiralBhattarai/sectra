from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from src.domain.enums.video_status_enum import VideoStatus


def _now() -> datetime:
    return datetime.now(UTC)


class Video(BaseModel):
    """A long-form source video, downloaded from a URL or uploaded."""

    id: UUID = Field(default_factory=uuid4)
    title: str
    source_url: str | None = None
    status: VideoStatus = VideoStatus.PROCESSING
    duration: float | None = None
    width: int | None = None
    height: int | None = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
