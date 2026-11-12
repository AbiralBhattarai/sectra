from typing import Literal

from pydantic import BaseModel

from src.domain.enums.caption_style_enum import CaptionStyle
from src.domain.models.edl import Color, Overlay, Transition


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


class CropMove(BaseModel):
    """From output time ``time`` on, the crop window's top-left is at (x, y)."""

    time: float
    x: int
    y: int


class MediaSource(BaseModel):
    """What the worker probed about one input of a render."""

    width: int
    height: int
    has_audio: bool


class PlannedSegment(BaseModel):
    """One main-track segment, resolved to an input, a source window and output time."""

    #: Key into the render's inputs (``render_planning.media_key``).
    input: str
    kind: Literal["video", "freeze", "image"]
    #: Media seconds to read from: a video's in point, a freeze's frame; 0 for images.
    source_start: float
    #: Media seconds to read (0 for a freeze frame).
    source_duration: float
    #: Output seconds it lasts (before the transition overlap).
    length: float
    speed: float = 1.0
    #: False for freezes, images and silent videos; their sound is silence.
    has_audio: bool
    volume: float = 1.0
    audio_fade_in: float = 0.0
    audio_fade_out: float = 0.0
    #: Source windows stacked top to bottom: one, or two for a split screen.
    crops: list[CropBox]
    #: Ken Burns: the window it animates to (single pane only).
    crop_to: CropBox | None = None
    #: Face tracking: where the crop jumps, in output seconds from the segment's start.
    crop_moves: list[CropMove] = []
    source_width: int
    source_height: int
    color: Color | None = None
    #: Into this segment from the previous one.
    transition: Transition | None = None
    #: Output time it starts at (its transition overlap included).
    offset: float


class PlannedBroll(BaseModel):
    input: str
    kind: Literal["video", "image"]
    start: float
    duration: float
    media_start: float
    #: Source window used (whole picture for picture-in-picture, cover crop for full).
    crop: CropBox
    #: Where it lands in the output frame.
    x: int
    y: int
    width: int
    height: int
    volume: float
    has_audio: bool
    fade: float


class RenderPlan(BaseModel):
    """Everything the renderer needs, already resolved to output time and pixels."""

    segments: list[PlannedSegment]
    broll: list[PlannedBroll] = []
    width: int
    height: int
    duration: float
    fade_in: float = 0.0
    fade_out: float = 0.0
    caption_style: CaptionStyle
    captions: list[CaptionCue]
    #: Always grouped like the "clean" style, for the downloadable .srt.
    subtitles: list[CaptionCue]
    overlays: list[Overlay]  # output time, clipped to the clip
    music_volume: float | None
    duck_music: bool
