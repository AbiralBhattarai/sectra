from src.application.services.pipeline_dispatcher import ProgressCallback
from src.domain.exceptions import AppValidationException, NotFoundException
from src.domain.models.job import Job
from src.ports.output.downloader_port import DownloaderPort
from src.ports.output.file_storage_port import FileStoragePort
from src.ports.output.video_repository import VideoRepository


class IngestService:
    """INGEST stage: download the video's URL into its directory as ``raw.<ext>``."""

    def __init__(
        self, videos: VideoRepository, storage: FileStoragePort, downloader: DownloaderPort
    ) -> None:
        self._videos = videos
        self._storage = storage
        self._downloader = downloader

    async def __call__(self, job: Job, report: ProgressCallback) -> None:
        video = await self._videos.get(job.video_id) if job.video_id else None
        if video is None:
            raise NotFoundException(f"Video {job.video_id} not found")
        if not video.source_url:
            raise AppValidationException("Video has no source URL to download")

        # A retried download starts clean rather than resuming a half-written file.
        if stale := self._storage.raw_path(video.id):
            stale.unlink()
        result = await self._downloader.download(
            video.source_url, self._storage.video_dir(video.id), report
        )
        if result.title:
            video.title = result.title
        video.duration = result.duration
        await self._videos.save(video)
