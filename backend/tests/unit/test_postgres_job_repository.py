from uuid import uuid4

from src.adapters.output.persistence.postgres_job_repository import PostgresJobRepository
from src.adapters.output.persistence.postgres_video_repository import PostgresVideoRepository
from src.domain.enums.job_status_enum import JobStatus
from src.domain.enums.job_type_enum import JobType
from src.domain.models.job import Job
from src.domain.models.video import Video


async def test_add_get_save_round_trip(pg_sessionmaker):
    repo = PostgresJobRepository(pg_sessionmaker)
    video = Video(title="talk")
    await PostgresVideoRepository(pg_sessionmaker).add(video)
    job = Job(type=JobType.INGEST, video_id=video.id, payload={"steps": 2})

    await repo.add(job)
    loaded = await repo.get(job.id)
    assert loaded == job

    job.status, job.progress, job.error, job.attempts = JobStatus.FAILED, 0.5, "boom", 2
    await repo.save(job)
    assert await repo.get(job.id) == job


async def test_get_missing_returns_none(pg_sessionmaker):
    assert await PostgresJobRepository(pg_sessionmaker).get(uuid4()) is None
