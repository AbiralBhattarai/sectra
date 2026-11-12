from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Discriminator, Field, Tag, model_validator

from src.domain.enums.aspect_ratio_enum import AspectRatio
from src.domain.enums.broll_layout_enum import BrollLayout
from src.domain.enums.caption_style_enum import CaptionStyle
from src.domain.enums.overlay_style_enum import OverlayStyle
from src.domain.enums.transition_type_enum import TransitionType
from src.domain.models.speech import TimeSpan
from src.domain.models.transcript import Word

#: File names in the image and music libraries.
SAFE_FILE_NAME = r"^[A-Za-z0-9][A-Za-z0-9._-]*$"


def new_id() -> str:
    """Short id for an item of an EDL; commands (and LLMs) address items by it."""
    return uuid4().hex[:8]


class Crop(BaseModel):
    """Centre of the crop window as fractions of the source frame, plus zoom."""

    x: float = Field(default=0.5, ge=0, le=1)
    y: float = Field(default=0.5, ge=0, le=1)
    scale: float = Field(default=1.0, ge=1, le=5)


class Color(BaseModel):
    """A colour grade with CSS ``filter`` semantics, applied in this order:
    brightness, contrast, saturate, sepia, hue-rotate. 1/1/1/0/0 changes nothing."""

    brightness: float = Field(default=1.0, ge=0, le=2, description="Multiplier; 1 = unchanged")
    contrast: float = Field(default=1.0, ge=0, le=2, description="1 = unchanged, 0 = flat grey")
    saturation: float = Field(default=1.0, ge=0, le=3, description="0 = black and white")
    sepia: float = Field(default=0.0, ge=0, le=1, description="0..1 amount of sepia tone")
    hue: float = Field(default=0.0, ge=-180, le=180, description="Hue rotation in degrees")

    @property
    def neutral(self) -> bool:
        return self == Color()


class Transition(BaseModel):
    """Blends the end of the previous segment into the start of this one; the two overlap
    for ``duration`` seconds, so the clip gets that much shorter."""

    type: TransitionType = TransitionType.FADE
    duration: float = Field(default=0.5, gt=0, le=5)


class _SegmentBase(BaseModel):
    id: str = Field(default_factory=new_id)
    color: Color = Field(default_factory=Color)
    #: Framing for this segment only; None uses ``Edl.crop`` (or face tracking).
    crop: Crop | None = None
    #: Into this segment from the previous one; ignored on the first segment.
    transition: Transition | None = None


class VideoSegment(_SegmentBase):
    """A stretch of a video, played back at ``speed``."""

    kind: Literal["video"] = "video"
    #: The video it comes from; None = the clip's own video.
    media: UUID | None = None
    #: Seconds on that video's timeline.
    start: float = Field(ge=0)
    end: float
    speed: float = Field(default=1.0, ge=0.25, le=4)
    volume: float = Field(default=1.0, ge=0, le=2)
    audio_fade_in: float = Field(default=0.0, ge=0)
    audio_fade_out: float = Field(default=0.0, ge=0)
    #: Ken Burns: the framing animates from ``crop`` to this over the segment.
    crop_to: Crop | None = None

    @model_validator(mode="after")
    def _ordered(self) -> "VideoSegment":
        if self.end <= self.start:
            raise ValueError(f"segment ends ({self.end}) before it starts ({self.start})")
        return self


class FreezeSegment(_SegmentBase):
    """One frame of a video held still (silent) for ``duration`` seconds."""

    kind: Literal["freeze"] = "freeze"
    media: UUID | None = None
    #: Source time of the frame.
    at: float = Field(ge=0)
    duration: float = Field(gt=0, le=60)


class ImageSegment(_SegmentBase):
    """A still image from the image library, shown (silent) for ``duration`` seconds."""

    kind: Literal["image"] = "image"
    image: str = Field(pattern=SAFE_FILE_NAME)
    duration: float = Field(gt=0, le=60)
    crop_to: Crop | None = None


def _segment_kind(value: object) -> str:
    """``kind`` may be left out of a video segment."""
    if isinstance(value, dict):
        return value.get("kind", "video")
    return getattr(value, "kind", "video")


Segment = Annotated[
    Annotated[VideoSegment, Tag("video")]
    | Annotated[FreezeSegment, Tag("freeze")]
    | Annotated[ImageSegment, Tag("image")],
    Discriminator(_segment_kind),
]


class Captions(BaseModel):
    #: Word timings on the clip video's source timeline; each segment shows the words
    #: inside it, remapped to output time.
    words: list[Word]
    style: CaptionStyle = CaptionStyle.BOLD_HIGHLIGHT


class Overlay(BaseModel):
    """Free-positioned text; times are on the output (clip) timeline."""

    id: str = Field(default_factory=new_id)
    text: str = Field(max_length=200)
    start: float = Field(ge=0)
    end: float
    x: float = Field(default=0.5, ge=0, le=1)
    y: float = Field(default=0.12, ge=0, le=1)
    style: OverlayStyle = OverlayStyle.TITLE


class BrollItem(BaseModel):
    """A video or image laid over the main track; times are on the output timeline."""

    id: str = Field(default_factory=new_id)
    #: Exactly one of ``media`` (a video) and ``image`` (image library file).
    media: UUID | None = None
    image: str | None = Field(default=None, pattern=SAFE_FILE_NAME)
    start: float = Field(ge=0)
    duration: float = Field(gt=0)
    #: Where in the video it starts playing (seconds); ignored for images.
    media_start: float = Field(default=0.0, ge=0)
    layout: BrollLayout = BrollLayout.FULL
    #: Centre of a picture-in-picture box as fractions of the frame.
    x: float = Field(default=0.72, ge=0, le=1)
    y: float = Field(default=0.25, ge=0, le=1)
    #: Picture-in-picture width as a fraction of the frame width.
    size: float = Field(default=0.4, ge=0.1, le=1)
    #: Its own audio; 0 keeps only the main track's sound.
    volume: float = Field(default=0.0, ge=0, le=2)
    #: Fade in and out (seconds).
    fade: float = Field(default=0.0, ge=0)

    @model_validator(mode="after")
    def _one_source(self) -> "BrollItem":
        if (self.media is None) == (self.image is None):
            raise ValueError("B-roll needs exactly one of media or image")
        return self

    @property
    def end(self) -> float:
        return self.start + self.duration


class Marker(BaseModel):
    id: str = Field(default_factory=new_id)
    #: Output time.
    time: float = Field(ge=0)
    label: str = Field(default="", max_length=100)


class Music(BaseModel):
    #: File name in the music library.
    file: str = Field(pattern=SAFE_FILE_NAME)
    volume: float = Field(default=0.15, ge=0, le=1)
    duck: bool = True


class Shot(BaseModel):
    """One camera position chosen by face tracking; runs until the next shot starts."""

    #: Source time.
    start: float
    #: The tracked face this shot frames (for labels only).
    face: int
    #: Crop centre as fractions of the source frame; zoom is the shared ``Edl.crop.scale``.
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class Tracking(BaseModel):
    """Active-speaker framing: hard cuts between shots of whoever is talking."""

    #: The checkbox; the shots are kept while it is off.
    enabled: bool = True
    #: Source span the tracker analysed.
    span: TimeSpan
    #: Sorted by start; the first starts at ``span.start``.
    shots: list[Shot]


class Edl(BaseModel):
    """Edit decision list: everything needed to preview or render one clip.

    ``segments`` is the main track, played back to back (transitions overlap
    neighbours). Overlays, B-roll and markers are placed on the output timeline."""

    version: Literal[2] = 2
    aspect: AspectRatio = AspectRatio.VERTICAL
    crop: Crop = Field(default_factory=Crop)
    #: Left and right halves of the source stacked top/bottom (e.g. OmeTV's two cameras);
    #: the crop frames each half the same way. Clip-video segments only.
    split_screen: bool = False
    #: Clip-video segments without their own crop follow it.
    tracking: Tracking | None = None
    segments: list[Segment]
    captions: Captions
    overlays: list[Overlay] = Field(default_factory=list)
    broll: list[BrollItem] = Field(default_factory=list)
    markers: list[Marker] = Field(default_factory=list)
    music: Music | None = None
    #: Whole clip, from/to black (picture) and silence (sound).
    fade_in: float = Field(default=0.0, ge=0, le=5)
    fade_out: float = Field(default=0.0, ge=0, le=5)

    @classmethod
    def for_span(cls, span: TimeSpan, words: list[Word]) -> "Edl":
        """Untouched clip: one segment, captioned with the words spoken inside it."""
        inside = [w for w in words if w.start >= span.start and w.end <= span.end]
        return cls(
            segments=[VideoSegment(start=span.start, end=span.end)],
            captions=Captions(words=inside),
        )
