from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from src.application.dto.job import JobDTO
from src.domain.enums.video_status_enum import VideoStatus
from src.domain.models.job import Job
from src.domain.models.video import Video


class AddVideoRequest(BaseModel):
    url: str = Field(min_length=1, pattern=r"^https?://")


class VideoDTO(BaseModel):
    id: UUID
    title: str
    source_url: str | None
    status: VideoStatus
    duration: float | None
    width: int | None
    height: int | None
    created_at: datetime
    #: Most recent pipeline job, i.e. the stage the video is in (or last finished).
    current_job: JobDTO | None

    @classmethod
    def from_domain(cls, video: Video, job: Job | None) -> "VideoDTO":
        return cls(
            **video.model_dump(exclude={"updated_at"}),
            current_job=JobDTO.from_domain(job) if job else None,
        )
