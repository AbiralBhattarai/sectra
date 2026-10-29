from src.application.services.pipeline_dispatcher import ProgressCallback
from src.domain.enums.video_file_enum import VideoFile
from src.domain.exceptions import NotFoundException
from src.domain.models.job import Job
from src.domain.models.speech import SpeechMap
from src.domain.services.speech_detection import speech_segments
from src.ports.output.file_storage_port import FileStoragePort
from src.ports.output.vad_port import VADPort
from src.ports.output.video_repository import VideoRepository


class SpeechDetectionService:
    """VAD stage: find where people speak, so transcription can skip the rest."""

    def __init__(self, videos: VideoRepository, storage: FileStoragePort, vad: VADPort) -> None:
        self._videos = videos
        self._storage = storage
        self._vad = vad

    async def __call__(self, job: Job, report: ProgressCallback) -> None:
        video = await self._videos.get(job.video_id) if job.video_id else None
        if video is None or video.duration is None:
            raise NotFoundException(f"Prepared video {job.video_id} not found")

        frames = await self._vad.frame_probabilities(
            self._storage.path(video.id, VideoFile.AUDIO), report
        )
        speech = SpeechMap(
            duration=video.duration,
            segments=speech_segments(frames.probabilities, frames.frame_seconds),
        )
        await self._storage.write_text(video.id, VideoFile.SPEECH, speech.model_dump_json())
