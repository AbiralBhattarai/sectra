"""Output port for the media files kept per video."""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Protocol
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

    def tracking_path(self, video_id: UUID, job_id: UUID) -> Path:
        """Where a TRACK job's shots (JSON) go, inside the video's directory. The
        directory is created if missing."""
        ...

    async def write_outbox(
        self,
        video_id: UUID,
        video_title: str,
        rank: int,
        caption: str,
        video: Path,
        sidecar: dict[str, Any],
    ) -> Path:
        """Copy a finished clip into the outbox folder of its video as
        ``<rank> <caption>.mp4``, then write ``sidecar`` next to it as JSON with the
        same name. Both appear atomically, the JSON last, so a reader that waits for the
        JSON never sees a half-copied video. Returns the video's new path."""
        ...

    async def read_outbox_sidecar(self, video_id: UUID, export_id: UUID) -> dict[str, Any] | None:
        """The outbox sidecar written for ``export_id`` (with whatever the poster has
        recorded in it since), or None if there is none."""
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

    def background_incoming_dir(self, job_id: UUID) -> Path:
        """Scratch directory for a BACKGROUND job's download/upload, created if missing."""
        ...

    async def save_background_upload(
        self, job_id: UUID, extension: str, chunks: AsyncIterator[bytes]
    ) -> Path:
        """Stream an uploaded gameplay clip into the job's scratch directory."""
        ...

    def background_path(self, category: str, file: str) -> Path:
        """Location of a library clip (it may not exist); the category dir is created."""
        ...

    def list_backgrounds(self) -> list[tuple[str, str]]:
        """(category, file) of every finished library clip, sorted."""
        ...

    async def delete_background(self, category: str, file: str) -> None: ...

    async def remove_background_incoming(self, job_id: UUID) -> None: ...

    def character_path(self, name: str, layer: str) -> Path:
        """A narrator character's layer file, e.g. ``("guy", "mouth/A.svg")``."""
        ...

    async def delete_video(self, video_id: UUID) -> None:
        """Remove every file of the video."""
        ...
