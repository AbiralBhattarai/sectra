"""Input port: add, list and remove source videos."""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Protocol
from uuid import UUID

from src.domain.enums.video_file_enum import VideoFile
from src.domain.models.job import Job
from src.domain.models.video import Video


class VideoLibraryPort(Protocol):
    async def add_from_url(self, url: str) -> Video:
        """Register the video and queue its download."""
        ...

    async def add_upload(self, filename: str, chunks: AsyncIterator[bytes]) -> Video:
        """Store the uploaded file and queue its processing. Raises
        ``AppValidationException`` for unsupported file types."""
        ...

    async def list(self) -> list[tuple[Video, Job | None]]:
        """Videos newest first, each with its most recent job."""
        ...

    async def get(self, video_id: UUID) -> tuple[Video, Job | None]: ...

    async def delete(self, video_id: UUID) -> None: ...

    async def find_clips_again(self, video_id: UUID) -> Job:
        """Re-run clip analysis on a processed video, replacing its clips (and their
        edits). Raises ``AppValidationException`` if it hasn't been transcribed."""
        ...

    async def media_path(self, video_id: UUID, file: VideoFile) -> Path:
        """Location of one of the video's files; raises ``NotFoundException`` if absent."""
        ...
