from collections.abc import AsyncIterator
from pathlib import Path, PurePath
from uuid import UUID

from src.application.services.job_scheduler import JobScheduler
from src.domain.enums.job_type_enum import JobType
from src.domain.enums.video_file_enum import VideoFile
from src.domain.enums.video_status_enum import VideoStatus
from src.domain.exceptions import AppValidationException, NotFoundException
from src.domain.models.job import Job
from src.domain.models.video import Video
from src.ports.output.file_storage_port import FileStoragePort
from src.ports.output.job_repository import JobRepository
from src.ports.output.video_repository import VideoRepository

UPLOAD_EXTENSIONS = {"mp4", "mov", "mkv", "webm", "m4v", "avi"}


class VideoLibraryService:
    def __init__(
        self,
        videos: VideoRepository,
        jobs: JobRepository,
        storage: FileStoragePort,
        scheduler: JobScheduler,
    ) -> None:
        self._videos = videos
        self._jobs = jobs
        self._storage = storage
        self._scheduler = scheduler

    async def add_from_url(self, url: str) -> Video:
        video = Video(title=url, source_url=url)
        await self._videos.add(video)
        await self._scheduler.submit(Job(type=JobType.INGEST, video_id=video.id))
        return video

    async def add_upload(self, filename: str, chunks: AsyncIterator[bytes]) -> Video:
        name = PurePath(filename)
        extension = name.suffix.lower().lstrip(".")
        if extension not in UPLOAD_EXTENSIONS:
            raise AppValidationException(
                f"Unsupported file type '.{extension}'; expected one of "
                + ", ".join(sorted(UPLOAD_EXTENSIONS))
            )
        video = Video(title=name.stem or filename)
        try:
            await self._storage.save_upload(video.id, extension, chunks)
        except BaseException:
            await self._storage.delete_video(video.id)
            raise
        await self._videos.add(video)
        # Already on disk, so processing starts at normalization.
        await self._scheduler.submit(Job(type=JobType.NORMALIZE, video_id=video.id))
        return video

    async def list(self) -> list[tuple[Video, Job | None]]:
        videos = await self._videos.list()
        latest = await self._jobs.latest_for_videos([v.id for v in videos])
        return [(video, latest.get(video.id)) for video in videos]

    async def get(self, video_id: UUID) -> tuple[Video, Job | None]:
        video = await self._require(video_id)
        latest = await self._jobs.latest_for_videos([video_id])
        return video, latest.get(video_id)

    async def delete(self, video_id: UUID) -> None:
        await self._require(video_id)
        await self._videos.delete(video_id)
        await self._storage.delete_video(video_id)

    async def find_clips_again(self, video_id: UUID) -> Job:
        video = await self._require(video_id)
        if video.status is VideoStatus.PROCESSING:
            raise AppValidationException("The video is still being processed")
        if not self._storage.path(video_id, VideoFile.TRANSCRIPT).is_file():
            raise AppValidationException("The video has no transcript yet")
        video.status = VideoStatus.PROCESSING
        await self._videos.save(video)
        job = Job(type=JobType.ANALYZE, video_id=video_id)
        await self._scheduler.submit(job)
        return job

    async def media_path(self, video_id: UUID, file: VideoFile) -> Path:
        await self._require(video_id)
        path = self._storage.path(video_id, file)
        if not path.is_file():
            raise NotFoundException(f"{file.value} is not available for video {video_id}")
        return path

    async def _require(self, video_id: UUID) -> Video:
        video = await self._videos.get(video_id)
        if video is None:
            raise NotFoundException(f"Video {video_id} not found")
        return video
