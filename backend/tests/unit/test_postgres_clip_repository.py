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
