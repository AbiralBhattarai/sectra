"""Input port: create, inspect and watch background jobs."""

from collections.abc import AsyncIterator
from typing import Protocol
from uuid import UUID

from src.domain.models.job import Job, JobEvent


class JobManagementPort(Protocol):
    async def submit_ping(self, steps: int) -> Job:
        """Queue a no-op job that reports progress ``steps`` times (end-to-end smoke test)."""
        ...

    async def get(self, job_id: UUID) -> Job:
        """Return the job; raises ``NotFoundException`` when it does not exist."""
        ...

    def events(self) -> AsyncIterator[JobEvent]:
        """Live stream of job progress events."""
        ...

    async def retry(self, job_id: UUID) -> Job:
        """Queue a failed job again; raises ``AppValidationException`` if it hasn't failed."""
        ...
