import re
import uuid
from collections.abc import AsyncIterator
from pathlib import Path, PurePath

from src.domain.exceptions import AppValidationException, NotFoundException
from src.domain.models.music_track import MusicTrack
from src.ports.output.file_storage_port import FileStoragePort

MUSIC_EXTENSIONS = {"mp3", "m4a", "aac", "wav", "ogg", "flac"}
#: Stored as "<8 hex>-<slug>.<ext>" so names are unique and safe in paths.
_STORED = re.compile(r"^[0-9a-f]{8}-(?P<slug>[A-Za-z0-9._-]*)\.[a-z0-9]+$")


class MusicLibraryService:
    """The built-in CC0 tracks plus the user's uploads."""

    def __init__(self, storage: FileStoragePort, defaults: list[MusicTrack] | None = None) -> None:
        self._storage = storage
        self._defaults = {track.file: track for track in defaults or []}

    async def upload(self, filename: str, chunks: AsyncIterator[bytes]) -> MusicTrack:
        name = PurePath(filename)
        extension = name.suffix.lower().lstrip(".")
        if extension not in MUSIC_EXTENSIONS:
            raise AppValidationException(
                f"Unsupported audio type '.{extension}'; expected one of "
                + ", ".join(sorted(MUSIC_EXTENSIONS))
            )
        slug = re.sub(r"[^A-Za-z0-9._-]+", "-", name.stem).strip("-.")[:60] or "track"
        file = f"{uuid.uuid4().hex[:8]}-{slug}.{extension}"
        await self._storage.save_music(file, chunks)
        return _track(file)

    async def list(self) -> list[MusicTrack]:
        uploads = [_track(file) for file in self._storage.list_music() if _STORED.match(file)]
        return [*self._defaults.values(), *uploads]

    async def path(self, file: str) -> Path:
        known = file in self._defaults or _STORED.match(file)
        path = self._storage.music_path(file)
        if not known or not path.is_file():
            raise NotFoundException(f"Music track {file} not found")
        return path


def _track(file: str) -> MusicTrack:
    match = _STORED.match(file)
    slug = match.group("slug") if match else file
    return MusicTrack(file=file, name=slug.replace("-", " ").replace("_", " "))
