from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from src.domain.models.clip import Clip
from src.domain.models.edl import Edl


class ClipDTO(BaseModel):
    id: UUID
    video_id: UUID
    title: str
    hook: str
    score: int
    reason: str
    start: float
    end: float
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, clip: Clip) -> "ClipDTO":
        return cls.model_validate(clip.model_dump(exclude={"edl"}))


class ClipDetailDTO(ClipDTO):
    edl: Edl

    @classmethod
    def from_domain(cls, clip: Clip) -> "ClipDetailDTO":
        return cls.model_validate(clip.model_dump())


class UpdateClipRequest(BaseModel):
    edl: Edl
