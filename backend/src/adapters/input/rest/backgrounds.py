from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import FileResponse

from src.adapters.input.rest.dependencies import get_backgrounds
from src.application.dto.job import JobDTO
from src.application.dto.story import AddBackgroundRequest, BackgroundDTO, BackgroundLibraryDTO
from src.ports.input.background_library_port import BackgroundLibraryPort

router = APIRouter(prefix="/api/backgrounds", tags=["backgrounds"])

Library = Annotated[BackgroundLibraryPort, Depends(get_backgrounds)]


@router.get("")
async def list_backgrounds(library: Library) -> BackgroundLibraryDTO:
    ready, pending = await library.list()
    return BackgroundLibraryDTO(
        ready=[BackgroundDTO.from_domain(b) for b in ready], pending=pending
    )


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def add_from_url(body: AddBackgroundRequest, library: Library) -> JobDTO:
    return JobDTO.from_domain(await library.add_from_url(body.url, body.category))


@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload(
    request: Request,
    library: Library,
    filename: Annotated[str, Query(min_length=1)],
    category: Annotated[str, Query(min_length=1, max_length=40)],
) -> JobDTO:
    """The request body is the raw video file."""
    return JobDTO.from_domain(await library.add_upload(filename, category, request.stream()))


@router.get("/{category}/{file}")
async def clip(category: str, file: str, library: Library) -> FileResponse:
    return FileResponse(await library.path(category, file))


@router.delete("/{category}/{file}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(category: str, file: str, library: Library) -> None:
    await library.delete(category, file)
