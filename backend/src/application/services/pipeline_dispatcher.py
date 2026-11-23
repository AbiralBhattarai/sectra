import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from uuid import UUID

from src.application.services.job_scheduler import JobScheduler
from src.domain.enums.job_status_enum import JobStatus
from src.domain.enums.job_type_enum import JobType
from src.domain.enums.video_status_enum import VideoStatus
from src.domain.models.job import Job, JobEvent
from src.ports.output.file_storage_port import FileStoragePort
from src.ports.output.job_repository import JobRepository
from src.ports.output.progress_port import ProgressPort
from src.ports.output.video_repository import VideoRepository

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[float], Awaitable[None]]
"""Reports a job's progress as a fraction in [0, 1]."""

StageHandler = Callable[[Job, ProgressCallback], Awaitable[None]]

#: How often a running job checks that its row still exists (deleting a video
#: cascades to its jobs, and that is how the worker learns to stop).
CANCEL_POLL_SECONDS = 3.0


class PipelineDispatcher:
    """Runs one job: picks the handler for its type, records the outcome, and on
    success queues the video's next stage.

    On a stream in ``inline_streams`` (consumed one job at a time) the next stage also
    runs right away in the same call, so a video goes through all of that stream's
    stages before the stream's next message is read. The next stage is still queued
    first, so a crash mid-chain resumes from it; when its message arrives after the
    inline run, the job is already terminal and is skipped.

    A job whose row disappears while it runs (its video was deleted) is cancelled, and
    whatever it wrote for the deleted video is removed."""

    def __init__(
        self,
        jobs: JobRepository,
        videos: VideoRepository,
        scheduler: JobScheduler,
        progress: ProgressPort,
        handlers: Mapping[JobType, StageHandler],
        max_attempts: int,
        inline_streams: frozenset[str] = frozenset(),
        storage: FileStoragePort | None = None,
        cancel_poll_seconds: float = CANCEL_POLL_SECONDS,
    ) -> None:
        self._jobs = jobs
        self._videos = videos
        self._scheduler = scheduler
        self._progress = progress
        self._handlers = handlers
        self._max_attempts = max_attempts
        self._inline_streams = inline_streams
        self._storage = storage
        self._cancel_poll = cancel_poll_seconds

    async def run_job(self, job_id: UUID) -> None:
        next_id: UUID | None = job_id
        while next_id is not None:
            next_id = await self._run_one(next_id)

    async def _run_one(self, job_id: UUID) -> UUID | None:
        """Runs the job; returns the next stage's job id when it should run inline."""
        job = await self._jobs.get(job_id)
        if job is None:
            logger.warning("Skipping unknown job %s", job_id)
            return None
        if job.status.is_terminal:
            # Redelivery of a job that already finished (crash between save and ack, or
            # the message of a stage that already ran inline).
            return None

        job.attempts += 1
        if job.attempts > self._max_attempts:
            await self._fail(job, f"Gave up after {self._max_attempts} attempts")
            return None

        job.status = JobStatus.RUNNING
        job.error = None
        await self._update(job)

        async def report(fraction: float) -> None:
            job.progress = min(max(fraction, 0.0), 1.0)
            await self._update(job)

        try:
            if not await self._run_unless_deleted(job, report):
                logger.info("Job %s (%s) was deleted while running; stopped it", job.id, job.type)
                await self._remove_orphan_files(job)
                return None
        except Exception as exc:
            logger.exception("Job %s (%s) failed", job.id, job.type)
            await self._fail(job, str(exc) or type(exc).__name__)
            return None

        # Advance the video before announcing success, so a UI refetch on the
        # event already sees the new state.
        inline: UUID | None = None
        if job.video_id:
            if next_stage := job.type.next_stage:
                next_job = Job(type=next_stage, video_id=job.video_id)
                await self._scheduler.submit(next_job)
                if next_stage.stream == job.type.stream and job.type.stream in self._inline_streams:
                    inline = next_job.id
            else:
                await self._set_video_status(job.video_id, VideoStatus.READY)
        job.status = JobStatus.SUCCEEDED
        job.progress = 1.0
        await self._update(job)
        return inline

    async def _run_unless_deleted(self, job: Job, report: ProgressCallback) -> bool:
        """Runs the handler; returns False if the job's row vanished and it was stopped."""
        work = asyncio.create_task(self._handlers[job.type](job, report))
        try:
            while True:
                done, _ = await asyncio.wait({work}, timeout=self._cancel_poll)
                if done:
                    work.result()  # re-raises the handler's exception
                    return True
                if await self._jobs.get(job.id) is None:
                    work.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await work
                    return False
        except asyncio.CancelledError:
            # Shutdown: stop the handler too, and stay cancelled (the job is replayed).
            work.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await work
            raise

    async def _remove_orphan_files(self, job: Job) -> None:
        if self._storage is None or job.video_id is None:
            return
        if await self._videos.get(job.video_id) is None:
            await self._storage.delete_video(job.video_id)

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
