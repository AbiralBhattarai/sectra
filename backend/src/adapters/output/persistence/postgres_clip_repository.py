from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.adapters.output.persistence.models import ClipRevisionRow, ClipRow
from src.domain.models.clip import Clip, ClipRevision
from src.domain.models.edl import Edl

#: Undo steps kept per clip.
HISTORY_LIMIT = 200


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

    async def commit_edit(self, clip: Clip, base_revision: int, label: str, actor: str) -> bool:
        async with self._sessionmaker.begin() as session:
            row = await session.get(ClipRow, clip.id, with_for_update=True)
            if row is None or row.revision != base_revision:
                return False
            # The first edit also records where the clip started, so it can be undone.
            if await session.get(ClipRevisionRow, (clip.id, base_revision)) is None:
                session.add(_revision(clip.id, base_revision, row.edl, "Original", "analysis"))
            await session.execute(
                delete(ClipRevisionRow).where(
                    ClipRevisionRow.clip_id == clip.id,
                    (ClipRevisionRow.revision > base_revision)
                    | (ClipRevisionRow.revision <= base_revision + 1 - HISTORY_LIMIT),
                )
            )
            clip.revision = base_revision + 1
            edl = clip.edl.model_dump(mode="json")
            session.add(_revision(clip.id, clip.revision, edl, label, actor))
            await _write_clip(session, clip, edl)
        return True

    async def revision_edl(self, clip_id: UUID, revision: int) -> Edl | None:
        async with self._sessionmaker() as session:
            row = await session.get(ClipRevisionRow, (clip_id, revision))
            return Edl.model_validate(row.edl) if row else None

    async def move_to_revision(self, clip: Clip, from_revision: int) -> bool:
        async with self._sessionmaker.begin() as session:
            row = await session.get(ClipRow, clip.id, with_for_update=True)
            if row is None or row.revision != from_revision:
                return False
            await _write_clip(session, clip, clip.edl.model_dump(mode="json"))
        return True

    async def history(self, clip_id: UUID) -> list[ClipRevision]:
        query = (
            select(ClipRevisionRow)
            .where(ClipRevisionRow.clip_id == clip_id)
            .order_by(ClipRevisionRow.revision)
        )
        async with self._sessionmaker() as session:
            return [
                ClipRevision(
                    revision=r.revision, label=r.label, actor=r.actor, created_at=r.created_at
                )
                for r in await session.scalars(query)
            ]


async def _write_clip(session: AsyncSession, clip: Clip, edl: dict) -> None:
    await session.execute(
        update(ClipRow)
        .where(ClipRow.id == clip.id)
        .values(
            **clip.model_dump(exclude={"id", "video_id", "created_at", "edl"}),
            edl=edl,
        )
    )


def _revision(clip_id: UUID, revision: int, edl: dict, label: str, actor: str) -> ClipRevisionRow:
    return ClipRevisionRow(
        clip_id=clip_id,
        revision=revision,
        edl=edl,
        label=label[:200],
        actor=actor,
        created_at=datetime.now(UTC),
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
        revision=row.revision,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
