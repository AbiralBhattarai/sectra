from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from src.adapters.output.storage.local_fs_storage_adapter import LocalFsStorageAdapter
from src.application.services.video_library_service import VideoLibraryService
from src.domain.enums.job_type_enum import JobType
from src.domain.enums.video_file_enum import VideoFile
from src.domain.enums.video_status_enum import VideoStatus
from src.domain.exceptions import AppValidationException, NotFoundException
from src.domain.models.video import Video
from tests.unit.fakes import Fakes


@pytest.fixture
def fakes():
    return Fakes()


@pytest.fixture
def storage(tmp_path):
    with ThreadPoolExecutor(2) as executor:
        yield LocalFsStorageAdapter(tmp_path, executor)


@pytest.fixture
def library(fakes, storage):
    return VideoLibraryService(
        videos=fakes.videos, jobs=fakes.jobs, storage=storage, scheduler=fakes.scheduler
    )


async def chunks(*parts: bytes):
    for part in parts:
        yield part


async def test_add_from_url_queues_ingest(fakes, library):
    video = await library.add_from_url("https://youtu.be/abc")

    assert fakes.videos.videos[video.id].source_url == "https://youtu.be/abc"
    [job] = fakes.queue.enqueued
    assert (job.type, job.video_id) == (JobType.INGEST, video.id)


async def test_upload_is_stored_and_skips_to_normalize(fakes, library, storage):
    video = await library.add_upload("My Talk.MOV", chunks(b"abc", b"def"))

    assert video.title == "My Talk"
    raw = storage.raw_path(video.id)
    assert raw.name == "raw.mov"
    assert raw.read_bytes() == b"abcdef"
    [job] = fakes.queue.enqueued
    assert (job.type, job.video_id) == (JobType.NORMALIZE, video.id)


async def test_upload_rejects_unknown_extension(fakes, library):
    with pytest.raises(AppValidationException):
        await library.add_upload("notes.txt", chunks(b"x"))
    assert fakes.videos.videos == {}


async def test_failed_upload_leaves_nothing_behind(fakes, library, tmp_path):
    async def broken():
        yield b"abc"
        raise ConnectionError("client went away")

    with pytest.raises(ConnectionError):
        await library.add_upload("talk.mp4", broken())
    assert fakes.videos.videos == {}
    assert list((tmp_path / "videos").iterdir()) == []


async def test_list_pairs_videos_with_their_latest_job(library):
    first = await library.add_from_url("https://a.example/1")
    second = await library.add_upload("b.mp4", chunks(b"x"))

    listed = await library.list()

    assert [(v.id, j.type) for v, j in listed] == [
        (second.id, JobType.NORMALIZE),
        (first.id, JobType.INGEST),
    ]


async def test_delete_removes_video_and_files(fakes, library, storage):
    video = await library.add_upload("talk.mp4", chunks(b"x"))

    await library.delete(video.id)

    assert video.id not in fakes.videos.videos
    assert not (storage.path(video.id, VideoFile.SOURCE)).parent.exists()


async def test_media_path_requires_existing_file(library):
    video = await library.add_from_url("https://a.example/1")
    with pytest.raises(NotFoundException):
        await library.media_path(video.id, VideoFile.THUMBNAIL)
    with pytest.raises(NotFoundException):
        await library.media_path(uuid4(), VideoFile.THUMBNAIL)


async def test_find_clips_again_queues_analysis_for_a_transcribed_video(fakes, library, storage):
    video = Video(title="talk", status=VideoStatus.READY, duration=60)
    await fakes.videos.add(video)
    with pytest.raises(AppValidationException, match="no transcript"):
        await library.find_clips_again(video.id)

    storage.video_dir(video.id)
    storage.path(video.id, VideoFile.TRANSCRIPT).write_text("{}")
    job = await library.find_clips_again(video.id)

    assert (job.type, job.video_id) == (JobType.ANALYZE, video.id)
    assert fakes.videos.videos[video.id].status is VideoStatus.PROCESSING
    with pytest.raises(AppValidationException, match="still being processed"):
        await library.find_clips_again(video.id)
