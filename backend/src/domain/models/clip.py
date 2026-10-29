from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from src.domain.models.edl import Edl


def _now() -> datetime:
    return datetime.now(UTC)


class ClipCandidate(BaseModel):
    """A highlight the LLM proposed, referring to transcript segments by id."""

    start_segment: int
    end_segment: int
    title: str
    hook: str
    score: int = Field(ge=0, le=100)
    reason: str


class Clip(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    video_id: UUID
    title: str
    hook: str
    score: int
    reason: str
    #: Where the clip came from in the source; the EDL holds the edited version.
    start: float
    end: float
    edl: Edl
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
