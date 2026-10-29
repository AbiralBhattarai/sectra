from datetime import UTC, datetime, timedelta

from src.adapters.output.persistence.postgres_job_repository import PostgresJobRepository
from src.adapters.output.persistence.postgres_video_repository import PostgresVideoRepository
from src.domain.enums.job_type_enum import JobType
from src.domain.enums.video_status_enum import VideoStatus
from src.domain.models.job import Job
from src.domain.models.video import Video


async def test_round_trip_and_newest_first(pg_sessionmaker):
    repo = PostgresVideoRepository(pg_sessionmaker)
    older = Video(title="old", created_at=datetime.now(UTC) - timedelta(minutes=1))
    newer = Video(title="new", source_url="https://a.example")
    await repo.add(older)
    await repo.add(newer)

    newer.status, newer.duration, newer.width, newer.height = VideoStatus.READY, 12.5, 1920, 1080
    await repo.save(newer)

    assert await repo.get(newer.id) == newer
    assert [v.id for v in await repo.list()] == [newer.id, older.id]


async def test_delete_cascades_to_jobs(pg_sessionmaker):
    videos = PostgresVideoRepository(pg_sessionmaker)
    jobs = PostgresJobRepository(pg_sessionmaker)
    video = Video(title="talk")
    await videos.add(video)
    job = Job(type=JobType.INGEST, video_id=video.id)
    await jobs.add(job)

    await videos.delete(video.id)

    assert await videos.get(video.id) is None
    assert await jobs.get(job.id) is None


async def test_latest_job_per_video(pg_sessionmaker):
    videos = PostgresVideoRepository(pg_sessionmaker)
    jobs = PostgresJobRepository(pg_sessionmaker)
    a, b = Video(title="a"), Video(title="b")
    await videos.add(a)
    await videos.add(b)
    start = datetime.now(UTC)
    first = Job(type=JobType.INGEST, video_id=a.id, created_at=start)
    second = Job(type=JobType.NORMALIZE, video_id=a.id, created_at=start + timedelta(seconds=1))
    for job in (first, second):
        await jobs.add(job)

    latest = await jobs.latest_for_videos([a.id, b.id])

    assert latest == {a.id: second}
