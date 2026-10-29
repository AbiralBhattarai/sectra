import asyncio

from src.application.services.pipeline_dispatcher import ProgressCallback
from src.domain.enums.video_file_enum import VideoFile
from src.domain.exceptions import MediaProcessingException, NotFoundException
from src.domain.models.job import Job
from src.domain.models.video import Video
from src.domain.services.media_rules import plan_normalization
from src.ports.output.file_storage_port import FileStoragePort
from src.ports.output.media_port import MediaPort
from src.ports.output.video_repository import VideoRepository

#: Waveform resolution for the timeline.
PEAKS_PER_SECOND = 20


class MediaPreparationService:
    """NORMALIZE and PREPARE stages."""

    def __init__(self, videos: VideoRepository, storage: FileStoragePort, media: MediaPort) -> None:
        self._videos = videos
        self._storage = storage
        self._media = media

    async def normalize(self, job: Job, report: ProgressCallback) -> None:
        """Store the raw file as ``source.mp4`` with its short side ≤ 1080 and H.264/AAC."""
        video = await self._video(job)
        source = self._storage.path(video.id, VideoFile.SOURCE)
        raw = self._storage.raw_path(video.id)
        if raw is None:
            if source.exists():
                return  # finished earlier; the worker died before recording it
            raise MediaProcessingException("No downloaded or uploaded file to process")

        info = await self._media.probe(raw)
        if info.audio_codec is None:
            raise MediaProcessingException(
                "Video has no audio track, so there is no speech to clip"
            )

        partial = source.with_name(f"{source.stem}.partial{source.suffix}")
        await self._media.normalize(raw, partial, plan_normalization(info), info.duration, report)
        partial.replace(source)
        raw.unlink()

        stored = await self._media.probe(source)
        video.duration, video.width, video.height = stored.duration, stored.width, stored.height
        await self._videos.save(video)

    async def prepare(self, job: Job, report: ProgressCallback) -> None:
        """Derive the analysis audio, waveform and thumbnail from ``source.mp4``. (No
        preview copy: the editor plays ``source.mp4`` itself; encoding a proxy took
        about an hour on a 6 h video.)"""
        video = await self._video(job)
        if not (video.width and video.height and video.duration):
            raise MediaProcessingException("Video has not been normalized")
        source, audio, peaks, thumbnail = (
            self._storage.path(video.id, file)
            for file in (VideoFile.SOURCE, VideoFile.AUDIO, VideoFile.PEAKS, VideoFile.THUMBNAIL)
        )

        async def audio_and_peaks() -> None:
            await self._media.extract_audio(source, audio)
            await report(0.6)
            await self._media.compute_peaks(audio, peaks, PEAKS_PER_SECOND)

        await asyncio.gather(
            audio_and_peaks(),
            self._media.make_thumbnail(source, thumbnail, video.duration * 0.1),
        )

    async def _video(self, job: Job) -> Video:
        video = await self._videos.get(job.video_id) if job.video_id else None
        if video is None:
            raise NotFoundException(f"Video {job.video_id} not found")
        return video
