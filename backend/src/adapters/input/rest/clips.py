from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends
from pydantic import TypeAdapter

from src.adapters.input.rest.dependencies import get_clip_editing
from src.application.dto.clip import (
    ClipDetailDTO,
    ClipDTO,
    EditRequest,
    HistoryStepRequest,
    UpdateClipRequest,
)
from src.domain.models.clip import Clip, ClipRevision
from src.domain.models.edit_command import EditCommand
from src.domain.models.timeline import TimelineView
from src.ports.input.clip_editing_port import ClipEditingPort

router = APIRouter(prefix="/api", tags=["clips"])

Clips = Annotated[ClipEditingPort, Depends(get_clip_editing)]

_COMMAND_SCHEMA = TypeAdapter(EditCommand).json_schema()


@router.get("/videos/{video_id}/clips")
async def list_clips(video_id: UUID, clips: Clips) -> list[ClipDTO]:
    return [ClipDTO.from_domain(clip) for clip in await clips.list_for_video(video_id)]


@router.get("/clips/{clip_id}")
async def get_clip(clip_id: UUID, clips: Clips) -> ClipDetailDTO:
    return await _detail(clips, await clips.get(clip_id))


@router.put("/clips/{clip_id}")
async def update_clip(clip_id: UUID, body: UpdateClipRequest, clips: Clips) -> ClipDetailDTO:
    """Replace the whole EDL (one undoable revision)."""
    clip = await clips.update_edl(clip_id, body.edl, body.base_revision, body.actor)
    return await _detail(clips, clip)


@router.post("/clips/{clip_id}/edits")
async def edit_clip(clip_id: UUID, body: EditRequest, clips: Clips) -> ClipDetailDTO:
    """Apply edit commands in order as one revision (see ``/api/edit-commands/schema``)."""
    clip = await clips.apply_edits(
        clip_id, body.commands, body.base_revision, body.dry_run, body.actor
    )
    return await _detail(clips, clip)


@router.post("/clips/{clip_id}/undo")
async def undo(
    clip_id: UUID, clips: Clips, body: Annotated[HistoryStepRequest | None, Body()] = None
) -> ClipDetailDTO:
    clip = await clips.undo(clip_id, (body or HistoryStepRequest()).actor)
    return await _detail(clips, clip)


@router.post("/clips/{clip_id}/redo")
async def redo(
    clip_id: UUID, clips: Clips, body: Annotated[HistoryStepRequest | None, Body()] = None
) -> ClipDetailDTO:
    clip = await clips.redo(clip_id, (body or HistoryStepRequest()).actor)
    return await _detail(clips, clip)


@router.get("/clips/{clip_id}/timeline")
async def timeline(clip_id: UUID, clips: Clips) -> TimelineView:
    """The clip's timeline resolved to output times, with the text of each segment."""
    return await clips.describe(clip_id)


@router.get("/clips/{clip_id}/history")
async def history(clip_id: UUID, clips: Clips) -> list[ClipRevision]:
    return await clips.history(clip_id)


@router.get("/edit-commands/schema")
async def command_schema() -> dict[str, Any]:
    """JSON Schema of one edit command (a union discriminated by ``op``)."""
    return _COMMAND_SCHEMA


async def _detail(clips: ClipEditingPort, clip: Clip) -> ClipDetailDTO:
    """With can_undo/can_redo, so the editor needn't ask separately."""
    return ClipDetailDTO.from_domain(clip, await clips.history(clip.id))
