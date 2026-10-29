"""Input port: the background-music library."""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Protocol

from src.domain.models.music_track import MusicTrack


class MusicLibraryPort(Protocol):
    async def upload(self, filename: str, chunks: AsyncIterator[bytes]) -> MusicTrack:
        """Store a track; raises ``AppValidationException`` for unsupported types."""
        ...

    async def list(self) -> list[MusicTrack]: ...

    async def path(self, file: str) -> Path:
        """Raises ``NotFoundException`` for unknown tracks."""
        ...
