from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import FileResponse

from src.adapters.input.rest.dependencies import get_image_library
from src.domain.models.image_asset import ImageAsset
from src.ports.input.image_library_port import ImageLibraryPort

router = APIRouter(prefix="/api/images", tags=["images"])

Library = Annotated[ImageLibraryPort, Depends(get_image_library)]


@router.get("")
async def list_images(library: Library) -> list[ImageAsset]:
    return await library.list()


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload(
    request: Request, library: Library, filename: Annotated[str, Query(min_length=1)]
) -> ImageAsset:
    """The request body is the raw image file."""
    return await library.upload(filename, request.stream())


@router.get("/{file}")
async def image(file: str, library: Library) -> FileResponse:
    return FileResponse(await library.path(file))
