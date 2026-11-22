from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from src.application.dto.job import JobDTO
from src.domain.enums.video_kind_enum import VideoKind
from src.domain.enums.video_status_enum import VideoStatus
from src.domain.models.job import Job
from src.domain.models.story import StorySpec
from src.domain.models.video import Video

#: Longest "what kind of clips" prompt accepted.
CLIP_PROMPT_MAX = 1000


class AddVideoRequest(BaseModel):
    url: str = Field(min_length=1, pattern=r"^https?://")
    clip_prompt: str = Field(default="", max_length=CLIP_PROMPT_MAX)


class FindClipsRequest(BaseModel):
    #: Replaces the video's stored prompt; omitted = keep it.
    clip_prompt: str | None = Field(default=None, max_length=CLIP_PROMPT_MAX)


class VideoDTO(BaseModel):
    id: UUID
    title: str
    source_url: str | None
    status: VideoStatus
    duration: float | None
    width: int | None
    height: int | None
    clip_prompt: str
    kind: VideoKind
    story: StorySpec | None
    created_at: datetime
    #: Most recent pipeline job, i.e. the stage the video is in (or last finished).
    current_job: JobDTO | None

    @classmethod
    def from_domain(cls, video: Video, job: Job | None) -> "VideoDTO":
        return cls(
            **video.model_dump(exclude={"updated_at"}),
            current_job=JobDTO.from_domain(job) if job else None,
        )
