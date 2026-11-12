from src.adapters.output.persistence import postgres_clip_repository
from src.adapters.output.persistence.postgres_clip_repository import PostgresClipRepository
from src.adapters.output.persistence.postgres_video_repository import PostgresVideoRepository
from src.domain.models.clip import Clip
from src.domain.models.edl import Edl
from src.domain.models.speech import TimeSpan
from src.domain.models.transcript import Word
from src.domain.models.video import Video


def make_clip(video, start, score):
    span = TimeSpan(start=start, end=start + 20)
    words = [Word(text="hi", start=start + 1, end=start + 1.5)]
    return Clip(
        video_id=video.id,
        title=f"clip at {start}",
        hook="h",
        score=score,
        reason="r",
        start=span.start,
        end=span.end,
        edl=Edl.for_span(span, words),
    )


async def test_replace_list_get_and_cascade(pg_sessionmaker):
    videos = PostgresVideoRepository(pg_sessionmaker)
    clips = PostgresClipRepository(pg_sessionmaker)
    video = Video(title="talk")
    await videos.add(video)

    await clips.replace_for_video(video.id, [make_clip(video, 0, 50)])
    newer = [make_clip(video, 10, 40), make_clip(video, 50, 90)]
    await clips.replace_for_video(video.id, newer)

    listed = await clips.list_for_video(video.id)
    assert [c.score for c in listed] == [90, 40]
    assert await clips.get(newer[0].id) == newer[0]

    await videos.delete(video.id)
    assert await clips.list_for_video(video.id) == []


async def test_edits_are_revisions_with_a_redo_branch(pg_sessionmaker, monkeypatch):
    videos = PostgresVideoRepository(pg_sessionmaker)
    clips = PostgresClipRepository(pg_sessionmaker)
    video = Video(title="talk")
    await videos.add(video)
    clip = make_clip(video, 0, 50)
    await clips.replace_for_video(video.id, [clip])
    original = clip.edl

    def edited(clip, end):
        clip.edl = clip.edl.model_copy(
            update={"segments": [clip.edl.segments[0].model_copy(update={"end": end})]}
        )
        return clip

    assert await clips.commit_edit(edited(clip, 15), 0, "trim", "editor")
    assert clip.revision == 1
    assert await clips.revision_edl(clip.id, 0) == original  # recorded on the first edit
    assert not await clips.commit_edit(edited(await clips.get(clip.id), 12), 0, "stale", "mcp")

    # Undo, then a new edit replaces the redo branch.
    back = await clips.get(clip.id)
    back.edl, back.revision = original, 0
    assert await clips.move_to_revision(back, 1)
    assert (await clips.get(clip.id)).edl == original
    assert await clips.commit_edit(edited(await clips.get(clip.id), 10), 0, "trim again", "mcp")
    history = await clips.history(clip.id)
    assert [(h.revision, h.label, h.actor) for h in history] == [
        (0, "Original", "analysis"),
        (1, "trim again", "mcp"),
    ]

    # Only the most recent HISTORY_LIMIT revisions are kept.
    monkeypatch.setattr(postgres_clip_repository, "HISTORY_LIMIT", 2)
    current = await clips.get(clip.id)
    assert await clips.commit_edit(edited(current, 9), 1, "trim", "editor")
    assert [h.revision for h in await clips.history(clip.id)] == [1, 2]
