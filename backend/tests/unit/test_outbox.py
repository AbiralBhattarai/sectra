import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from src.adapters.output.storage.local_fs_storage_adapter import LocalFsStorageAdapter
from src.application.services.clip_export_service import ClipExportService
from src.domain.enums.job_type_enum import JobType
from src.domain.enums.video_file_enum import VideoFile
from src.domain.models.video import Video
from src.domain.services.outbox_naming import (
    MAX_STEM,
    folder_name,
    outbox_stem,
    post_description,
    unique_stem,
)
from tests.unit.fakes import Fakes
from tests.unit.test_highlight_analysis_service import InMemoryClipRepository
from tests.unit.test_postgres_clip_repository import make_clip


def test_stem_is_rank_and_caption_made_windows_safe():
    assert outbox_stem(3, 'Wait: "what?" <no> way/ok #fyp\n#viral') == (
        "03 Wait what no way ok #fyp #viral"
    )
    assert outbox_stem(12, "😂 he said WHAT #podcast") == "12 😂 he said WHAT #podcast"
    assert outbox_stem(1, "   ", fallback="The title") == "01 The title"
    assert outbox_stem(1, "trailing dots...") == "01 trailing dots"


def test_long_caption_is_cut_at_a_word():
    stem = outbox_stem(1, "word " * 100)
    assert len(stem) <= MAX_STEM and stem.endswith("word")


def test_unique_stem_and_folder():
    assert unique_stem("01 a", set()) == "01 a"
    assert unique_stem("01 a", {"01 a", "01 a (2)"}) == "01 a (3)"
    assert folder_name('My "Big" Stream: part 2/3') == "My Big Stream part 2 3"


@pytest.fixture
def storage(tmp_path):
    with ThreadPoolExecutor(2) as executor:
        yield LocalFsStorageAdapter(tmp_path / "data", executor, outbox_dir=tmp_path / "outbox")


class FakeRenderer:
    async def render(self, plan, source, music, output, subtitles, on_progress):
        output.write_bytes(b"mp4")
        subtitles.write_text("srt")


async def test_outbox_export_copies_the_video_and_writes_its_sidecar(storage, tmp_path):
    fakes = Fakes()
    video = Video(title="Big: Stream", duration=200, width=1920, height=1080)
    await fakes.videos.add(video)
    storage.video_dir(video.id)
    storage.path(video.id, VideoFile.SOURCE).write_bytes(b"source")
    clip = make_clip(video, start=50, score=88).model_copy(
        update={"caption": "He did WHAT? #podcast #fyp"}
    )
    clips = InMemoryClipRepository()
    await clips.replace_for_video(video.id, [clip])
    service = ClipExportService(
        clips=clips,
        videos=fakes.videos,
        jobs=fakes.jobs,
        storage=storage,
        scheduler=fakes.scheduler,
        renderer=FakeRenderer(),
    )

    job = await service.request_export(clip.id, outbox_rank=4)
    assert job.type is JobType.EXPORT and job.payload["outbox_rank"] == 4

    async def progress(_):
        pass

    await service(job, progress)
    await service(job.model_copy(update={"id": uuid4()}), progress)

    folder = tmp_path / "outbox" / f"Big Stream [{str(video.id)[:8]}]"
    assert sorted(p.name for p in folder.iterdir()) == [
        "04 He did WHAT #podcast #fyp (2).json",
        "04 He did WHAT #podcast #fyp (2).mp4",
        "04 He did WHAT #podcast #fyp.json",
        "04 He did WHAT #podcast #fyp.mp4",
    ]
    assert (folder / "04 He did WHAT #podcast #fyp.mp4").read_bytes() == b"mp4"
    sidecar = json.loads((folder / "04 He did WHAT #podcast #fyp.json").read_text("utf-8"))
    assert sidecar["caption"] == "He did WHAT? #podcast #fyp"  # exact, "?" included
    assert (sidecar["rank"], sidecar["score"], sidecar["posted"]) == (4, 88, {})
    assert sidecar["clip_id"] == str(clip.id)


async def test_plain_export_leaves_the_outbox_alone(storage, tmp_path):
    fakes = Fakes()
    video = Video(title="t", duration=200, width=1920, height=1080)
    await fakes.videos.add(video)
    clip = make_clip(video, start=50, score=88)
    clips = InMemoryClipRepository()
    await clips.replace_for_video(video.id, [clip])
    service = ClipExportService(
        clips=clips,
        videos=fakes.videos,
        jobs=fakes.jobs,
        storage=storage,
        scheduler=fakes.scheduler,
        renderer=FakeRenderer(),
    )
    job = await service.request_export(clip.id)

    async def progress(_):
        pass

    await service(job, progress)
    assert "outbox_rank" not in job.payload
    assert not (tmp_path / "outbox").exists()


async def test_post_button_marks_the_sidecar_and_reports_the_poster_progress(storage, tmp_path):
    from src.domain.enums.job_status_enum import JobStatus

    fakes = Fakes()
    video = Video(title="Show", duration=200, width=1920, height=1080)
    await fakes.videos.add(video)
    storage.video_dir(video.id)
    storage.path(video.id, VideoFile.SOURCE).write_bytes(b"source")
    clip = make_clip(video, start=50, score=88).model_copy(
        update={"title": "He said WHAT", "caption": "Hook #fyp"}
    )
    clips = InMemoryClipRepository()
    await clips.replace_for_video(video.id, [clip])
    service = ClipExportService(
        clips=clips,
        videos=fakes.videos,
        jobs=fakes.jobs,
        storage=storage,
        scheduler=fakes.scheduler,
        renderer=FakeRenderer(),
        post_platforms=("youtube", "x"),
    )
    assert await service.post_status(clip.id) is None

    job = await service.request_post(clip.id)

    async def progress(_):
        pass

    await service(job, progress)
    job.status = JobStatus.SUCCEEDED
    await fakes.jobs.save(job)
    [sidecar_path] = (tmp_path / "outbox").glob("*/*.json")
    sidecar = json.loads(sidecar_path.read_text("utf-8"))
    assert sidecar["post_now"] is True
    assert sidecar["description"] == "He said WHAT"  # the title, as the description
    assert sidecar["platforms"] == ["youtube", "x"]
    assert sidecar_path.name.startswith("00 ")

    sidecar["posted"]["x"] = {"at": "2026-11-21T10:00:00+00:00", "url": None}
    sidecar_path.write_text(json.dumps(sidecar), "utf-8")
    found_job, found = await service.post_status(clip.id)
    assert found_job.id == job.id and found["posted"] == sidecar["posted"]

    # Posting again with the user's own text: it follows the title and is kept on the clip.
    again = await service.request_post(clip.id, "  #lacy  ")
    assert again.payload["description"] == "He said WHAT #lacy"
    assert (await clips.get(clip.id)).post_caption == "#lacy"
    third = await service.request_post(clip.id)  # left out: the saved text is used
    assert third.payload["description"] == "He said WHAT #lacy"


def test_post_description_is_the_title_then_the_users_text():
    title = "Betrayal and Confrontation"
    assert post_description(title, "#lacy") == "Betrayal and Confrontation #lacy"
    assert post_description(title, "  ") == title
    assert post_description(" Title ", " credit: @lacy\n#fyp ") == "Title credit: @lacy\n#fyp"
    assert post_description("", "#lacy") == "#lacy"


async def test_deleting_a_video_removes_its_outbox_folder_only(storage, tmp_path):
    video_id, other_id = uuid4(), uuid4()
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"mp4")
    await storage.write_outbox(video_id, "Gone", 1, "bye", clip, {"video_id": str(video_id)})
    await storage.write_outbox(other_id, "Kept", 1, "hi", clip, {"video_id": str(other_id)})
    # Same id prefix, different video: must survive.
    twin = tmp_path / "outbox" / f"Twin [{str(video_id)[:8]}]"
    twin.mkdir()
    (twin / "01 x.json").write_text(json.dumps({"video_id": str(other_id)}), encoding="utf-8")
    storage.path(video_id, VideoFile.SOURCE).parent.mkdir(parents=True, exist_ok=True)

    await storage.delete_video(video_id)

    left = sorted(p.name for p in (tmp_path / "outbox").iterdir())
    assert left == [f"Kept [{str(other_id)[:8]}]", f"Twin [{str(video_id)[:8]}]"]
    assert not storage.path(video_id, VideoFile.SOURCE).parent.exists()


async def test_leftovers_are_folders_of_videos_that_no_longer_exist(storage, tmp_path):
    kept, gone = uuid4(), uuid4()
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"mp4")
    for video_id in (kept, gone):
        storage.path(video_id, VideoFile.SOURCE).parent.mkdir(parents=True, exist_ok=True)
        await storage.write_outbox(video_id, "V", 1, "c", clip, {"video_id": str(video_id)})
    (tmp_path / "data" / "videos" / "not-a-video").mkdir()

    found = storage.leftovers({str(kept)}, min_age_seconds=0)

    assert sorted(p.name for p in found) == sorted([str(gone), f"V [{str(gone)[:8]}]"])
    assert storage.leftovers({str(kept)}, min_age_seconds=3600) == []  # too recent
