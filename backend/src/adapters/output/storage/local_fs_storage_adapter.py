import contextlib
import functools
import json
import logging
import shutil
import time
from collections.abc import AsyncIterator
from concurrent.futures import Executor
from pathlib import Path
from typing import Any
from uuid import UUID

from src.domain.enums.video_file_enum import VideoFile
from src.domain.services.outbox_naming import folder_name, outbox_stem, unique_stem
from src.utils.concurrency import run_blocking

logger = logging.getLogger(__name__)

#: Scratch space for background downloads/uploads, inside the backgrounds root.
_INCOMING = ".incoming"
#: Upload chunks are buffered to this size before each (threaded) disk write.
_WRITE_BUFFER = 4 * 1024 * 1024


class LocalFsStorageAdapter:
    """Lays files out as ``<root>/videos/<video_id>/<file>`` and ``<root>/music/<name>``;
    music not uploaded there is looked up in the read-only built-in library. Clips
    ready to post go to ``<outbox>/<video title> [<id prefix>]/<rank> <caption>.mp4``."""

    def __init__(
        self,
        root: Path,
        executor: Executor,
        default_music_dir: Path | None = None,
        outbox_dir: Path | None = None,
        characters_dir: Path | None = None,
    ) -> None:
        self._videos_root = root / "videos"
        self._music_root = root / "music"
        self._backgrounds_root = root / "backgrounds"
        self._characters_root = characters_dir or Path("../assets/characters")
        self._outbox_root = outbox_dir or root / "outbox"
        self._default_music_root = default_music_dir
        self._executor = executor

    def video_dir(self, video_id: UUID) -> Path:
        path = self._videos_root / str(video_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def path(self, video_id: UUID, file: VideoFile) -> Path:
        return self._videos_root / str(video_id) / file.value

    def raw_path(self, video_id: UUID) -> Path | None:
        return next((self._videos_root / str(video_id)).glob("raw.*"), None)

    async def save_upload(
        self, video_id: UUID, extension: str, chunks: AsyncIterator[bytes]
    ) -> Path:
        dest = self.video_dir(video_id) / f"raw.{extension}"
        await self._stream_to(dest, chunks)
        return dest

    def export_path(self, video_id: UUID, export_id: UUID, extension: str) -> Path:
        directory = self._videos_root / str(video_id) / "exports"
        directory.mkdir(parents=True, exist_ok=True)
        return directory / f"{export_id}.{extension}"

    def tracking_path(self, video_id: UUID, job_id: UUID) -> Path:
        directory = self._videos_root / str(video_id) / "tracking"
        directory.mkdir(parents=True, exist_ok=True)
        return directory / f"{job_id}.json"

    async def write_outbox(
        self,
        video_id: UUID,
        video_title: str,
        rank: int,
        caption: str,
        video: Path,
        sidecar: dict[str, Any],
    ) -> Path:
        def write() -> Path:
            folder = self._outbox_root / f"{folder_name(video_title)} [{str(video_id)[:8]}]"
            folder.mkdir(parents=True, exist_ok=True)
            taken = {p.stem for p in folder.iterdir() if p.suffix in (".mp4", ".json")}
            stem = unique_stem(outbox_stem(rank, caption, fallback=sidecar.get("title", "")), taken)
            target = folder / f"{stem}.mp4"
            partial = folder / f"{stem}.mp4.partial"
            shutil.copyfile(video, partial)
            partial.replace(target)
            notes = folder / f"{stem}.json.partial"
            notes.write_text(json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8")
            notes.replace(folder / f"{stem}.json")
            return target

        return await run_blocking(self._executor, write)

    async def read_outbox_sidecar(self, video_id: UUID, export_id: UUID) -> dict[str, Any] | None:
        suffix = f"[{str(video_id)[:8]}]"

        def read() -> dict[str, Any] | None:
            if not self._outbox_root.is_dir():
                return None
            for folder in self._outbox_root.iterdir():
                if not (folder.is_dir() and folder.name.endswith(suffix)):
                    continue
                for sidecar in folder.glob("*.json"):
                    try:
                        data = json.loads(sidecar.read_text(encoding="utf-8"))
                    except (OSError, ValueError):
                        continue  # being rewritten by the poster: next poll
                    if data.get("export_id") == str(export_id):
                        return data
            return None

        return await run_blocking(self._executor, read)

    async def save_music(self, name: str, chunks: AsyncIterator[bytes]) -> str:
        self._music_root.mkdir(parents=True, exist_ok=True)
        # Always the user's folder: music_path() would fall back to the read-only
        # built-in library for a file that doesn't exist yet.
        dest = self._music_root / name
        try:
            await self._stream_to(dest, chunks)
        except BaseException:
            dest.unlink(missing_ok=True)
            raise
        return name

    def list_music(self) -> list[str]:
        if not self._music_root.is_dir():
            return []
        return sorted(p.name for p in self._music_root.iterdir() if p.is_file())

    def music_path(self, name: str) -> Path:
        uploaded = self._music_root / name
        if uploaded.is_file() or self._default_music_root is None:
            return uploaded
        return self._default_music_root / name

    async def _stream_to(self, dest: Path, chunks: AsyncIterator[bytes]) -> None:
        handle = await run_blocking(self._executor, open, dest, "wb")
        try:
            buffer = bytearray()
            async for chunk in chunks:
                buffer += chunk
                if len(buffer) >= _WRITE_BUFFER:
                    await run_blocking(self._executor, handle.write, bytes(buffer))
                    buffer.clear()
            await run_blocking(self._executor, handle.write, bytes(buffer))
        finally:
            await run_blocking(self._executor, handle.close)

    async def read_text(self, video_id: UUID, file: VideoFile) -> str:
        path = self.path(video_id, file)
        return await run_blocking(
            self._executor, functools.partial(path.read_text, encoding="utf-8")
        )

    async def write_text(self, video_id: UUID, file: VideoFile, content: str) -> None:
        def write() -> None:
            target = self.path(video_id, file)
            partial = target.with_name(f"{target.name}.partial")
            partial.write_text(content, encoding="utf-8")
            partial.replace(target)

        await run_blocking(self._executor, write)

    def background_incoming_dir(self, job_id: UUID) -> Path:
        path = self._backgrounds_root / _INCOMING / str(job_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    async def save_background_upload(
        self, job_id: UUID, extension: str, chunks: AsyncIterator[bytes]
    ) -> Path:
        dest = self.background_incoming_dir(job_id) / f"raw.{extension}"
        await self._stream_to(dest, chunks)
        return dest

    def background_path(self, category: str, file: str) -> Path:
        directory = self._backgrounds_root / category
        directory.mkdir(parents=True, exist_ok=True)
        return directory / file

    def list_backgrounds(self) -> list[tuple[str, str]]:
        if not self._backgrounds_root.is_dir():
            return []
        return sorted(
            (category.name, file.name)
            for category in self._backgrounds_root.iterdir()
            if category.is_dir() and category.name != _INCOMING
            for file in category.glob("*.mp4")
            if not file.name.endswith(".partial.mp4")
        )

    async def delete_background(self, category: str, file: str) -> None:
        def delete() -> None:
            (self._backgrounds_root / category / file).unlink(missing_ok=True)
            directory = self._backgrounds_root / category
            if directory.is_dir() and not any(directory.iterdir()):
                directory.rmdir()

        await run_blocking(self._executor, delete)

    async def remove_background_incoming(self, job_id: UUID) -> None:
        await run_blocking(
            self._executor,
            shutil.rmtree,
            self._backgrounds_root / _INCOMING / str(job_id),
            True,
        )

    def character_path(self, name: str, layer: str) -> Path:
        return self._characters_root / name / layer

    async def delete_video(self, video_id: UUID) -> None:
        def delete() -> None:
            folders = [self._videos_root / str(video_id), *self._outbox_folders(video_id)]
            for folder in folders:
                shutil.rmtree(folder, ignore_errors=True)
                if folder.exists():  # a file still open (the poster uploading it, a player)
                    logger.warning("Couldn't remove all of %s; delete what's left by hand", folder)

        await run_blocking(self._executor, delete)

    def leftovers(self, known: set[str], min_age_seconds: float = 600) -> list[Path]:
        """Folders of videos that no longer exist: ``videos/<id>/`` and outbox folders
        whose sidecars all name unknown videos. Recently changed ones are left alone (a
        video being created right now isn't in the list that was read)."""
        now = time.time()

        def old(path: Path) -> bool:
            return now - path.stat().st_mtime >= min_age_seconds

        found = []
        if self._videos_root.is_dir():
            for folder in self._videos_root.iterdir():
                if folder.is_dir() and folder.name not in known and old(folder):
                    with contextlib.suppress(ValueError):
                        UUID(folder.name)  # only video folders
                        found.append(folder)
        if self._outbox_root.is_dir():
            for folder in self._outbox_root.iterdir():
                if not folder.is_dir() or not old(folder):
                    continue
                owners = set()
                for sidecar in folder.glob("*.json"):
                    try:
                        owners.add(json.loads(sidecar.read_text(encoding="utf-8")).get("video_id"))
                    except (OSError, ValueError):
                        owners.add("?")  # unreadable: keep the folder
                if owners and not owners & (known | {"?", None}):
                    found.append(folder)
        return found

    def _outbox_folders(self, video_id: UUID) -> list[Path]:
        """The video's outbox folders: named ``… [<id prefix>]``, and every sidecar in them
        names this exact video (an id prefix alone could, rarely, be another video's)."""
        if not self._outbox_root.is_dir():
            return []
        suffix = f"[{str(video_id)[:8]}]"
        found = []
        for folder in self._outbox_root.iterdir():
            if not (folder.is_dir() and folder.name.endswith(suffix)):
                continue
            owners = set()
            for sidecar in folder.glob("*.json"):
                try:
                    owners.add(json.loads(sidecar.read_text(encoding="utf-8")).get("video_id"))
                except (OSError, ValueError):
                    owners.add(None)  # unreadable: can't tell whose it is
            if owners <= {str(video_id)}:
                found.append(folder)
        return found
