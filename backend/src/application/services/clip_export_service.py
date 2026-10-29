import re
from pathlib import Path
from uuid import UUID

from src.application.services.job_scheduler import JobScheduler
from src.application.services.pipeline_dispatcher import ProgressCallback
from src.domain.enums.job_status_enum import JobStatus
from src.domain.enums.job_type_enum import JobType
from src.domain.enums.video_file_enum import VideoFile
from src.domain.exceptions import MediaProcessingException, NotFoundException
from src.domain.models.edl import Edl
from src.domain.models.job import Job
from src.domain.services.edl_rules import validate_edl
from src.domain.services.render_planning import plan_render
from src.ports.input.clip_export_port import ExportFile
from src.ports.output.clip_repository import ClipRepository
from src.ports.output.file_storage_port import FileStoragePort
from src.ports.output.job_repository import JobRepository
from src.ports.output.renderer_port import RendererPort
from src.ports.output.video_repository import VideoRepository

_EXTENSIONS: dict[ExportFile, str] = {"video": "mp4", "subtitles": "srt"}


class ClipExportService:
    """Requests exports (API side) and runs the EXPORT stage (worker side). An export
    is a job: its payload snapshots the EDL, so later edits don't change a render in
    flight, and it is tied to the clip — not the video, so a failed render never marks
    the video failed."""

    def __init__(
        self,
        clips: ClipRepository,
        videos: VideoRepository,
        jobs: JobRepository,
        storage: FileStoragePort,
        scheduler: JobScheduler,
        renderer: RendererPort | None = None,
    ) -> None:
        self._clips = clips
        self._videos = videos
        self._jobs = jobs
        self._storage = storage
        self._scheduler = scheduler
        self._renderer = renderer

    async def request_export(self, clip_id: UUID) -> Job:
        clip = await self._clips.get(clip_id)
        if clip is None:
            raise NotFoundException(f"Clip {clip_id} not found")
        video = await self._videos.get(clip.video_id)
        if video is None or video.duration is None:
            raise NotFoundException(f"Video {clip.video_id} not found")
        validate_edl(clip.edl, video.duration)
        job = Job(
            type=JobType.EXPORT,
            clip_id=clip.id,
            payload={
                "video_id": str(video.id),
                "title": clip.title,
                "edl": clip.edl.model_dump(mode="json"),
            },
        )
        await self._scheduler.submit(job)
        return job

    async def list_exports(self, clip_id: UUID) -> list[Job]:
        return await self._jobs.list_for_clip(clip_id, JobType.EXPORT)

    async def export_file(self, export_id: UUID, file: ExportFile) -> tuple[Path, str]:
        job = await self._jobs.get(export_id)
        if job is None or job.type is not JobType.EXPORT or job.status is not JobStatus.SUCCEEDED:
            raise NotFoundException(f"Finished export {export_id} not found")
        extension = _EXTENSIONS[file]
        path = self._storage.export_path(UUID(job.payload["video_id"]), job.id, extension)
        if not path.is_file():
            raise NotFoundException(f"The {file} of export {export_id} is gone")
        return path, f"{_slug(job.payload.get('title', 'clip'))}.{extension}"

    async def __call__(self, job: Job, report: ProgressCallback) -> None:
        """EXPORT stage."""
        if self._renderer is None:
            raise RuntimeError("ClipExportService was built without a renderer")
        video_id = UUID(job.payload["video_id"])
        video = await self._videos.get(video_id)
        if video is None or not (video.width and video.height):
            raise NotFoundException(f"Video {video_id} not found")
        edl = Edl.model_validate(job.payload["edl"])
        music = self._storage.music_path(edl.music.file) if edl.music else None
        if music is not None and not music.is_file():
            raise MediaProcessingException(f"Music track {edl.music.file} is missing")

        await self._renderer.render(
            plan_render(edl, video.width, video.height),
            self._storage.path(video_id, VideoFile.SOURCE),
            music,
            self._storage.export_path(video_id, job.id, "mp4"),
            self._storage.export_path(video_id, job.id, "srt"),
            report,
        )


def _slug(title: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-")[:80] or "clip"
