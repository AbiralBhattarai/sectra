"""Everything broadcast to the UI over pub/sub (and relayed as SSE)."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, TypeAdapter

from src.domain.models.job import JobEvent


class ClipEvent(BaseModel):
    """A clip's EDL changed (an edit, undo/redo, or face tracking applied)."""

    kind: Literal["clip"] = "clip"
    clip_id: UUID
    video_id: UUID
    revision: int
    actor: str


AppEvent = Annotated[JobEvent | ClipEvent, Field(discriminator="kind")]

_ADAPTER: TypeAdapter[JobEvent | ClipEvent] = TypeAdapter(AppEvent)


def parse_event(data: str | bytes) -> JobEvent | ClipEvent:
    return _ADAPTER.validate_json(data)
