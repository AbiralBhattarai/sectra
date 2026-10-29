from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import FileResponse

from src.adapters.input.rest.dependencies import get_video_library
from src.application.dto.job import JobDTO
from src.application.dto.video import AddVideoRequest, VideoDTO
from src.domain.enums.video_file_enum import VideoFile
from src.ports.input.video_library_port import VideoLibraryPort

router = APIRouter(prefix="/api/videos", tags=["videos"])

Library = Annotated[VideoLibraryPort, Depends(get_video_library)]


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def add_from_url(body: AddVideoRequest, library: Library) -> VideoDTO:
    return VideoDTO.from_domain(await library.add_from_url(body.url), None)


@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload(
    request: Request, library: Library, filename: Annotated[str, Query(min_length=1)]
) -> VideoDTO:
    """The request body is the raw file, streamed straight to disk (no multipart)."""
    return VideoDTO.from_domain(await library.add_upload(filename, request.stream()), None)


@router.get("")
async def list_videos(library: Library) -> list[VideoDTO]:
    return [VideoDTO.from_domain(video, job) for video, job in await library.list()]


@router.get("/{video_id}")
async def get_video(video_id: UUID, library: Library) -> VideoDTO:
    return VideoDTO.from_domain(*await library.get(video_id))


@router.delete("/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_video(video_id: UUID, library: Library) -> None:
    await library.delete(video_id)


@router.post("/{video_id}/analyze", status_code=status.HTTP_202_ACCEPTED)
async def find_clips_again(video_id: UUID, library: Library) -> JobDTO:
    """Re-run clip finding; replaces the video's clips."""
    return JobDTO.from_domain(await library.find_clips_again(video_id))


@router.get("/{video_id}/media/{file}")
async def media(video_id: UUID, file: VideoFile, library: Library) -> FileResponse:
    """Serves Range requests, so the browser can seek in videos."""
    return FileResponse(await library.media_path(video_id, file))
