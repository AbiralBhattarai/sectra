import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pytest

from src.adapters.output.lipsync.rhubarb_adapter import parse_rhubarb
from src.adapters.output.renderer.ass_builder import build_ass
from src.adapters.output.renderer.character_frames import (
    CharacterLayers,
    bob_margin,
    frame_source,
    write_character_video,
)
from src.adapters.output.renderer.ffmpeg_command import build_command
from src.domain.enums.emotion_enum import Emotion
from src.domain.models.character import CharacterTrack, Mood, MouthCue
from src.domain.models.edl import Edl
from src.domain.models.speech import TimeSpan
from src.domain.models.transcript import Word
from src.domain.services.render_planning import plan_render
from src.domain.services.story_text import split_sentences

CHARACTERS = Path(__file__).resolve().parents[3] / "assets" / "characters"
CUES = [
    MouthCue(start=0, end=1, shape="X"),
    MouthCue(start=1, end=1.5, shape="D"),
    MouthCue(start=1.5, end=3, shape="A"),
]


def story_edl(**character) -> Edl:
    edl = Edl.for_span(TimeSpan(start=0, end=3), [Word(text="Hello", start=0.2, end=0.6)])
    edl.character = CharacterTrack(name="guy", **character)
    edl.captions.y = 0.54
    return edl


def test_plan_carries_the_character_box_and_caption_anchor():
    plan = plan_render(story_edl(), 1080, 1920, CUES)
    assert (plan.character.x, plan.character.y) == (271, 1095)
    assert (plan.character.width, plan.character.height) == (538, 806)
    assert plan.character.cues == CUES
    assert plan.caption_y == 0.54
    assert plan_render(story_edl(enabled=False), 1080, 1920, CUES).character is None


def test_captions_anchor_their_bottom_edge_at_caption_y():
    ass = build_ass(plan_render(story_edl(), 1080, 1920, CUES))
    assert "{\\an2\\pos(540,1037)}" in ass  # 0.54 × 1920
    edl = story_edl()
    edl.captions.y = None
    assert "{\\an8\\pos(540,1190)}" in build_ass(plan_render(edl, 1080, 1920))


def test_command_overlays_the_character_under_the_captions():
    plan = plan_render(story_edl(), 1080, 1920, CUES)
    args = build_command(
        plan, Path("s.mp4"), None, Path("c.ass"), Path("fonts"), Path("o.mp4"), Path("c.mov")
    )
    assert args[args.index("c.mov") - 1] == "-i"
    graph = args[args.index("-filter_complex") + 1]
    overlay = f"[picture][1:v:0]overlay=271:{1095 - bob_margin(806)}:eof_action=pass"
    assert overlay in graph
    assert graph.index("overlay=") < graph.index("subtitles=")


@pytest.mark.skipif(not (CHARACTERS / "guy").is_dir(), reason="characters not generated")
def test_frames_follow_the_mouth_and_mood():
    edl = story_edl(scale=0.2)
    edl.character.moods = [Mood(start=2, end=3, emotion=Emotion.SHOCKED)]
    plan = plan_render(edl, 1080, 1920, CUES)
    box = plan.character
    layers = CharacterLayers(CHARACTERS / "guy", box.width, box.height)
    count, frame = frame_source(plan, layers)
    assert count == 90  # 3 s at 30 fps
    size = box.width * (box.height + 2 * bob_margin(box.height)) * 4
    rest, talking, shocked = (np.frombuffer(frame(i), np.uint8) for i in (15, 36, 75))
    assert len(rest) == size
    assert not np.array_equal(rest, talking)  # mouth D vs X
    assert not np.array_equal(talking, shocked)
    assert rest.reshape(-1, 4)[:, 3].max() == 255  # opaque where the figure is


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not (CHARACTERS / "guy").is_dir(), reason="needs ffmpeg"
)
async def test_character_video_is_written(tmp_path):
    edl = story_edl(scale=0.15)
    edl.ranges = [TimeSpan(start=0, end=1)]
    plan = plan_render(edl, 1080, 1920, CUES)
    with ThreadPoolExecutor(2) as executor:
        await write_character_video(plan, CHARACTERS, tmp_path / "c.mov", executor)
    assert (tmp_path / "c.mov").stat().st_size > 1000


def test_rhubarb_output_is_parsed():
    output = (
        '{"metadata": {}, "mouthCues": [{"start": 0.0, "end": 0.27, "value": "X"},'
        '{"start": 0.27, "end": 0.35, "value": "D"}, {"start": 0.35, "end": 0.35, "value": "B"}]}'
    )
    assert [(c.start, c.end, c.shape) for c in parse_rhubarb(output)] == [
        (0.0, 0.27, "X"),
        (0.27, 0.35, "D"),
    ]


KOKORO = Path(os.getenv("TTS_MODEL_PATH", "models/kokoro-v1.0.int8.onnx"))
VOICES = Path(os.getenv("TTS_VOICES_PATH", "models/voices-v1.0.bin"))


@pytest.mark.skipif(not (KOKORO.is_file() and VOICES.is_file()), reason="run `make models`")
async def test_kokoro_narrates_sentences_into_one_wav(tmp_path):
    import asyncio
    import wave

    from src.adapters.output.tts.kokoro_onnx_adapter import KokoroOnnxAdapter

    progress = []

    async def report(fraction):
        progress.append(fraction)

    with ThreadPoolExecutor(2) as executor:
        tts = KokoroOnnxAdapter(KOKORO, VOICES, asyncio.Semaphore(1), executor)
        seconds = await tts.narrate(
            split_sentences("Hello there. This is a test!"), "am_michael", 1.0, 0.25,
            tmp_path / "n.wav", report,
        )  # fmt: skip
    with wave.open(str(tmp_path / "n.wav")) as reader:
        assert reader.getframerate() == 24_000 and reader.getnchannels() == 1
        assert reader.getnframes() / 24_000 == pytest.approx(seconds)
    assert 1.5 < seconds < 6
    assert progress == [0.5, 1.0]
