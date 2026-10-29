"""Output port for persisting jobs."""

from typing import Protocol
from uuid import UUID

from src.domain.enums.job_type_enum import JobType
from src.domain.models.job import Job


class JobRepository(Protocol):
    async def add(self, job: Job) -> None:
        """Insert a new job."""
        ...

    async def get(self, job_id: UUID) -> Job | None:
        """Return the job, or ``None`` when it does not exist."""
        ...

    async def save(self, job: Job) -> None:
        """Persist every mutable field of an existing job (status, progress, error, attempts)."""
        ...

    async def latest_for_videos(self, video_ids: list[UUID]) -> dict[UUID, Job]:
        """Most recently created job per video, for the videos that have one."""
        ...

    async def list_for_clip(self, clip_id: UUID, job_type: JobType) -> list[Job]:
        """The clip's jobs of ``job_type``, newest first."""
        ...
