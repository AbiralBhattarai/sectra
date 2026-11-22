import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID

from src.application.services.job_scheduler import JobScheduler
from src.application.services.pipeline_dispatcher import ProgressCallback
from src.domain.enums.job_status_enum import JobStatus
from src.domain.enums.job_type_enum import JobType
from src.domain.enums.video_file_enum import VideoFile
from src.domain.exceptions import MediaProcessingException, NotFoundException
from src.domain.models.edl import Tracking
from src.domain.models.face_track import FRAME_RATE
from src.domain.models.job import Job
from src.domain.models.speech import TimeSpan
from src.domain.services.edl_rules import edl_bounds
from src.domain.services.speaker_shots import build_shots
from src.ports.input.clip_export_port import ClipExportPort
from src.ports.output.clip_repository import ClipRepository
from src.ports.output.face_tracker_port import FaceTrackerPort
from src.ports.output.file_storage_port import FileStoragePort
from src.ports.output.job_repository import JobRepository
from src.ports.output.video_repository import VideoRepository

logger = logging.getLogger(__name__)

#: Seconds tracked either side of the clip, so small trims don't need a re-track.
_PADDING = 2.0


class ClipTrackingService:
    """Requests face tracking (API side) and runs the TRACK stage (worker side). Like an
    export, a TRACK job belongs to the clip, not the video. The worker only writes the
    result file; the editor applies it to the EDL, so autosave can't overwrite it.

    The automatic edit after analysis is the exception: nobody has the clip open, so
    the worker applies the shots itself and queues the clip's export to the outbox."""

    def __init__(
        self,
        clips: ClipRepository,
        videos: VideoRepository,
        jobs: JobRepository,
        storage: FileStoragePort,
        scheduler: JobScheduler,
        tracker: FaceTrackerPort | None = None,
        min_shot_seconds: float = 1.5,
        exports: ClipExportPort | None = None,
    ) -> None:
        self._clips = clips
        self._videos = videos
        self._jobs = jobs
        self._storage = storage
        self._scheduler = scheduler
        self._tracker = tracker
        self._min_shot_seconds = min_shot_seconds
        self._exports = exports

    async def request_tracking(self, clip_id: UUID, auto_rank: int | None = None) -> Job:
        clip = await self._clips.get(clip_id)
        if clip is None:
            raise NotFoundException(f"Clip {clip_id} not found")
        video = await self._videos.get(clip.video_id)
        if video is None or video.duration is None:
            raise NotFoundException(f"Video {clip.video_id} not found")
        bounds = edl_bounds(clip.edl)
        for job in await self._jobs.list_for_clip(clip_id, JobType.TRACK):
            covered = TimeSpan.model_validate(job.payload["span"])
            if (
                auto_rank is None
                and job.status is not JobStatus.FAILED
                and covered.start <= bounds.start
                and covered.end >= bounds.end
            ):
                return job
        span = TimeSpan(
            start=round(max(0.0, bounds.start - _PADDING), 3),
            end=min(video.duration, bounds.end + _PADDING),
        )
        payload = {"video_id": str(video.id), "span": span.model_dump()}
        if auto_rank is not None:
            payload["auto_rank"] = auto_rank
        job = Job(type=JobType.TRACK, clip_id=clip.id, payload=payload)
        await self._scheduler.submit(job)
        return job

    async def tracking_result(self, job_id: UUID) -> Tracking:
        job = await self._jobs.get(job_id)
        if job is None or job.type is not JobType.TRACK or job.status is not JobStatus.SUCCEEDED:
            raise NotFoundException(f"Finished face tracking {job_id} not found")
        path = self._storage.tracking_path(UUID(job.payload["video_id"]), job.id)
        try:
            return Tracking.model_validate_json(await asyncio.to_thread(path.read_text))
        except FileNotFoundError as e:
            raise NotFoundException(f"The result of face tracking {job_id} is gone") from e

    async def __call__(self, job: Job, report: ProgressCallback) -> None:
        """TRACK stage."""
        rank = job.payload.get("auto_rank")
        if rank is None:
            await self._track(job, report)
            return
        try:
            tracking = await self._track(job, report)
        except Exception as exc:
            # The clip still goes out, centre-cropped: one face-less clip mustn't stall it.
            logger.warning("Face tracking for clip %s failed (%s); centre crop", job.clip_id, exc)
            tracking = None
        await self._apply_and_export(job, tracking, rank)

    async def _apply_and_export(self, job: Job, tracking: Tracking | None, rank: int) -> None:
        clip = await self._clips.get(job.clip_id) if job.clip_id else None
        if clip is None:
            return  # re-analysed or deleted meanwhile
        if tracking is not None:
            clip.edl.tracking = tracking
            clip.updated_at = datetime.now(UTC)
            await self._clips.save(clip)
        if self._exports is not None:
            await self._exports.request_export(clip.id, outbox_rank=rank)

    async def _track(self, job: Job, report: ProgressCallback) -> Tracking:
        if self._tracker is None:
            raise RuntimeError("ClipTrackingService was built without a face tracker")
        video_id = UUID(job.payload["video_id"])
        video = await self._videos.get(video_id)
        if video is None or not (video.width and video.height):
            raise NotFoundException(f"Video {video_id} not found")
        span = TimeSpan.model_validate(job.payload["span"])
        tracks = await self._tracker.track(
            self._storage.path(video_id, VideoFile.SOURCE),
            self._storage.path(video_id, VideoFile.AUDIO),
            span,
            (video.width, video.height),
            report,
        )
        shots = build_shots(tracks, span, FRAME_RATE, self._min_shot_seconds)
        if not shots:
            raise MediaProcessingException("No faces found in this clip")
        tracking = Tracking(span=span, shots=shots)
        path = self._storage.tracking_path(video_id, job.id)
        await asyncio.to_thread(path.write_text, tracking.model_dump_json())
        return tracking
