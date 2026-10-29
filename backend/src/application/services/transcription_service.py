import asyncio

from src.application.services.pipeline_dispatcher import ProgressCallback
from src.domain.enums.video_file_enum import VideoFile
from src.domain.exceptions import NotFoundException
from src.domain.models.job import Job
from src.domain.models.speech import SpeechMap, TimeSpan
from src.domain.models.transcript import Transcript
from src.domain.services.transcript_merging import merge_chunk_transcripts
from src.domain.services.vad_chunking import build_chunks
from src.ports.output.file_storage_port import FileStoragePort
from src.ports.output.stt_port import STTPort
from src.ports.output.video_repository import VideoRepository


class TranscriptionService:
    """TRANSCRIBE stage: run speech-to-text over the speech chunks concurrently (the
    STT adapter's semaphore decides how many at once) and stitch the results."""

    def __init__(
        self,
        videos: VideoRepository,
        storage: FileStoragePort,
        stt: STTPort,
        language: str | None,
    ) -> None:
        self._videos = videos
        self._storage = storage
        self._stt = stt
        self._language = language

    async def __call__(self, job: Job, report: ProgressCallback) -> None:
        video = await self._videos.get(job.video_id) if job.video_id else None
        if video is None:
            raise NotFoundException(f"Video {job.video_id} not found")

        speech = SpeechMap.model_validate_json(
            await self._storage.read_text(video.id, VideoFile.SPEECH)
        )
        chunks = build_chunks(speech.segments, speech.duration)
        audio = self._storage.path(video.id, VideoFile.AUDIO)
        parts: list[tuple[TimeSpan, Transcript]] = []

        async def transcribe(chunk: TimeSpan) -> None:
            parts.append((chunk, await self._stt.transcribe(audio, chunk, self._language)))
            await report(len(parts) / len(chunks))

        try:
            # A failing chunk cancels the rest instead of transcribing for nothing.
            async with asyncio.TaskGroup() as group:
                for chunk in chunks:
                    group.create_task(transcribe(chunk))
        except ExceptionGroup as errors:
            raise errors.exceptions[0] from errors

        transcript = merge_chunk_transcripts(parts, speech.segments)
        await self._storage.write_text(video.id, VideoFile.TRANSCRIPT, transcript.model_dump_json())
