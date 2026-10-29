from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import FileResponse

from src.adapters.input.rest.dependencies import get_clip_export
from src.application.dto.export import ExportDTO
from src.ports.input.clip_export_port import ClipExportPort, ExportFile

router = APIRouter(prefix="/api", tags=["exports"])

Exports = Annotated[ClipExportPort, Depends(get_clip_export)]


@router.post("/clips/{clip_id}/exports", status_code=status.HTTP_202_ACCEPTED)
async def request_export(clip_id: UUID, exports: Exports) -> ExportDTO:
    return ExportDTO.from_job(await exports.request_export(clip_id))


@router.get("/clips/{clip_id}/exports")
async def list_exports(clip_id: UUID, exports: Exports) -> list[ExportDTO]:
    return [ExportDTO.from_job(job) for job in await exports.list_exports(clip_id)]


@router.get("/exports/{export_id}/{file}")
async def download(export_id: UUID, file: ExportFile, exports: Exports) -> FileResponse:
    path, filename = await exports.export_file(export_id, file)
    return FileResponse(path, filename=filename)
