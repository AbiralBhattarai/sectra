import shutil
from collections.abc import AsyncIterator
from concurrent.futures import Executor
from pathlib import Path
from uuid import UUID

from src.domain.enums.video_file_enum import VideoFile
from src.utils.concurrency import run_blocking

#: Upload chunks are buffered to this size before each (threaded) disk write.
_WRITE_BUFFER = 4 * 1024 * 1024


class LocalFsStorageAdapter:
    """Lays files out as ``<root>/videos/<video_id>/<file>`` and ``<root>/music/<name>``;
    music not uploaded there is looked up in the read-only built-in library."""

    def __init__(
        self, root: Path, executor: Executor, default_music_dir: Path | None = None
    ) -> None:
        self._videos_root = root / "videos"
        self._music_root = root / "music"
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
        return await run_blocking(self._executor, self.path(video_id, file).read_text)

    async def write_text(self, video_id: UUID, file: VideoFile, content: str) -> None:
        def write() -> None:
            target = self.path(video_id, file)
            partial = target.with_name(f"{target.name}.partial")
            partial.write_text(content)
            partial.replace(target)

        await run_blocking(self._executor, write)

    async def delete_video(self, video_id: UUID) -> None:
        await run_blocking(self._executor, shutil.rmtree, self._videos_root / str(video_id), True)
