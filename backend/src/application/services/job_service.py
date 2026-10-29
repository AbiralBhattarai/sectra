from collections.abc import AsyncIterator
from uuid import UUID

from src.application.services.job_scheduler import JobScheduler
from src.domain.enums.job_status_enum import JobStatus
from src.domain.enums.job_type_enum import JobType
from src.domain.enums.video_status_enum import VideoStatus
from src.domain.exceptions import AppValidationException, NotFoundException
from src.domain.models.job import Job, JobEvent
from src.ports.output.job_repository import JobRepository
from src.ports.output.progress_port import ProgressPort
from src.ports.output.video_repository import VideoRepository


class JobService:
    def __init__(
        self,
        jobs: JobRepository,
        videos: VideoRepository,
        scheduler: JobScheduler,
        progress: ProgressPort,
    ) -> None:
        self._jobs = jobs
        self._videos = videos
        self._scheduler = scheduler
        self._progress = progress

    async def submit_ping(self, steps: int) -> Job:
        job = Job(type=JobType.PING, payload={"steps": steps})
        await self._scheduler.submit(job)
        return job

    async def get(self, job_id: UUID) -> Job:
        job = await self._jobs.get(job_id)
        if job is None:
            raise NotFoundException(f"Job {job_id} not found")
        return job

    async def retry(self, job_id: UUID) -> Job:
        job = await self.get(job_id)
        if job.status is not JobStatus.FAILED:
            raise AppValidationException(f"Only failed jobs can be retried (job is {job.status})")
        if job.video_id and (video := await self._videos.get(job.video_id)):
            video.status = VideoStatus.PROCESSING
            await self._videos.save(video)
        await self._scheduler.resubmit(job)
        return job

    def events(self) -> AsyncIterator[JobEvent]:
        return self._progress.subscribe()
