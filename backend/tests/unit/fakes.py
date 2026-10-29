"""In-memory stand-ins for output ports, for application-layer tests."""

from collections.abc import AsyncIterator
from uuid import UUID

from src.application.services.job_scheduler import JobScheduler
from src.domain.models.job import Job, JobEvent
from src.domain.models.video import Video


class InMemoryJobRepository:
    def __init__(self) -> None:
        self.jobs: dict[UUID, Job] = {}

    async def add(self, job: Job) -> None:
        self.jobs[job.id] = job.model_copy(deep=True)

    async def get(self, job_id: UUID) -> Job | None:
        job = self.jobs.get(job_id)
        return job.model_copy(deep=True) if job else None

    async def save(self, job: Job) -> None:
        if job.id in self.jobs:
            self.jobs[job.id] = job.model_copy(deep=True)

    async def latest_for_videos(self, video_ids: list[UUID]) -> dict[UUID, Job]:
        latest: dict[UUID, Job] = {}
        for job in sorted(self.jobs.values(), key=lambda j: j.created_at):
            if job.video_id in video_ids:
                latest[job.video_id] = job
        return latest

    async def list_for_clip(self, clip_id: UUID, job_type) -> list[Job]:
        jobs = [j for j in self.jobs.values() if j.clip_id == clip_id and j.type == job_type]
        return sorted(jobs, key=lambda j: j.created_at, reverse=True)


class InMemoryVideoRepository:
    def __init__(self) -> None:
        self.videos: dict[UUID, Video] = {}

    async def add(self, video: Video) -> None:
        self.videos[video.id] = video.model_copy(deep=True)

    async def get(self, video_id: UUID) -> Video | None:
        video = self.videos.get(video_id)
        return video.model_copy(deep=True) if video else None

    async def list(self) -> list[Video]:
        return sorted(self.videos.values(), key=lambda v: v.created_at, reverse=True)

    async def save(self, video: Video) -> None:
        if video.id in self.videos:
            self.videos[video.id] = video.model_copy(deep=True)

    async def delete(self, video_id: UUID) -> None:
        self.videos.pop(video_id, None)


class RecordingProgress:
    def __init__(self) -> None:
        self.events: list[JobEvent] = []

    async def publish(self, event: JobEvent) -> None:
        self.events.append(event)

    async def subscribe(self) -> AsyncIterator[JobEvent]:
        for event in self.events:
            yield event


class RecordingQueue:
    def __init__(self) -> None:
        self.enqueued: list[Job] = []

    async def enqueue(self, job: Job) -> None:
        self.enqueued.append(job)


class Fakes:
    """One consistent set of fakes plus a scheduler wired to them."""

    def __init__(self) -> None:
        self.jobs = InMemoryJobRepository()
        self.videos = InMemoryVideoRepository()
        self.queue = RecordingQueue()
        self.progress = RecordingProgress()
        self.scheduler = JobScheduler(jobs=self.jobs, queue=self.queue, progress=self.progress)
