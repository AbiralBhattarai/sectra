from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.adapters.output.persistence.models import ClipRow
from src.domain.models.clip import Clip
from src.domain.models.edl import Edl


class PostgresClipRepository:
    def __init__(self, sessionmaker: async_sessionmaker) -> None:
        self._sessionmaker = sessionmaker

    async def replace_for_video(self, video_id: UUID, clips: list[Clip]) -> None:
        async with self._sessionmaker.begin() as session:
            await session.execute(delete(ClipRow).where(ClipRow.video_id == video_id))
            session.add_all(_to_row(clip) for clip in clips)

    async def list_for_video(self, video_id: UUID) -> list[Clip]:
        query = (
            select(ClipRow)
            .where(ClipRow.video_id == video_id)
            .order_by(ClipRow.score.desc(), ClipRow.start)
        )
        async with self._sessionmaker() as session:
            return [_to_domain(row) for row in await session.scalars(query)]

    async def get(self, clip_id: UUID) -> Clip | None:
        async with self._sessionmaker() as session:
            row = await session.get(ClipRow, clip_id)
            return _to_domain(row) if row else None

    async def save(self, clip: Clip) -> None:
        async with self._sessionmaker.begin() as session:
            await session.execute(
                update(ClipRow)
                .where(ClipRow.id == clip.id)
                .values(
                    **clip.model_dump(exclude={"id", "video_id", "created_at", "edl"}),
                    edl=clip.edl.model_dump(mode="json"),
                )
            )


def _to_row(clip: Clip) -> ClipRow:
    return ClipRow(**clip.model_dump(exclude={"edl"}), edl=clip.edl.model_dump(mode="json"))


def _to_domain(row: ClipRow) -> Clip:
    return Clip(
        id=row.id,
        video_id=row.video_id,
        title=row.title,
        hook=row.hook,
        score=row.score,
        reason=row.reason,
        start=row.start,
        end=row.end,
        edl=Edl.model_validate(row.edl),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
