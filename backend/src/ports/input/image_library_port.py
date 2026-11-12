"""Input port: still images to edit with (image segments, B-roll)."""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Protocol

from src.domain.models.image_asset import ImageAsset


class ImageLibraryPort(Protocol):
    async def upload(self, filename: str, chunks: AsyncIterator[bytes]) -> ImageAsset:
        """Store an image; raises ``AppValidationException`` for unsupported types."""
        ...

    async def list(self) -> list[ImageAsset]: ...

    async def path(self, file: str) -> Path:
        """Raises ``NotFoundException`` for unknown images."""
        ...
