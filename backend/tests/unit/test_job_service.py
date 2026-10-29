from uuid import uuid4

import pytest

from src.application.services.job_service import JobService
from src.domain.enums.job_status_enum import JobStatus
from src.domain.enums.job_type_enum import JobType
from src.domain.enums.video_status_enum import VideoStatus
from src.domain.exceptions import AppValidationException, NotFoundException
from src.domain.models.job import Job
from src.domain.models.video import Video
from tests.unit.fakes import Fakes


@pytest.fixture
def fakes():
    return Fakes()


@pytest.fixture
def service(fakes):
    return JobService(
        jobs=fakes.jobs, videos=fakes.videos, scheduler=fakes.scheduler, progress=fakes.progress
    )


async def test_submit_ping_persists_enqueues_and_announces(fakes, service):
    job = await service.submit_ping(steps=3)

    assert fakes.jobs.jobs[job.id].payload == {"steps": 3}
    assert [j.id for j in fakes.queue.enqueued] == [job.id]
    assert fakes.progress.events[0].status is JobStatus.QUEUED


async def test_get_missing_job_raises_not_found(service):
    with pytest.raises(NotFoundException):
        await service.get(uuid4())


async def test_retry_resets_failed_job_and_reopens_video(fakes, service):
    video = Video(title="talk", status=VideoStatus.FAILED)
    await fakes.videos.add(video)
    job = Job(
        type=JobType.NORMALIZE,
        video_id=video.id,
        status=JobStatus.FAILED,
        error="boom",
        attempts=1,
        progress=0.4,
    )
    await fakes.jobs.add(job)

    await service.retry(job.id)

    stored = fakes.jobs.jobs[job.id]
    assert (stored.status, stored.error, stored.attempts, stored.progress) == (
        JobStatus.QUEUED,
        None,
        0,
        0.0,
    )
    assert [j.id for j in fakes.queue.enqueued] == [job.id]
    assert fakes.videos.videos[video.id].status is VideoStatus.PROCESSING


async def test_retry_refuses_jobs_that_have_not_failed(fakes, service):
    job = Job(type=JobType.PING, status=JobStatus.RUNNING)
    await fakes.jobs.add(job)
    with pytest.raises(AppValidationException):
        await service.retry(job.id)
