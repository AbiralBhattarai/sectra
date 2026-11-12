import re
import uuid
from collections.abc import AsyncIterator
from pathlib import Path, PurePath

from src.domain.exceptions import AppValidationException, NotFoundException
from src.domain.models.image_asset import ImageAsset
from src.ports.output.file_storage_port import FileStoragePort

IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
#: Stored as "<8 hex>-<slug>.<ext>" so names are unique and safe in paths.
_STORED = re.compile(r"^[0-9a-f]{8}-(?P<slug>[A-Za-z0-9._-]*)\.[a-z0-9]+$")


class ImageLibraryService:
    """The user's uploaded images, laid out like the music library."""

    def __init__(self, storage: FileStoragePort) -> None:
        self._storage = storage

    async def upload(self, filename: str, chunks: AsyncIterator[bytes]) -> ImageAsset:
        name = PurePath(filename)
        extension = name.suffix.lower().lstrip(".")
        if extension not in IMAGE_EXTENSIONS:
            raise AppValidationException(
                f"Unsupported image type '.{extension}'; expected one of "
                + ", ".join(sorted(IMAGE_EXTENSIONS))
            )
        slug = re.sub(r"[^A-Za-z0-9._-]+", "-", name.stem).strip("-.")[:60] or "image"
        file = f"{uuid.uuid4().hex[:8]}-{slug}.{extension}"
        await self._storage.save_image(file, chunks)
        return _asset(file)

    async def list(self) -> list[ImageAsset]:
        return [_asset(file) for file in self._storage.list_images() if _STORED.match(file)]

    async def path(self, file: str) -> Path:
        path = self._storage.image_path(file)
        if not _STORED.match(file) or not path.is_file():
            raise NotFoundException(f"Image {file} not found")
        return path


def _asset(file: str) -> ImageAsset:
    match = _STORED.match(file)
    slug = match.group("slug") if match else file
    return ImageAsset(file=file, name=slug.replace("-", " ").replace("_", " "))
