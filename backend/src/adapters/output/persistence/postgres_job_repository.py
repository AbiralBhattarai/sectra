from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.adapters.output.persistence.models import JobRow
from src.domain.enums.job_status_enum import JobStatus
from src.domain.enums.job_type_enum import JobType
from src.domain.models.job import Job


class PostgresJobRepository:
    def __init__(self, sessionmaker: async_sessionmaker) -> None:
        self._sessionmaker = sessionmaker

    async def add(self, job: Job) -> None:
        async with self._sessionmaker.begin() as session:
            session.add(_to_row(job))

    async def get(self, job_id: UUID) -> Job | None:
        async with self._sessionmaker() as session:
            row = await session.get(JobRow, job_id)
            return _to_domain(row) if row else None

    async def save(self, job: Job) -> None:
        async with self._sessionmaker.begin() as session:
            await session.execute(
                update(JobRow)
                .where(JobRow.id == job.id)
                .values(
                    status=job.status.value,
                    progress=job.progress,
                    error=job.error,
                    attempts=job.attempts,
                    updated_at=job.updated_at,
                )
            )

    async def latest_for_videos(self, video_ids: list[UUID]) -> dict[UUID, Job]:
        if not video_ids:
            return {}
        query = (
            select(JobRow)
            .where(JobRow.video_id.in_(video_ids))
            .order_by(JobRow.video_id, JobRow.created_at.desc())
            .ext(distinct_on(JobRow.video_id))
        )
        async with self._sessionmaker() as session:
            return {row.video_id: _to_domain(row) for row in await session.scalars(query)}

    async def list_for_clip(self, clip_id: UUID, job_type: JobType) -> list[Job]:
        query = (
            select(JobRow)
            .where(JobRow.clip_id == clip_id, JobRow.type == job_type.value)
            .order_by(JobRow.created_at.desc())
        )
        async with self._sessionmaker() as session:
            return [_to_domain(row) for row in await session.scalars(query)]


def _to_row(job: Job) -> JobRow:
    return JobRow(
        id=job.id,
        type=job.type.value,
        status=job.status.value,
        video_id=job.video_id,
        clip_id=job.clip_id,
        payload=job.payload,
        progress=job.progress,
        error=job.error,
        attempts=job.attempts,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _to_domain(row: JobRow) -> Job:
    return Job(
        id=row.id,
        type=JobType(row.type),
        status=JobStatus(row.status),
        video_id=row.video_id,
        clip_id=row.clip_id,
        payload=row.payload,
        progress=row.progress,
        error=row.error,
        attempts=row.attempts,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
