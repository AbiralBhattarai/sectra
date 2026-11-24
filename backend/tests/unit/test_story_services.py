import random
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from src.adapters.output.storage.local_fs_storage_adapter import LocalFsStorageAdapter
from src.application.prompts.story_prompt import META_SCHEMA, MOODS_SCHEMA
from src.application.services.story_clip_service import AnalysisRouter, StoryClipService
from src.application.services.story_composition_service import StoryCompositionService
from src.application.services.story_narration_service import StoryNarrationService
from src.application.services.story_service import StoryService
from src.domain.enums.emotion_enum import Emotion
from src.domain.enums.job_type_enum import JobType
from src.domain.enums.video_file_enum import VideoFile
from src.domain.enums.video_kind_enum import VideoKind
from src.domain.exceptions import AppValidationException, LLMException
from src.domain.models.character import LipSync, MouthCue
from src.domain.models.job import Job
from src.domain.models.media import MediaInfo
from src.domain.models.story import StorySpec
from src.domain.models.video import Video
from tests.unit.fakes import Fakes
from tests.unit.test_highlight_analysis_service import InMemoryClipRepository
from tests.unit.transcript_builders import seg, transcript

STORY = (
    "So this happened last week. My sister borrowed my car without asking.\n\n"
    "She returned it with an empty tank. I was furious."
)


class FakeTTS:
    def __init__(self, seconds: float = 12.5):
        self.seconds = seconds
        self.calls = []

    async def narrate(self, sentences, voice, speed, pause_seconds, dst, on_progress):
        self.calls.append((sentences, voice, speed, pause_seconds))
        dst.write_bytes(b"RIFF")
        await on_progress(1.0)
        return self.seconds


class FakeLipSync:
    def __init__(self):
        self.calls = []

    async def mouth_cues(self, wav, text):
        self.calls.append((wav, text))
        return [MouthCue(start=0, end=0.4, shape="X"), MouthCue(start=0.4, end=0.6, shape="D")]


class StoryLLM:
    """Rewrites by uppercasing (same length), or replays scripted answers."""

    def __init__(self, text_answers=None, json_answers=None):
        self.text_answers = list(text_answers or [])
        self.json_answers = list(json_answers or [])
        self.text_calls, self.json_calls = [], []

    async def complete_text(self, system, user):
        self.text_calls.append(user)
        if self.text_answers:
            answer = self.text_answers.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer
        return user.split("Passage:\n", 1)[1].upper()

    async def complete_json(self, system, user, schema):
        self.json_calls.append((schema, user))
        answer = self.json_answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


class FakeMedia:
    def __init__(self, background_seconds: float = 600):
        self.background_seconds = background_seconds
        self.composed = []

    async def probe(self, path: Path) -> MediaInfo:
        if path.name.startswith("source"):
            return MediaInfo(
                duration=12.5, width=1080, height=1920, video_codec="h264",
                pixel_format="yuv420p", audio_codec="aac",
            )  # fmt: skip
        return MediaInfo(
            duration=self.background_seconds, width=1920, height=1080, video_codec="h264",
            pixel_format="yuv420p", audio_codec=None,
        )  # fmt: skip

    async def compose_story(self, narration, dst, duration, background, offset, on_progress):
        self.composed.append((narration, duration, background, offset))
        dst.write_bytes(b"mp4")


@pytest.fixture
def storage(tmp_path):
    executor = ThreadPoolExecutor(2)
    yield LocalFsStorageAdapter(tmp_path / "data", executor, characters_dir=tmp_path / "chars")
    executor.shutdown()


@pytest.fixture
def fakes():
    return Fakes()


async def add_story(fakes, **spec) -> Video:
    video = Video(title="untitled", kind=VideoKind.STORY, story=StorySpec(text=STORY, **spec))
    await fakes.videos.add(video)
    return video


async def noop_report(fraction):
    pass


# ---------------------------------------------------------------- NARRATE


async def test_narrate_without_polish_speaks_the_cleaned_text(fakes, storage):
    video = await add_story(fakes, voice="am_michael", speed=1.1)
    tts, lipsync, llm = FakeTTS(), FakeLipSync(), StoryLLM()
    service = StoryNarrationService(fakes.videos, storage, tts, lipsync, llm, pause_seconds=0.3)

    await service(Job(type=JobType.NARRATE, video_id=video.id), noop_report)

    [(sentences, voice, speed, pause)] = tts.calls
    assert sentences[0] == "So this happened last week." and sentences[-1] == "I was furious."
    assert (voice, speed, pause) == ("am_michael", 1.1, 0.3)
    assert llm.text_calls == [] and llm.json_calls == []
    stored = fakes.videos.videos[video.id]
    assert stored.title == "So this happened last week."
    assert stored.duration == 12.5
    assert stored.story.caption == "So this happened last week. #storytime #fyp"
    cues = LipSync.model_validate_json(await storage.read_text(video.id, VideoFile.LIPSYNC)).cues
    assert [c.shape for c in cues] == ["X", "D"]


async def test_polish_rewrites_chunks_and_asks_for_title_and_caption(fakes, storage):
    video = await add_story(fakes, polish=True)
    llm = StoryLLM(json_answers=[{"title": "My sister's road trip", "caption": "Oof #storytime"}])
    service = StoryNarrationService(fakes.videos, storage, FakeTTS(), FakeLipSync(), llm)

    await service(Job(type=JobType.NARRATE, video_id=video.id), noop_report)

    assert len(llm.text_calls) == 1 and "gripping hook" in llm.text_calls[0]
    assert llm.json_calls[0][0] is META_SCHEMA
    stored = fakes.videos.videos[video.id]
    assert stored.title == "My sister's road trip"
    assert stored.story.caption == "Oof #storytime"
    assert stored.story.narration.startswith("SO THIS HAPPENED")


async def test_polish_falls_back_to_the_original_when_the_llm_misbehaves(fakes, storage):
    video = await add_story(fakes, polish=True, title="Car drama")
    llm = StoryLLM(
        text_answers=["Too short."],  # a summary: rejected
        json_answers=[LLMException("down"), LLMException("still down")],
    )
    service = StoryNarrationService(fakes.videos, storage, FakeTTS(), FakeLipSync(), llm)

    await service(Job(type=JobType.NARRATE, video_id=video.id), noop_report)

    stored = fakes.videos.videos[video.id]
    assert stored.title == "Car drama"  # the user's title always wins
    assert stored.story.narration.startswith("So this happened")
    assert stored.story.caption == "Car drama #storytime #fyp"


async def test_no_character_means_no_lip_sync(fakes, storage):
    video = await add_story(fakes, character=None)
    lipsync = FakeLipSync()
    service = StoryNarrationService(fakes.videos, storage, FakeTTS(), lipsync, StoryLLM())
    await service(Job(type=JobType.NARRATE, video_id=video.id), noop_report)
    assert lipsync.calls == []


# ---------------------------------------------------------------- COMPOSE


async def narrated(fakes, storage, **spec) -> Video:
    video = await add_story(fakes, **spec)
    stored = fakes.videos.videos[video.id]
    stored.duration = 12.5
    storage.video_dir(video.id)
    storage.path(video.id, VideoFile.NARRATION).write_bytes(b"RIFF")
    return stored


async def test_compose_black_screen(fakes, storage):
    video = await narrated(fakes, storage)
    media = FakeMedia()
    await StoryCompositionService(fakes.videos, storage, media)(
        Job(type=JobType.COMPOSE, video_id=video.id), noop_report
    )
    [(_, duration, background, offset)] = media.composed
    assert (duration, background, offset) == (12.5, None, 0.0)
    assert storage.path(video.id, VideoFile.SOURCE).read_bytes() == b"mp4"
    stored = fakes.videos.videos[video.id]
    assert (stored.width, stored.height) == (1080, 1920)


async def test_compose_gameplay_picks_from_the_category_at_a_random_offset(fakes, storage):
    for category, file in (("minecraft", "0000000a-a.mp4"), ("subway", "0000000b-b.mp4")):
        storage.background_path(category, file).write_bytes(b"x")
    video = await narrated(fakes, storage, background_mode="gameplay", category="subway")
    media = FakeMedia(background_seconds=100)
    service = StoryCompositionService(fakes.videos, storage, media, rng=random.Random(1))
    await service(Job(type=JobType.COMPOSE, video_id=video.id), noop_report)

    [(_, _, background, offset)] = media.composed
    assert background.parent.name == "subway"
    assert 0 <= offset <= 100 - 12.5


async def test_compose_short_gameplay_loops_from_the_start(fakes, storage):
    storage.background_path("minecraft", "0000000a-a.mp4").write_bytes(b"x")
    video = await narrated(fakes, storage, background_mode="gameplay")
    media = FakeMedia(background_seconds=5)
    await StoryCompositionService(fakes.videos, storage, media)(
        Job(type=JobType.COMPOSE, video_id=video.id), noop_report
    )
    assert media.composed[0][3] == 0.0


async def test_compose_gameplay_with_an_empty_library_explains_itself(fakes, storage):
    video = await narrated(fakes, storage, background_mode="gameplay")
    with pytest.raises(AppValidationException, match="No gameplay clips"):
        await StoryCompositionService(fakes.videos, storage, FakeMedia())(
            Job(type=JobType.COMPOSE, video_id=video.id), noop_report
        )


# ---------------------------------------------------------------- ANALYZE (stories)


class RecordingExports:
    def __init__(self):
        self.requests = []

    async def request_export(self, clip_id, outbox_rank=None):
        self.requests.append((clip_id, outbox_rank))


async def transcribed(fakes, storage, duration, segments, **spec) -> Video:
    video = await add_story(fakes, **spec)
    stored = fakes.videos.videos[video.id]
    stored.title, stored.duration = "Sister stole my car", duration
    stored.story = stored.story.model_copy(update={"caption": "Wild #storytime"})
    storage.video_dir(video.id)
    await storage.write_text(video.id, VideoFile.TRANSCRIPT, transcript(segments).model_dump_json())
    return stored


async def test_short_story_is_one_clip_with_character_and_captions_above_it(fakes, storage):
    segments = [seg(0, 0.2, 4, "So this happened."), seg(1, 4.5, 9, "She left!")]
    video = await transcribed(fakes, storage, 9.5, segments)
    clips = InMemoryClipRepository()
    llm = StoryLLM(json_answers=[{"moods": [{"line": 1, "emotion": "shocked"}]}])
    exports = RecordingExports()
    service = StoryClipService(fakes.videos, storage, clips, llm, 170, exports)

    await service(Job(type=JobType.ANALYZE, video_id=video.id), noop_report)

    [clip] = clips.by_video[video.id]
    assert (clip.title, clip.caption, clip.start, clip.end) == (
        "Sister stole my car", "Wild #storytime", 0.0, 9.5,
    )  # fmt: skip
    edl = clip.edl
    assert edl.character.name == "guy"
    assert [(m.start, m.end, m.emotion) for m in edl.character.moods] == [(4.5, 9, Emotion.SHOCKED)]
    # Captions end just above the character's head.
    assert edl.captions.y == pytest.approx(0.78 - 0.21 - 0.03)
    assert [w.text for w in edl.captions.words] == ["So this happened.", "She left!"]
    assert edl.overlays[0].text == "Sister stole my car" and edl.overlays[0].end == 3.0
    assert llm.json_calls[0][0] is MOODS_SCHEMA
    assert exports.requests == [(clip.id, 1)]


async def test_long_story_becomes_numbered_parts_in_outbox_order(fakes, storage):
    segments = [seg(i, i * 10, i * 10 + 9.5) for i in range(30)]
    video = await transcribed(fakes, storage, 300, segments, character=None)
    clips = InMemoryClipRepository()
    exports = RecordingExports()
    service = StoryClipService(fakes.videos, storage, clips, StoryLLM(), 170, exports)

    await service(Job(type=JobType.ANALYZE, video_id=video.id), noop_report)

    parts = clips.by_video[video.id]
    assert [c.title for c in parts] == [
        "Sister stole my car · Part 1",
        "Sister stole my car · Part 2",
    ]
    assert parts[1].caption == "Part 2/2 — Wild #storytime"
    assert parts[1].edl.overlays[0].text == "Part 2"
    assert parts[0].edl.character is None and parts[0].edl.captions.y is None
    assert [rank for _, rank in exports.requests] == [1, 2]


async def test_bad_mood_answers_leave_the_narrator_neutral(fakes, storage):
    video = await transcribed(fakes, storage, 9.5, [seg(0, 0.2, 9, "Hi.")])
    llm = StoryLLM(json_answers=[{"moods": "nope"}, LLMException("down")])
    clips = InMemoryClipRepository()
    await StoryClipService(fakes.videos, storage, clips, llm, 170)(
        Job(type=JobType.ANALYZE, video_id=video.id), noop_report
    )
    assert clips.by_video[video.id][0].edl.character.moods == []


async def test_analysis_router_sends_stories_and_sources_their_own_way(fakes):
    story = await add_story(fakes)
    source = Video(title="podcast")
    await fakes.videos.add(source)
    seen = []

    async def clipping(job, report):
        seen.append(("clips", job.video_id))

    async def stories(job, report):
        seen.append(("story", job.video_id))

    router = AnalysisRouter(fakes.videos, clipping, stories)
    await router(Job(type=JobType.ANALYZE, video_id=story.id), noop_report)
    await router(Job(type=JobType.ANALYZE, video_id=source.id), noop_report)
    assert seen == [("story", story.id), ("clips", source.id)]


# ---------------------------------------------------------------- creating stories


async def test_create_story_queues_narration(fakes, storage):
    service = StoryService(fakes.videos, storage, fakes.scheduler)
    video = await service.create(StorySpec(text=STORY, voice="bf_emma", character="girl"))

    assert video.kind is VideoKind.STORY and video.title == "So this happened last week."
    [job] = fakes.queue.enqueued
    assert (job.type, job.video_id) == (JobType.NARRATE, video.id)


@pytest.mark.parametrize(
    ("spec", "message"),
    [
        ({"voice": "zz_nobody"}, "Unknown voice"),
        ({"character": "wizard"}, "Unknown character"),
        ({"background": "minecraft/0000000a-a.mp4"}, "takes no gameplay"),
        (
            {"background_mode": "gameplay", "background": "minecraft/0000000a-gone.mp4"},
            "not in the library",
        ),
        ({"text": "** ##"}, "no words"),
    ],
)
async def test_create_story_rejects_bad_input(fakes, storage, spec, message):
    service = StoryService(fakes.videos, storage, fakes.scheduler)
    with pytest.raises(AppValidationException, match=message):
        await service.create(StorySpec(**({"text": STORY} | spec)))
    assert fakes.queue.enqueued == []
