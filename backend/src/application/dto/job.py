from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from src.domain.enums.job_status_enum import JobStatus
from src.domain.enums.job_type_enum import JobType
from src.domain.models.job import Job


class PingRequest(BaseModel):
    steps: int = Field(default=5, ge=1, le=100)


class JobDTO(BaseModel):
    id: UUID
    type: JobType
    status: JobStatus
    video_id: UUID | None
    clip_id: UUID | None
    progress: float
    error: str | None
    attempts: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, job: Job) -> "JobDTO":
        return cls.model_validate(job.model_dump(exclude={"payload"}))
