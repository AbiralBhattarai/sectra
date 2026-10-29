from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import FileResponse

from src.adapters.input.rest.dependencies import get_music_library
from src.domain.models.music_track import MusicTrack
from src.ports.input.music_library_port import MusicLibraryPort

router = APIRouter(prefix="/api/music", tags=["music"])

Library = Annotated[MusicLibraryPort, Depends(get_music_library)]


@router.get("")
async def list_tracks(library: Library) -> list[MusicTrack]:
    return await library.list()


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload(
    request: Request, library: Library, filename: Annotated[str, Query(min_length=1)]
) -> MusicTrack:
    """The request body is the raw audio file."""
    return await library.upload(filename, request.stream())


@router.get("/{file}")
async def track(file: str, library: Library) -> FileResponse:
    return FileResponse(await library.path(file))
