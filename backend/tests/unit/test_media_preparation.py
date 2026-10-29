"""Normalize and prepare stages against real ffmpeg (no Docker services needed)."""

import asyncio
import json
import wave
from concurrent.futures import ThreadPoolExecutor

import pytest

from src.adapters.output.media.ffmpeg_media_adapter import FfmpegMediaAdapter
from src.adapters.output.storage.local_fs_storage_adapter import LocalFsStorageAdapter
from src.application.services.media_preparation_service import (
    PEAKS_PER_SECOND,
    MediaPreparationService,
)
from src.domain.enums.job_type_enum import JobType
from src.domain.enums.video_file_enum import VideoFile
from src.domain.exceptions import MediaProcessingException
from src.domain.models.job import Job
from src.domain.models.video import Video
from tests.unit.fakes import InMemoryVideoRepository
from tests.unit.media_samples import make_video


@pytest.fixture
def executor():
    with ThreadPoolExecutor(2) as executor:
        yield executor


@pytest.fixture
def media(executor):
    return FfmpegMediaAdapter(asyncio.Semaphore(2), executor)


@pytest.fixture
def storage(tmp_path, executor):
    return LocalFsStorageAdapter(tmp_path, executor)


@pytest.fixture
def videos():
    return InMemoryVideoRepository()


@pytest.fixture
def service(videos, storage, media):
    return MediaPreparationService(videos=videos, storage=storage, media=media)


async def add_raw(videos, storage, **sample) -> Video:
    video = Video(title="sample")
    await videos.add(video)
    make_video(storage.video_dir(video.id) / "raw.mp4", **sample)
    return video


async def ignore(_: float) -> None:
    pass


async def test_oversized_video_is_scaled_to_1080(service, videos, storage, media):
    video = await add_raw(videos, storage, width=1920, height=1440)
    reported = []

    async def report(fraction):
        reported.append(fraction)

    await service.normalize(Job(type=JobType.NORMALIZE, video_id=video.id), report)

    info = await media.probe(storage.path(video.id, VideoFile.SOURCE))
    assert (info.width, info.height, info.video_codec, info.audio_codec) == (
        1440,
        1080,
        "h264",
        "aac",
    )
    assert storage.raw_path(video.id) is None
    stored = videos.videos[video.id]
    assert (stored.width, stored.height) == (1440, 1080)
    assert stored.duration == pytest.approx(2.0, abs=0.1)
    assert reported and reported[-1] <= 1.0


async def test_portrait_video_is_limited_by_its_width(service, videos, storage, media):
    video = await add_raw(videos, storage, width=1440, height=2560)

    await service.normalize(Job(type=JobType.NORMALIZE, video_id=video.id), ignore)

    info = await media.probe(storage.path(video.id, VideoFile.SOURCE))
    assert (info.width, info.height) == (1080, 1920)


async def test_non_h264_video_is_reencoded_at_same_size(service, videos, storage, media):
    video = await add_raw(videos, storage, width=640, height=360, vcodec="mpeg4")

    await service.normalize(Job(type=JobType.NORMALIZE, video_id=video.id), ignore)

    info = await media.probe(storage.path(video.id, VideoFile.SOURCE))
    assert (info.width, info.height, info.video_codec) == (640, 360, "h264")


async def test_video_without_audio_is_rejected(service, videos, storage):
    video = await add_raw(videos, storage, width=640, height=360, audio=False)

    with pytest.raises(MediaProcessingException, match="no audio"):
        await service.normalize(Job(type=JobType.NORMALIZE, video_id=video.id), ignore)


async def test_prepare_writes_audio_peaks_and_thumbnail_but_no_proxy(
    service, videos, storage, media
):
    video = await add_raw(videos, storage, width=1920, height=1080, seconds=3)
    await service.normalize(Job(type=JobType.NORMALIZE, video_id=video.id), ignore)

    await service.prepare(Job(type=JobType.PREPARE, video_id=video.id), ignore)

    assert not (storage.video_dir(video.id) / "proxy.mp4").exists()
    with wave.open(str(storage.path(video.id, VideoFile.AUDIO))) as audio:
        assert (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) == (16000, 1, 2)
    peaks = json.loads(storage.path(video.id, VideoFile.PEAKS).read_text())
    assert peaks["per_second"] == PEAKS_PER_SECOND
    assert len(peaks["peaks"]) == pytest.approx(3 * PEAKS_PER_SECOND, abs=2)
    assert 0 < max(peaks["peaks"]) <= 1
    assert storage.path(video.id, VideoFile.THUMBNAIL).stat().st_size > 0
