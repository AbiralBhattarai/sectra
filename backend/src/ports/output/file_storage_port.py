"""Output port for the media files kept per video."""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Protocol
from uuid import UUID

from src.domain.enums.video_file_enum import VideoFile


class FileStoragePort(Protocol):
    def video_dir(self, video_id: UUID) -> Path:
        """Directory holding the video's files, created if missing."""
        ...

    def path(self, video_id: UUID, file: VideoFile) -> Path: ...

    def raw_path(self, video_id: UUID) -> Path | None:
        """The downloaded/uploaded file awaiting normalization, if present."""
        ...

    async def save_upload(
        self, video_id: UUID, extension: str, chunks: AsyncIterator[bytes]
    ) -> Path:
        """Stream an uploaded file to ``raw.<extension>``."""
        ...

    async def read_text(self, video_id: UUID, file: VideoFile) -> str:
        """Raises ``FileNotFoundError`` when the file does not exist."""
        ...

    async def write_text(self, video_id: UUID, file: VideoFile, content: str) -> None:
        """Write atomically, so readers never see a half-written file."""
        ...

    def export_path(self, video_id: UUID, export_id: UUID, extension: str) -> Path:
        """Where an export's file goes (inside the video's directory, so deleting the
        video deletes its exports). The directory is created if missing."""
        ...

    async def save_music(self, name: str, chunks: AsyncIterator[bytes]) -> str:
        """Stream an uploaded track into the music library under the given file name."""
        ...

    def list_music(self) -> list[str]:
        """File names in the music library, sorted."""
        ...

    def music_path(self, name: str) -> Path:
        """Location of a track: an upload, else a built-in one (it may not exist)."""
        ...

    async def delete_video(self, video_id: UUID) -> None:
        """Remove every file of the video."""
        ...
