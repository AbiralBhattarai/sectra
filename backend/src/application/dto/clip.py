from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from src.domain.models.clip import Clip, ClipRevision
from src.domain.models.edit_command import EditCommand
from src.domain.models.edl import Edl

#: Who made an edit, as recorded in the clip's history ("editor", "mcp", …).
Actor = Field(default="editor", pattern=r"^[a-z0-9_-]{1,32}$")


class ClipDTO(BaseModel):
    id: UUID
    video_id: UUID
    title: str
    hook: str
    score: int
    reason: str
    start: float
    end: float
    revision: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, clip: Clip) -> "ClipDTO":
        return cls.model_validate(clip.model_dump(exclude={"edl"}))


class ClipDetailDTO(ClipDTO):
    edl: Edl
    can_undo: bool
    can_redo: bool

    @classmethod
    def from_domain(cls, clip: Clip, history: list[ClipRevision]) -> "ClipDetailDTO":
        revisions = {r.revision for r in history}
        return cls.model_validate(
            {
                **clip.model_dump(),
                "can_undo": clip.revision - 1 in revisions,
                "can_redo": clip.revision + 1 in revisions,
            }
        )


class UpdateClipRequest(BaseModel):
    edl: Edl
    base_revision: int | None = None
    actor: str = Actor


class EditRequest(BaseModel):
    commands: list[EditCommand] = Field(min_length=1)
    #: The revision the commands were made against; stale → 409. Omit to apply to the
    #: latest (commands address items by id, so that's usually safe).
    base_revision: int | None = None
    #: Return the result without saving it.
    dry_run: bool = False
    actor: str = Actor


class HistoryStepRequest(BaseModel):
    actor: str = Actor
