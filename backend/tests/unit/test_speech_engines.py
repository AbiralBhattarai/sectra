"""Silero VAD and faster-whisper on real (synthesized) speech. Needs macOS `say`,
host ffmpeg, the Silero model (`make models`) and downloads Whisper `tiny` once."""

import asyncio
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from src.adapters.output.stt.faster_whisper_adapter import FasterWhisperAdapter
from src.adapters.output.vad.silero_onnx_adapter import SileroOnnxAdapter
from src.domain.models.speech import TimeSpan
from src.domain.services.speech_detection import speech_segments

MODEL = Path(__file__).parents[2] / "models" / "silero_vad.onnx"
SENTENCE = "The quick brown fox jumps over the lazy dog."

pytestmark = pytest.mark.skipif(
    not shutil.which("say") or not MODEL.exists(),
    reason="needs macOS `say` and the Silero model (make models)",
)


@pytest.fixture(scope="module")
def speech_wav(tmp_path_factory) -> Path:
    """2 s silence, the sentence, 3 s silence, the sentence again — 16 kHz mono."""
    tmp = tmp_path_factory.mktemp("speech")
    subprocess.run(["say", "-o", str(tmp / "s.aiff"), SENTENCE], check=True)
    wav = tmp / "audio.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(tmp / "s.aiff"),
         "-af", "adelay=2s:all=1,apad=pad_dur=3,aloop=loop=1:size=2e9", "-ac", "1", "-ar", "16000",
         "-c:a", "pcm_s16le", str(wav)],
        check=True,
    )  # fmt: skip
    return wav


@pytest.fixture(scope="module")
def executor():
    with ThreadPoolExecutor(2) as executor:
        yield executor


async def ignore(_):
    pass


async def test_silero_finds_both_sentences(speech_wav, executor):
    vad = SileroOnnxAdapter(MODEL, asyncio.Semaphore(1), executor)

    frames = await vad.frame_probabilities(speech_wav, ignore)
    segments = speech_segments(frames.probabilities, frames.frame_seconds, min_silence=0.5)

    assert len(segments) == 2
    first, second = segments
    assert 1.8 < first.start < 2.4  # speech begins after the 2 s of silence
    assert second.start - first.end > 2.5  # the 3 s gap is detected as silence


async def test_faster_whisper_transcribes_a_span_with_word_times(speech_wav, executor):
    stt = FasterWhisperAdapter("tiny", workers=1, semaphore=asyncio.Semaphore(1), executor=executor)

    transcript = await stt.transcribe(speech_wav, TimeSpan(start=1.5, end=6.0), language="en")

    words = [w for s in transcript.segments for w in s.words]
    text = " ".join(w.text.strip(" .").lower() for w in words)
    assert "quick brown fox" in text
    starts = [w.start for w in words]
    assert starts == sorted(starts)
    # Relative to the span: speech runs from ~0.5 s for about 2.5 s. (Whisper stamps
    # the first word from 0; merging fixes that using the VAD onset.)
    assert 2.5 < words[-1].end < 3.6
