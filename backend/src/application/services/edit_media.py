"""Looks up the other media an EDL uses (videos besides the clip's own, images, music),
for validating edits and for rendering."""

from uuid import UUID

from src.domain.enums.video_file_enum import VideoFile
from src.domain.exceptions import AppValidationException
from src.domain.models.edl import Edl, ImageSegment
from src.ports.output.file_storage_port import FileStoragePort
from src.ports.output.video_repository import VideoRepository


def referenced_videos(edl: Edl) -> set[UUID]:
    media = {getattr(s, "media", None) for s in edl.segments} | {b.media for b in edl.broll}
    return {m for m in media if m is not None}


def referenced_images(edl: Edl) -> set[str]:
    images = {s.image for s in edl.segments if isinstance(s, ImageSegment)}
    return images | {b.image for b in edl.broll if b.image is not None}


async def media_durations(
    edl: Edl, extra: set[UUID], videos: VideoRepository, storage: FileStoragePort
) -> dict[UUID, float]:
    """Durations of every video the EDL (or ``extra``) refers to whose source file is
    ready; videos that aren't are left out, so validation names them."""
    durations: dict[UUID, float] = {}
    for video_id in referenced_videos(edl) | extra:
        video = await videos.get(video_id)
        if video and video.duration and storage.path(video_id, VideoFile.SOURCE).is_file():
            durations[video_id] = video.duration
    return durations


def check_files(edl: Edl, storage: FileStoragePort) -> None:
    """Images and the music track must exist in their libraries."""
    for image in sorted(referenced_images(edl)):
        if not storage.image_path(image).is_file():
            raise AppValidationException(f"Image {image} not found")
    if edl.music and not storage.music_path(edl.music.file).is_file():
        raise AppValidationException(f"Music track {edl.music.file} not found")
