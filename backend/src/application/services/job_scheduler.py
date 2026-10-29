from datetime import UTC, datetime

from src.domain.enums.job_status_enum import JobStatus
from src.domain.models.job import Job, JobEvent
from src.ports.output.job_queue_port import JobQueuePort
from src.ports.output.job_repository import JobRepository
from src.ports.output.progress_port import ProgressPort


class JobScheduler:
    """Persists, queues and announces jobs. Shared by every service that starts work."""

    def __init__(self, jobs: JobRepository, queue: JobQueuePort, progress: ProgressPort) -> None:
        self._jobs = jobs
        self._queue = queue
        self._progress = progress

    async def submit(self, job: Job) -> None:
        # Persist before enqueueing so the worker can always find the row.
        await self._jobs.add(job)
        await self._queue.enqueue(job)
        await self._progress.publish(JobEvent.from_job(job))

    async def resubmit(self, job: Job) -> None:
        """Reset an existing job to its initial state and queue it again."""
        job.status = JobStatus.QUEUED
        job.progress = 0.0
        job.error = None
        job.attempts = 0
        job.updated_at = datetime.now(UTC)
        await self._jobs.save(job)
        await self._queue.enqueue(job)
        await self._progress.publish(JobEvent.from_job(job))
