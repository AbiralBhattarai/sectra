import logging
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from uuid import UUID

from src.application.services.job_scheduler import JobScheduler
from src.domain.enums.job_status_enum import JobStatus
from src.domain.enums.job_type_enum import JobType
from src.domain.enums.video_status_enum import VideoStatus
from src.domain.models.job import Job, JobEvent
from src.ports.output.job_repository import JobRepository
from src.ports.output.progress_port import ProgressPort
from src.ports.output.video_repository import VideoRepository

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[float], Awaitable[None]]
"""Reports a job's progress as a fraction in [0, 1]."""

StageHandler = Callable[[Job, ProgressCallback], Awaitable[None]]


class PipelineDispatcher:
    """Runs one job: picks the handler for its type, records the outcome, and on
    success queues the video's next stage."""

    def __init__(
        self,
        jobs: JobRepository,
        videos: VideoRepository,
        scheduler: JobScheduler,
        progress: ProgressPort,
        handlers: Mapping[JobType, StageHandler],
        max_attempts: int,
    ) -> None:
        self._jobs = jobs
        self._videos = videos
        self._scheduler = scheduler
        self._progress = progress
        self._handlers = handlers
        self._max_attempts = max_attempts

    async def run_job(self, job_id: UUID) -> None:
        job = await self._jobs.get(job_id)
        if job is None:
            logger.warning("Skipping unknown job %s", job_id)
            return
        if job.status.is_terminal:
            # Redelivery of a job that already finished (crash between save and ack).
            return

        job.attempts += 1
        if job.attempts > self._max_attempts:
            await self._fail(job, f"Gave up after {self._max_attempts} attempts")
            return

        job.status = JobStatus.RUNNING
        job.error = None
        await self._update(job)

        async def report(fraction: float) -> None:
            job.progress = min(max(fraction, 0.0), 1.0)
            await self._update(job)

        try:
            await self._handlers[job.type](job, report)
        except Exception as exc:
            logger.exception("Job %s (%s) failed", job.id, job.type)
            await self._fail(job, str(exc) or type(exc).__name__)
            return

        # Advance the video before announcing success, so a UI refetch on the
        # event already sees the new state.
        if job.video_id:
            if next_stage := job.type.next_stage:
                await self._scheduler.submit(Job(type=next_stage, video_id=job.video_id))
            else:
                await self._set_video_status(job.video_id, VideoStatus.READY)
        job.status = JobStatus.SUCCEEDED
        job.progress = 1.0
        await self._update(job)

    async def _fail(self, job: Job, error: str) -> None:
        if job.video_id:
            await self._set_video_status(job.video_id, VideoStatus.FAILED)
        job.status = JobStatus.FAILED
        job.error = error
        await self._update(job)

    async def _set_video_status(self, video_id: UUID, status: VideoStatus) -> None:
        video = await self._videos.get(video_id)
        if video is not None:  # deleted while the job ran
            video.status = status
            await self._videos.save(video)

    async def _update(self, job: Job) -> None:
        job.updated_at = datetime.now(UTC)
        await self._jobs.save(job)
        await self._progress.publish(JobEvent.from_job(job))
