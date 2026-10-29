from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from src.domain.enums.job_status_enum import JobStatus
from src.domain.enums.job_type_enum import JobType


def _now() -> datetime:
    return datetime.now(UTC)


class Job(BaseModel):
    """One unit of background work. Each pipeline stage is its own job."""

    id: UUID = Field(default_factory=uuid4)
    type: JobType
    status: JobStatus = JobStatus.QUEUED
    video_id: UUID | None = None
    clip_id: UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    progress: float = 0.0
    error: str | None = None
    #: Number of times a worker picked the job up; a crash mid-job shows up as > 1.
    attempts: int = 0
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class JobEvent(BaseModel):
    """Progress notification pushed to the UI whenever a job changes."""

    job_id: UUID
    type: JobType
    status: JobStatus
    progress: float
    error: str | None = None
    video_id: UUID | None = None
    clip_id: UUID | None = None

    @classmethod
    def from_job(cls, job: Job) -> "JobEvent":
        return cls(
            job_id=job.id,
            type=job.type,
            status=job.status,
            progress=job.progress,
            error=job.error,
            video_id=job.video_id,
            clip_id=job.clip_id,
        )
