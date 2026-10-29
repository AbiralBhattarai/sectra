import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from src.adapters.output.storage.local_fs_storage_adapter import LocalFsStorageAdapter
from src.application.prompts.highlight_prompt import (
    ENERGY_MARK,
    HIGHLIGHT_SCHEMA,
    RANK_SCHEMA,
    rank_prompt,
    user_prompt,
)
from src.application.services.highlight_analysis_service import HighlightAnalysisService
from src.domain.enums.job_type_enum import JobType
from src.domain.enums.video_file_enum import VideoFile
from src.domain.exceptions import InvalidLLMOutputException, LLMException
from src.domain.models.clip import Clip
from src.domain.models.job import Job
from src.domain.models.video import Video
from tests.unit.fakes import InMemoryVideoRepository
from tests.unit.transcript_builders import evenly, seg, transcript


class InMemoryClipRepository:
    def __init__(self):
        self.by_video: dict = {}

    async def replace_for_video(self, video_id, clips):
        self.by_video[video_id] = list(clips)

    async def list_for_video(self, video_id):
        return sorted(self.by_video.get(video_id, []), key=lambda c: -c.score)

    async def get(self, clip_id):
        return next((c for cs in self.by_video.values() for c in cs if c.id == clip_id), None)


class ScriptedLLM:
    """Answers each request from a queue; records (schema, system, user)."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    async def complete_json(self, system, user, schema):
        assert schema is HIGHLIGHT_SCHEMA or schema is RANK_SCHEMA
        self.calls.append((schema, system, user))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    def window_calls(self):
        return [c for c in self.calls if c[0] is HIGHLIGHT_SCHEMA]

    def rank_calls(self):
        return [c for c in self.calls if c[0] is RANK_SCHEMA]


def clip(start, end, rating=7, title="A moment"):
    return {
        "start_segment": start,
        "end_segment": end,
        "title": title,
        "hook": "hook",
        "reason": "why",
        "hook_strength": rating,
        "emotion": rating,
        "payoff": rating,
        "standalone": rating,
        "shareability": rating,
    }


@pytest.fixture
def storage(tmp_path):
    with ThreadPoolExecutor(2) as executor:
        yield LocalFsStorageAdapter(tmp_path, executor)


@pytest.fixture
async def setup(storage):
    videos = InMemoryVideoRepository()
    video = Video(title="talk", duration=200)
    await videos.add(video)
    storage.video_dir(video.id)
    return videos, video, InMemoryClipRepository()


async def write_transcript(storage, video, segments):
    await storage.write_text(video.id, VideoFile.TRANSCRIPT, transcript(segments).model_dump_json())


def service(videos, storage, clips, llm, window=300):
    return HighlightAnalysisService(
        videos=videos,
        storage=storage,
        clips=clips,
        llm=llm,
        min_seconds=15,
        max_seconds=60,
        max_count=10,
        window_seconds=window,
    )


async def ignore(_):
    pass


async def run(svc, video):
    await svc(Job(type=JobType.ANALYZE, video_id=video.id), ignore)


async def test_single_clip_is_scored_from_its_ratings_and_captioned(storage, setup):
    videos, video, clips = setup
    await write_transcript(storage, video, evenly(10))
    llm = ScriptedLLM({"clips": [clip(1, 2, rating=7, title="  Big idea  ")]})

    await run(service(videos, storage, clips, llm), video)

    [stored] = clips.by_video[video.id]
    assert isinstance(stored, Clip)
    assert (stored.title, stored.score, stored.start, stored.end) == ("Big idea", 70, 10.0, 30.0)
    assert [(r.start, r.end) for r in stored.edl.ranges] == [(10.0, 30.0)]
    assert [w.text for w in stored.edl.captions.words] == ["segment 1", "segment 2"]
    assert llm.rank_calls() == []  # nothing to rank against
    _, system, user = llm.window_calls()[0]
    assert "15-60 seconds" in system
    assert "[1] 00:10 segment 1" in user


async def test_ranking_pass_decides_the_order(storage, setup):
    videos, video, clips = setup
    await write_transcript(storage, video, evenly(20))
    llm = ScriptedLLM(
        {"clips": [clip(0, 2, 9, "A"), clip(6, 8, 6, "B"), clip(12, 14, 4, "C")]},
        {"ranking": [3, 2, 1]},  # the LLM prefers C, then B, then A
    )

    await run(service(videos, storage, clips, llm), video)

    stored = clips.by_video[video.id]
    # Rubric 90/60/40 blended half-and-half with rank 0/50/100.
    assert [(c.title, c.score) for c in stored] == [("C", 70), ("B", 55), ("A", 45)]
    _, _, ranked_prompt = llm.rank_calls()[0]
    assert (
        ranked_prompt.index('#1 "A"')
        < ranked_prompt.index('#2 "B"')
        < ranked_prompt.index('#3 "C"')
    )
    assert "segment 12 segment 13 segment 14" in ranked_prompt


async def test_unusable_ranking_falls_back_to_rubric_order(storage, setup):
    videos, video, clips = setup
    await write_transcript(storage, video, evenly(20))
    llm = ScriptedLLM(
        {"clips": [clip(12, 14, 4, "C"), clip(0, 2, 9, "A"), clip(6, 8, 6, "B")]},
        {"rank": "nope"},
        InvalidLLMOutputException("prose"),
    )

    await run(service(videos, storage, clips, llm), video)

    assert [(c.title, c.score) for c in clips.by_video[video.id]] == [
        ("A", 90),
        ("B", 60),
        ("C", 40),
    ]
    assert len(llm.rank_calls()) == 2


async def test_loud_segments_are_flagged_in_the_prompt(storage, setup):
    videos, video, clips = setup
    await write_transcript(storage, video, evenly(10))
    levels = [0.1] * 200
    levels[30:40] = [0.9] * 10  # segment 3 (30-40 s) is shouting; peaks at 1/s
    await storage.write_text(
        video.id, VideoFile.PEAKS, json.dumps({"per_second": 1, "peaks": levels})
    )
    llm = ScriptedLLM({"clips": []})

    await run(service(videos, storage, clips, llm), video)

    _, _, user = llm.window_calls()[0]
    assert f"[3] 00:30 {ENERGY_MARK} segment 3" in user
    assert "[4] 00:40 segment 4" in user


async def test_each_window_is_asked_once(storage, setup):
    videos, video, clips = setup
    await write_transcript(storage, video, evenly(30))  # 300 s
    llm = ScriptedLLM(*[{"clips": []}] * 10)

    await run(service(videos, storage, clips, llm, window=120), video)

    # 120 s windows overlapping by 60 s: 0-120, 60-180, 120-240, 180-300.
    assert len(llm.window_calls()) == 4
    assert clips.by_video[video.id] == []


async def test_malformed_answer_is_retried(storage, setup):
    videos, video, clips = setup
    await write_transcript(storage, video, evenly(10))
    llm = ScriptedLLM({"clips": [{"start_segment": "one"}]}, {"clips": [clip(0, 2)]})

    await run(service(videos, storage, clips, llm), video)

    assert len(llm.window_calls()) == 2
    assert len(clips.by_video[video.id]) == 1


async def test_llm_that_never_answers_properly_fails_the_stage(storage, setup):
    videos, video, clips = setup
    await write_transcript(storage, video, evenly(10))
    llm = ScriptedLLM(InvalidLLMOutputException("prose"), {"nope": 1})

    with pytest.raises(InvalidLLMOutputException, match="never returned usable JSON"):
        await run(service(videos, storage, clips, llm), video)
    assert video.id not in clips.by_video


async def test_provider_errors_fail_the_stage(storage, setup):
    videos, video, clips = setup
    await write_transcript(storage, video, evenly(10))
    llm = ScriptedLLM(LLMException("connection refused"))

    with pytest.raises(LLMException, match="connection refused"):
        await run(service(videos, storage, clips, llm), video)


async def test_silent_video_yields_no_clips_without_calling_the_llm(storage, setup):
    videos, video, clips = setup
    await write_transcript(storage, video, [])
    llm = ScriptedLLM()

    await run(service(videos, storage, clips, llm), video)

    assert clips.by_video[video.id] == []
    assert llm.calls == []


def test_user_prompt_lists_segments_with_ids_clock_and_energy():
    prompt = user_prompt([seg(7, 65.4, 70, "hello"), seg(8, 3725, 3730, "later")], loud={8})
    assert f"[7] 01:05 hello\n[8] 62:05 {ENERGY_MARK} later" in prompt


def test_rank_prompt_numbers_candidates_and_shortens_long_text():
    prompt = rank_prompt([("Hook", 31.6, "word " * 400), ("Other", 20, "short")])
    assert '#1 "Hook" (32s)' in prompt
    assert prompt.count("word") < 200 and "…" in prompt
    assert '#2 "Other" (20s)\nshort' in prompt


async def test_loudness_marker_never_reaches_titles_or_hooks(storage, setup):
    videos, video, clips = setup
    await write_transcript(storage, video, evenly(10))
    answer = clip(1, 2) | {"title": f"{ENERGY_MARK} Big moment", "hook": f"{ENERGY_MARK} Yes! Yes!"}
    llm = ScriptedLLM({"clips": [answer]})

    await run(service(videos, storage, clips, llm), video)

    [stored] = clips.by_video[video.id]
    assert (stored.title, stored.hook) == ("Big moment", "Yes! Yes!")
