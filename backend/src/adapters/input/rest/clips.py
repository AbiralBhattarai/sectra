from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from src.adapters.input.rest.dependencies import get_clip_editing
from src.application.dto.clip import ClipDetailDTO, ClipDTO, UpdateClipRequest
from src.ports.input.clip_editing_port import ClipEditingPort

router = APIRouter(prefix="/api", tags=["clips"])

Clips = Annotated[ClipEditingPort, Depends(get_clip_editing)]


@router.get("/videos/{video_id}/clips")
async def list_clips(video_id: UUID, clips: Clips) -> list[ClipDTO]:
    return [ClipDTO.from_domain(clip) for clip in await clips.list_for_video(video_id)]


@router.get("/clips/{clip_id}")
async def get_clip(clip_id: UUID, clips: Clips) -> ClipDetailDTO:
    return ClipDetailDTO.from_domain(await clips.get(clip_id))


@router.put("/clips/{clip_id}")
async def update_clip(clip_id: UUID, body: UpdateClipRequest, clips: Clips) -> ClipDetailDTO:
    return ClipDetailDTO.from_domain(await clips.update_edl(clip_id, body.edl))
