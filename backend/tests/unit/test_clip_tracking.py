from concurrent.futures import ThreadPoolExecutor

import pytest

from src.adapters.output.storage.local_fs_storage_adapter import LocalFsStorageAdapter
from src.application.services.clip_tracking_service import ClipTrackingService
from src.domain.enums.job_status_enum import JobStatus
from src.domain.enums.job_type_enum import JobType
from src.domain.exceptions import MediaProcessingException, NotFoundException
from src.domain.models.face_track import FaceTrack
from src.domain.models.speech import TimeSpan
from src.domain.models.video import Video
from tests.unit.fakes import Fakes
from tests.unit.test_highlight_analysis_service import InMemoryClipRepository
from tests.unit.test_postgres_clip_repository import make_clip


class FakeTracker:
    def __init__(self, tracks):
        self.tracks = tracks
        self.calls = []

    async def track(self, source, audio, span, source_size, on_progress):
        self.calls.append((source.name, audio.name, span, source_size))
        await on_progress(1.0)
        return self.tracks


@pytest.fixture
def storage(tmp_path):
    with ThreadPoolExecutor(2) as executor:
        yield LocalFsStorageAdapter(tmp_path, executor)


@pytest.fixture
async def setup(storage):
    fakes = Fakes()
    video = Video(title="talk", duration=200, width=1920, height=1080)
    await fakes.videos.add(video)
    clip = make_clip(video, start=50, score=90)  # ranges 50-70
    clips = InMemoryClipRepository()
    await clips.replace_for_video(video.id, [clip])

    def service(tracks=()):
        return ClipTrackingService(
            clips=clips,
            videos=fakes.videos,
            jobs=fakes.jobs,
            storage=storage,
            scheduler=fakes.scheduler,
            tracker=FakeTracker(list(tracks)),
            min_shot_seconds=1,
        )

    return fakes, clip, service


async def test_request_queues_a_padded_span_and_reuses_a_covering_job(setup):
    fakes, clip, service = setup
    job = await service().request_tracking(clip.id)

    assert job.type is JobType.TRACK and job.clip_id == clip.id
    assert TimeSpan.model_validate(job.payload["span"]) == TimeSpan(start=48, end=72)
    assert [j.id for j in fakes.queue.enqueued] == [job.id]
    # Asking again (e.g. ticking twice, or reopening the clip) reuses it.
    assert (await service().request_tracking(clip.id)).id == job.id


async def test_failed_job_is_not_reused(setup):
    fakes, clip, service = setup
    job = await service().request_tracking(clip.id)
    failed = job.model_copy(update={"status": JobStatus.FAILED})
    await fakes.jobs.save(failed)
    assert (await service().request_tracking(clip.id)).id != job.id


async def test_stage_writes_shots_that_the_result_endpoint_reads(setup):
    fakes, clip, service = setup
    job = await service().request_tracking(clip.id)
    face = FaceTrack(id=3, first_frame=0, centres=[(0.3, 0.4)] * 50, scores=[1.0] * 50)
    worker = service([face])

    async def progress(_):
        pass

    await worker(job, progress)
    await fakes.jobs.save(job.model_copy(update={"status": JobStatus.SUCCEEDED}))
    result = await service().tracking_result(job.id)

    assert result.span == TimeSpan(start=48, end=72)
    assert [(s.start, s.face, s.x, s.y) for s in result.shots] == [(48, 0, 0.3, 0.4)]
    assert worker._tracker.calls == [
        ("source.mp4", "audio.wav", TimeSpan(start=48, end=72), (1920, 1080))
    ]


async def test_no_faces_fails_the_job(setup):
    _, clip, service = setup
    job = await service().request_tracking(clip.id)

    async def progress(_):
        pass

    with pytest.raises(MediaProcessingException, match="No faces"):
        await service([])(job, progress)


async def test_unfinished_result_is_not_found(setup):
    _, clip, service = setup
    job = await service().request_tracking(clip.id)
    with pytest.raises(NotFoundException):
        await service().tracking_result(job.id)
