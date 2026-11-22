from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import FileResponse

from src.adapters.input.rest.dependencies import get_clip_export
from src.application.dto.clip import PostClipRequest
from src.application.dto.export import ExportDTO, PostStatusDTO
from src.ports.input.clip_export_port import ClipExportPort, ExportFile

router = APIRouter(prefix="/api", tags=["exports"])

Exports = Annotated[ClipExportPort, Depends(get_clip_export)]


@router.post("/clips/{clip_id}/exports", status_code=status.HTTP_202_ACCEPTED)
async def request_export(clip_id: UUID, exports: Exports) -> ExportDTO:
    return ExportDTO.from_job(await exports.request_export(clip_id))


@router.post("/clips/{clip_id}/post", status_code=status.HTTP_202_ACCEPTED)
async def post_clip(
    clip_id: UUID, exports: Exports, body: PostClipRequest | None = None
) -> PostStatusDTO:
    """Render the clip into the outbox for `poster serve` to post everywhere now, with
    the title plus the clip's post caption as the description."""
    post_caption = body.post_caption if body else None
    return PostStatusDTO.from_post(await exports.request_post(clip_id, post_caption), None)


@router.get("/clips/{clip_id}/post", response_model=PostStatusDTO | None)
async def post_status(clip_id: UUID, exports: Exports, response: Response):
    """The latest Post of the clip and how far the poster got; 204 if never posted."""
    found = await exports.post_status(clip_id)
    if found is None:
        response.status_code = status.HTTP_204_NO_CONTENT
        return None
    return PostStatusDTO.from_post(*found)


@router.get("/clips/{clip_id}/exports")
async def list_exports(clip_id: UUID, exports: Exports) -> list[ExportDTO]:
    return [ExportDTO.from_job(job) for job in await exports.list_exports(clip_id)]


@router.get("/exports/{export_id}/{file}")
async def download(export_id: UUID, file: ExportFile, exports: Exports) -> FileResponse:
    path, filename = await exports.export_file(export_id, file)
    return FileResponse(path, filename=filename)
