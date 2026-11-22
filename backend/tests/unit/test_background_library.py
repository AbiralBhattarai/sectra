from concurrent.futures import ThreadPoolExecutor

import pytest

from src.adapters.output.storage.local_fs_storage_adapter import LocalFsStorageAdapter
from src.application.services.background_library_service import BackgroundLibraryService
from src.domain.enums.job_status_enum import JobStatus
from src.domain.enums.job_type_enum import JobType
from src.domain.exceptions import AppValidationException, NotFoundException
from src.domain.models.media import MediaInfo
from src.ports.output.downloader_port import DownloadResult
from tests.unit.fakes import Fakes


class FakeDownloader:
    async def download(self, url, dest_dir, on_progress):
        path = dest_dir / "raw.webm"
        path.write_bytes(b"downloaded")
        await on_progress(1.0)
        return DownloadResult(path=path, title="Minecraft Parkour 4K!", duration=600)


class FakeMedia:
    def __init__(self):
        self.encoded = []

    async def probe(self, path):
        return MediaInfo(
            duration=600, width=3840, height=2160, video_codec="vp9",
            pixel_format="yuv420p", audio_codec="opus",
        )  # fmt: skip

    async def make_background(self, src, dst, duration, on_progress):
        self.encoded.append((src.read_bytes(), duration))
        dst.write_bytes(b"encoded")


async def chunks(*parts):
    for part in parts:
        yield part


@pytest.fixture
def setup(tmp_path):
    executor = ThreadPoolExecutor(2)
    fakes = Fakes()
    storage = LocalFsStorageAdapter(tmp_path, executor)
    media = FakeMedia()
    service = BackgroundLibraryService(
        storage, fakes.jobs, fakes.scheduler, FakeDownloader(), media
    )
    yield fakes, storage, media, service
    executor.shutdown()


async def noop(fraction):
    pass


async def test_url_is_downloaded_encoded_and_listed(setup):
    fakes, storage, media, service = setup
    job = await service.add_from_url("https://youtu.be/x", "Minecraft")
    assert job.type is JobType.BACKGROUND and job.payload["category"] == "minecraft"

    await service(fakes.jobs.jobs[job.id], noop)

    assert media.encoded == [(b"downloaded", 600)]
    [(category, file)] = storage.list_backgrounds()
    assert category == "minecraft" and file.endswith("-Minecraft-Parkour-4K.mp4")
    ready, pending = await service.list()
    assert ready[0].ref == f"minecraft/{file}" and ready[0].name == "Minecraft Parkour 4K"
    assert [p.status for p in pending] == [JobStatus.QUEUED]  # the fake never ran the job
    # The scratch download is gone.
    assert not (storage.background_incoming_dir(job.id) / "raw.webm").exists()


async def test_upload_is_encoded_from_its_scratch_copy(setup):
    fakes, storage, media, service = setup
    job = await service.add_upload("subway run.mp4", "subway-surfers", chunks(b"up", b"load"))
    await service(fakes.jobs.jobs[job.id], noop)
    assert media.encoded == [(b"upload", 600)]
    [(category, file)] = storage.list_backgrounds()
    assert category == "subway-surfers" and file.endswith("-subway-run.mp4")


async def test_bad_category_and_file_type_are_rejected(setup):
    _, _, _, service = setup
    with pytest.raises(AppValidationException, match="Category"):
        await service.add_from_url("https://x.y", "../etc")
    with pytest.raises(AppValidationException, match="Unsupported"):
        await service.add_upload("notes.txt", "minecraft", chunks(b""))


async def test_delete_removes_the_clip_and_unknown_names_are_404(setup):
    _, storage, _, service = setup
    storage.background_path("roblox", "0123abcd-obby.mp4").write_bytes(b"x")
    await service.delete("roblox", "0123abcd-obby.mp4")
    assert storage.list_backgrounds() == []
    with pytest.raises(NotFoundException):
        await service.path("roblox", "../../secret.mp4")


async def test_a_failed_upload_keeps_its_file_so_retry_works(setup):
    fakes, storage, media, service = setup
    job = await service.add_upload("run.mp4", "subway", chunks(b"clip"))

    async def broken(src, dst, duration, on_progress):
        raise RuntimeError("encoder crashed")

    media.make_background = broken
    with pytest.raises(RuntimeError):
        await service(fakes.jobs.jobs[job.id], noop)
    assert storage.list_backgrounds() == []

    del media.make_background  # back to the working fake
    await service(fakes.jobs.jobs[job.id], noop)
    assert len(storage.list_backgrounds()) == 1
