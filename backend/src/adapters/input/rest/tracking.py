from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from src.adapters.input.rest.dependencies import get_clip_tracking
from src.application.dto.job import JobDTO
from src.domain.models.edl import Tracking
from src.ports.input.clip_tracking_port import ClipTrackingPort

router = APIRouter(prefix="/api", tags=["tracking"])

Trackings = Annotated[ClipTrackingPort, Depends(get_clip_tracking)]


@router.post("/clips/{clip_id}/tracking", status_code=status.HTTP_202_ACCEPTED)
async def request_tracking(clip_id: UUID, trackings: Trackings) -> JobDTO:
    return JobDTO.from_domain(await trackings.request_tracking(clip_id))


@router.get("/tracking/{job_id}")
async def tracking_result(job_id: UUID, trackings: Trackings) -> Tracking:
    return await trackings.tracking_result(job_id)
