from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.adapters.output.persistence.models import VideoRow
from src.domain.enums.video_status_enum import VideoStatus
from src.domain.models.video import Video


class PostgresVideoRepository:
    def __init__(self, sessionmaker: async_sessionmaker) -> None:
        self._sessionmaker = sessionmaker

    async def add(self, video: Video) -> None:
        async with self._sessionmaker.begin() as session:
            session.add(VideoRow(**video.model_dump(mode="python")))

    async def get(self, video_id: UUID) -> Video | None:
        async with self._sessionmaker() as session:
            row = await session.get(VideoRow, video_id)
            return _to_domain(row) if row else None

    async def list(self) -> list[Video]:
        async with self._sessionmaker() as session:
            rows = await session.scalars(select(VideoRow).order_by(VideoRow.created_at.desc()))
            return [_to_domain(row) for row in rows]

    async def save(self, video: Video) -> None:
        async with self._sessionmaker.begin() as session:
            await session.execute(
                update(VideoRow)
                .where(VideoRow.id == video.id)
                .values(**video.model_dump(exclude={"id", "created_at"}))
            )

    async def delete(self, video_id: UUID) -> None:
        async with self._sessionmaker.begin() as session:
            await session.execute(delete(VideoRow).where(VideoRow.id == video_id))


def _to_domain(row: VideoRow) -> Video:
    return Video(
        id=row.id,
        title=row.title,
        source_url=row.source_url,
        status=VideoStatus(row.status),
        duration=row.duration,
        width=row.width,
        height=row.height,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
