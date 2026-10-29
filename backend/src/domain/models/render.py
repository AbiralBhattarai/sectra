from pydantic import BaseModel

from src.domain.enums.caption_style_enum import CaptionStyle
from src.domain.models.edl import Overlay
from src.domain.models.speech import TimeSpan


class TimedText(BaseModel):
    text: str
    start: float
    end: float


class CaptionCue(BaseModel):
    """One page of captions on the output timeline; ``end`` includes the hold."""

    words: list[TimedText]
    start: float
    end: float


class CropBox(BaseModel):
    x: int
    y: int
    width: int
    height: int


class RenderPlan(BaseModel):
    """Everything the renderer needs, already resolved to output time and pixels."""

    ranges: list[TimeSpan]  # source time, played back to back
    crop: CropBox
    width: int
    height: int
    duration: float
    caption_style: CaptionStyle
    captions: list[CaptionCue]
    #: Always grouped like the "clean" style, for the downloadable .srt.
    subtitles: list[CaptionCue]
    overlays: list[Overlay]  # output time, clipped to the clip
    music_volume: float | None
    duck_music: bool
