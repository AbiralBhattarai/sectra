"""VAD and transcription stages with fake engines."""

import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest

from src.adapters.output.storage.local_fs_storage_adapter import LocalFsStorageAdapter
from src.application.services.speech_detection_service import SpeechDetectionService
from src.application.services.transcription_service import TranscriptionService
from src.domain.enums.job_type_enum import JobType
from src.domain.enums.video_file_enum import VideoFile
from src.domain.exceptions import TranscriptionException
from src.domain.models.job import Job
from src.domain.models.speech import SpeechMap, TimeSpan
from src.domain.models.transcript import Segment, Transcript, Word
from src.domain.models.video import Video
from src.ports.output.vad_port import FrameProbabilities
from tests.unit.fakes import InMemoryVideoRepository


class FakeVAD:
    def __init__(self, probabilities):
        self.probabilities = probabilities

    async def frame_probabilities(self, wav, on_progress):
        await on_progress(1.0)
        return FrameProbabilities(frame_seconds=0.5, probabilities=self.probabilities)


class FakeSTT:
    """Says the chunk's start time; records peak concurrency."""

    def __init__(self, fail_at: float | None = None):
        self.fail_at = fail_at
        self.in_flight = self.peak = 0

    async def transcribe(self, wav, span, language):
        self.in_flight += 1
        self.peak = max(self.peak, self.in_flight)
        await asyncio.sleep(0.01)
        self.in_flight -= 1
        if span.start == self.fail_at:
            raise TranscriptionException("engine fell over")
        word = Word(text=f"t{span.start:g}", start=0.0, end=0.5)
        return Transcript(
            language="en", segments=[Segment(id=0, start=0, end=0.5, text=word.text, words=[word])]
        )


@pytest.fixture
def storage(tmp_path):
    with ThreadPoolExecutor(2) as executor:
        yield LocalFsStorageAdapter(tmp_path, executor)


@pytest.fixture
async def video(storage):
    videos = InMemoryVideoRepository()
    video = Video(title="talk", duration=100.0)
    await videos.add(video)
    storage.video_dir(video.id)
    return videos, video


async def test_vad_stage_writes_speech_map(storage, video):
    videos, v = video
    service = SpeechDetectionService(
        videos=videos, storage=storage, vad=FakeVAD([0, 0.9, 0.9, 0, 0, 0])
    )
    progress = []

    async def report(fraction):
        progress.append(fraction)

    await service(Job(type=JobType.VAD, video_id=v.id), report)

    speech = SpeechMap.model_validate_json(await storage.read_text(v.id, VideoFile.SPEECH))
    assert speech.duration == 100.0
    assert [(seg.start, seg.end) for seg in speech.segments] == [(0.5, 1.5)]
    assert progress == [1.0]


async def write_speech(storage, video_id, segments):
    speech = SpeechMap(duration=100.0, segments=[TimeSpan(start=a, end=b) for a, b in segments])
    await storage.write_text(video_id, VideoFile.SPEECH, speech.model_dump_json())


async def test_transcription_stitches_chunks_in_time_order(storage, video):
    videos, v = video
    await write_speech(storage, v.id, [(10, 12), (40, 42), (70, 72)])
    stt = FakeSTT()
    progress = []

    async def report(fraction):
        progress.append(fraction)

    await TranscriptionService(videos, storage, stt, language=None)(
        Job(type=JobType.TRANSCRIBE, video_id=v.id), report
    )

    transcript = Transcript.model_validate_json(await storage.read_text(v.id, VideoFile.TRANSCRIPT))
    # Each chunk's first word moves from the padded chunk start to the VAD onset.
    assert [s.words[0].start for s in transcript.segments] == [10.0, 40.0, 70.0]
    assert [s.id for s in transcript.segments] == [0, 1, 2]
    assert stt.peak == 3  # all chunks were in flight together
    assert sorted(progress) == pytest.approx([1 / 3, 2 / 3, 1.0])


async def test_no_speech_gives_empty_transcript(storage, video):
    videos, v = video
    await write_speech(storage, v.id, [])

    async def report(_):
        raise AssertionError("no chunks, no progress")

    await TranscriptionService(videos, storage, FakeSTT(), None)(
        Job(type=JobType.TRANSCRIBE, video_id=v.id), report
    )

    transcript = Transcript.model_validate_json(await storage.read_text(v.id, VideoFile.TRANSCRIPT))
    assert transcript.segments == []


async def test_failing_chunk_fails_the_stage_with_its_own_error(storage, video):
    videos, v = video
    await write_speech(storage, v.id, [(10, 12), (40, 42)])

    async def report(_):
        pass

    with pytest.raises(TranscriptionException, match="engine fell over"):
        await TranscriptionService(videos, storage, FakeSTT(fail_at=39.8), None)(
            Job(type=JobType.TRANSCRIBE, video_id=v.id), report
        )
    assert not storage.path(v.id, VideoFile.TRANSCRIPT).exists()
