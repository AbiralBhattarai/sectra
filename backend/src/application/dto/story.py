from pydantic import BaseModel, Field

from src.domain.models.background import Background, PendingBackground
from src.domain.models.story import STORY_TEXT_MAX, BackgroundMode, StorySpec


class CreateStoryRequest(BaseModel):
    text: str = Field(min_length=1, max_length=STORY_TEXT_MAX)
    title: str = Field(default="", max_length=200)
    polish: bool = False
    voice: str = "af_heart"
    speed: float = Field(default=1.0, ge=0.7, le=1.5)
    background_mode: BackgroundMode = "black"
    background: str | None = None
    category: str | None = None
    character: str | None = "guy"

    def to_spec(self) -> StorySpec:
        return StorySpec(**self.model_dump())


class AddBackgroundRequest(BaseModel):
    url: str = Field(min_length=1, pattern=r"^https?://")
    category: str = Field(min_length=1, max_length=40)


class BackgroundDTO(BaseModel):
    category: str
    file: str
    name: str
    #: What a story's ``background`` field takes: "<category>/<file>".
    ref: str

    @classmethod
    def from_domain(cls, background: Background) -> "BackgroundDTO":
        return cls(**background.model_dump(), ref=background.ref)


class BackgroundLibraryDTO(BaseModel):
    ready: list[BackgroundDTO]
    pending: list[PendingBackground]
