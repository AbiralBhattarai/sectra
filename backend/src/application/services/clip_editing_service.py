from datetime import UTC, datetime
from uuid import UUID

from src.domain.exceptions import AppValidationException, NotFoundException
from src.domain.models.clip import Clip
from src.domain.models.edl import Edl
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

    async def update_edl(self, clip_id: UUID, edl: Edl) -> Clip:
        clip = await self.get(clip_id)
        video = await self._videos.get(clip.video_id)
        if video is None or video.duration is None:
            raise NotFoundException(f"Video {clip.video_id} not found")
        validate_edl(edl, video.duration)
        if edl.music and not self._storage.music_path(edl.music.file).is_file():
            raise AppValidationException(f"Music track {edl.music.file} not found")
        bounds = edl_bounds(edl)
        clip.edl, clip.start, clip.end = edl, bounds.start, bounds.end
        clip.updated_at = datetime.now(UTC)
        await self._clips.save(clip)
        return clip
