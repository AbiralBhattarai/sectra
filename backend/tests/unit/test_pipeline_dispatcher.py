import pytest

from src.application.services.ping_service import PingService
from src.application.services.pipeline_dispatcher import PipelineDispatcher
from src.domain.enums.job_status_enum import JobStatus
from src.domain.enums.job_type_enum import JobType
from src.domain.enums.video_status_enum import VideoStatus
from src.domain.models.job import Job
from src.domain.models.video import Video
from tests.unit.fakes import Fakes


@pytest.fixture
def fakes():
    return Fakes()


def dispatcher(fakes, handlers, max_attempts=3):
    return PipelineDispatcher(
        jobs=fakes.jobs,
        videos=fakes.videos,
        scheduler=fakes.scheduler,
        progress=fakes.progress,
        handlers=handlers,
        max_attempts=max_attempts,
    )


async def noop(job, report):
    pass


async def test_successful_job_reports_progress_and_succeeds(fakes):
    job = Job(type=JobType.PING, payload={"steps": 4})
    await fakes.jobs.add(job)

    await dispatcher(fakes, {JobType.PING: PingService(step_delay=0)}).run_job(job.id)

    stored = fakes.jobs.jobs[job.id]
    assert stored.status is JobStatus.SUCCEEDED
    assert stored.progress == 1.0
    assert stored.attempts == 1
    events = fakes.progress.events
    assert [e.status for e in events] == [JobStatus.RUNNING] * 5 + [JobStatus.SUCCEEDED]
    assert [e.progress for e in events[1:5]] == [0.25, 0.5, 0.75, 1.0]


async def test_success_queues_the_next_stage_for_the_video(fakes):
    video = Video(title="talk")
    await fakes.videos.add(video)
    job = Job(type=JobType.INGEST, video_id=video.id)
    await fakes.jobs.add(job)

    await dispatcher(fakes, {JobType.INGEST: noop}).run_job(job.id)

    [queued] = fakes.queue.enqueued
    assert (queued.type, queued.video_id) == (JobType.NORMALIZE, video.id)
    assert fakes.videos.videos[video.id].status is VideoStatus.PROCESSING


async def test_last_stage_marks_video_ready(fakes):
    video = Video(title="talk")
    await fakes.videos.add(video)
    job = Job(type=JobType.ANALYZE, video_id=video.id)
    await fakes.jobs.add(job)

    await dispatcher(fakes, {JobType.ANALYZE: noop}).run_job(job.id)

    assert fakes.queue.enqueued == []
    assert fakes.videos.videos[video.id].status is VideoStatus.READY


async def test_handler_exception_fails_job_and_video_without_raising(fakes):
    async def boom(job, report):
        raise RuntimeError("ffmpeg exploded")

    video = Video(title="talk")
    await fakes.videos.add(video)
    job = Job(type=JobType.NORMALIZE, video_id=video.id)
    await fakes.jobs.add(job)

    await dispatcher(fakes, {JobType.NORMALIZE: boom}).run_job(job.id)

    stored = fakes.jobs.jobs[job.id]
    assert stored.status is JobStatus.FAILED
    assert stored.error == "ffmpeg exploded"
    assert fakes.videos.videos[video.id].status is VideoStatus.FAILED
    assert fakes.queue.enqueued == []


async def test_redelivered_finished_job_is_not_rerun(fakes):
    calls = []

    async def handler(job, report):
        calls.append(job.id)

    job = Job(type=JobType.PING, status=JobStatus.SUCCEEDED)
    await fakes.jobs.add(job)

    await dispatcher(fakes, {JobType.PING: handler}).run_job(job.id)

    assert calls == []
    assert fakes.progress.events == []


async def test_job_that_keeps_crashing_the_worker_gives_up(fakes):
    calls = []

    async def handler(job, report):
        calls.append(job.id)

    # Two earlier deliveries never finished (worker died while RUNNING).
    job = Job(type=JobType.PING, status=JobStatus.RUNNING, attempts=2)
    await fakes.jobs.add(job)

    await dispatcher(fakes, {JobType.PING: handler}, max_attempts=2).run_job(job.id)

    stored = fakes.jobs.jobs[job.id]
    assert calls == []
    assert stored.status is JobStatus.FAILED
    assert stored.error == "Gave up after 2 attempts"


async def test_unknown_job_is_ignored(fakes):
    job = Job(type=JobType.PING)
    await dispatcher(fakes, {JobType.PING: PingService(step_delay=0)}).run_job(job.id)
    assert fakes.progress.events == []
