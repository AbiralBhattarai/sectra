import json
from datetime import UTC, datetime
from uuid import UUID

from src.domain.enums.video_file_enum import VideoFile
from src.domain.exceptions import AppValidationException, NotFoundException
from src.domain.models.clip import Clip
from src.domain.models.edl import Edl, Zoom
from src.domain.models.speech import TimeSpan
from src.domain.models.transcript import Transcript
from src.domain.services.auto_zoom import auto_zooms
from src.domain.services.edl_rules import edl_bounds, validate_edl
from src.ports.output.clip_repository import ClipRepository
from src.ports.output.file_storage_port import FileStoragePort
from src.ports.output.video_repository import VideoRepository


class ClipEditingService:
    def __init__(
        self, clips: ClipRepository, videos: VideoRepository, storage: FileStoragePort
    ) -> None:
        self._clips = clips
        self._videos = videos
        self._storage = storage

    async def list_for_video(self, video_id: UUID) -> list[Clip]:
        if await self._videos.get(video_id) is None:
            raise NotFoundException(f"Video {video_id} not found")
        return await self._clips.list_for_video(video_id)

    async def get(self, clip_id: UUID) -> Clip:
        clip = await self._clips.get(clip_id)
        if clip is None:
            raise NotFoundException(f"Clip {clip_id} not found")
        return clip

    async def update_edl(self, clip_id: UUID, edl: Edl, caption: str | None = None) -> Clip:
        clip = await self.get(clip_id)
        video = await self._videos.get(clip.video_id)
        if video is None or video.duration is None:
            raise NotFoundException(f"Video {clip.video_id} not found")
        validate_edl(edl, video.duration)
        if edl.music and not self._storage.music_path(edl.music.file).is_file():
            raise AppValidationException(f"Music track {edl.music.file} not found")
        bounds = edl_bounds(edl)
        clip.edl, clip.start, clip.end = edl, bounds.start, bounds.end
        if caption is not None:
            clip.caption = caption.strip()
        clip.updated_at = datetime.now(UTC)
        await self._clips.save(clip)
        return clip

    async def auto_zoom(self, clip_id: UUID, ranges: list[TimeSpan]) -> list[Zoom]:
        clip = await self.get(clip_id)
        try:
            transcript = Transcript.model_validate_json(
                await self._storage.read_text(clip.video_id, VideoFile.TRANSCRIPT)
            )
        except FileNotFoundError as e:
            raise NotFoundException(f"The transcript of video {clip.video_id} is gone") from e
        try:
            peaks = json.loads(await self._storage.read_text(clip.video_id, VideoFile.PEAKS))
        except FileNotFoundError:
            peaks = None
        ordered = sorted(ranges, key=lambda r: r.start)
        return auto_zooms(
            TimeSpan(start=ordered[0].start, end=ordered[-1].end),
            transcript.segments,
            peaks["peaks"] if peaks else None,
            peaks["per_second"] if peaks else 20,
        )
