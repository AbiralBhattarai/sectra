from pydantic import BaseModel

from src.domain.enums.caption_style_enum import CaptionStyle
from src.domain.models.character import Mood, MouthCue
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


class CropMove(BaseModel):
    """From output time ``time`` on, the crop window's top-left is at (x, y)."""

    time: float
    x: int
    y: int


class ZoomCue(BaseModel):
    """A zoom on the output timeline (see ``Edl.zooms``)."""

    start: float
    end: float
    scale: float
    ramp: float


class PipBox(BaseModel):
    """Streamer mode: ``source`` (a source window) drawn at ``x, y`` (output pixels)
    scaled to ``width x height``, over the main picture and under the captions."""

    source: CropBox
    x: int
    y: int
    width: int
    height: int


class CharacterPlan(BaseModel):
    """The narrator to draw: ``name``'s layers in a ``width x height`` box whose top-left
    is ``x, y`` (output pixels). Its state at each output frame comes from
    ``character_timeline.character_state`` over the source-time cues and moods."""

    name: str
    x: int
    y: int
    width: int
    height: int
    cues: list[MouthCue]
    moods: list[Mood]


class RenderPlan(BaseModel):
    """Everything the renderer needs, already resolved to output time and pixels."""

    ranges: list[TimeSpan]  # source time, played back to back
    #: Source windows stacked top to bottom: one, or two for a split screen.
    crops: list[CropBox]
    #: Face tracking: where the (single) crop jumps; empty when it never moves.
    crop_moves: list[CropMove] = []
    #: Zoom-ins over the framed picture, output time; empty for a split screen.
    zooms: list[ZoomCue] = []
    #: Streamer mode's facecam box (then ``crops`` holds just the gameplay window).
    pip: PipBox | None = None
    width: int
    height: int
    duration: float
    caption_style: CaptionStyle
    #: Bottom of the caption block as a fraction of the height; None = the style's spot.
    caption_y: float | None = None
    captions: list[CaptionCue]
    #: Always grouped like the "clean" style, for the downloadable .srt.
    subtitles: list[CaptionCue]
    overlays: list[Overlay]  # output time, clipped to the clip
    music_volume: float | None
    character: CharacterPlan | None = None
    duck_music: bool
