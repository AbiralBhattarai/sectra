"""Output port for handing jobs to the worker."""

from typing import Protocol

from src.domain.models.job import Job


class JobQueuePort(Protocol):
    async def enqueue(self, job: Job) -> None:
        """Queue ``job`` on the stream its type belongs to. The job must already be persisted."""
        ...
