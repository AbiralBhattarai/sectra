from pydantic import BaseModel, Field

from src.domain.enums.aspect_ratio_enum import AspectRatio
from src.domain.enums.caption_style_enum import CaptionStyle
from src.domain.enums.overlay_style_enum import OverlayStyle
from src.domain.models.character import CharacterTrack
from src.domain.models.speech import TimeSpan
from src.domain.models.transcript import Word


class Crop(BaseModel):
    """Centre of the crop window as fractions of the source frame, plus zoom."""

    x: float = Field(default=0.5, ge=0, le=1)
    y: float = Field(default=0.5, ge=0, le=1)
    scale: float = Field(default=1.0, ge=1)


class Facecam(BaseModel):
    """Streamer mode: the source region shown in a picture-in-picture box at the bottom
    right of the frame (the streamer's face cam) while the main frame shows gameplay.
    Centre as fractions of the source frame, plus zoom (the box's aspect is fixed)."""

    x: float = Field(default=0.85, ge=0, le=1)
    y: float = Field(default=0.85, ge=0, le=1)
    scale: float = Field(default=3.0, ge=1, le=8)


class Captions(BaseModel):
    #: Word timings on the source timeline; remapped to output time at render.
    words: list[Word]
    style: CaptionStyle = CaptionStyle.BOLD_HIGHLIGHT
    #: Bottom edge of the caption block as a fraction of the frame height (e.g. just
    #: above a narrator character); None = the style's own position.
    y: float | None = Field(default=None, ge=0.1, le=1)


class Overlay(BaseModel):
    """Free-positioned text; times are on the output (clip) timeline."""

    text: str = Field(max_length=200)
    start: float = Field(ge=0)
    end: float
    x: float = Field(default=0.5, ge=0, le=1)
    y: float = Field(default=0.12, ge=0, le=1)
    style: OverlayStyle = OverlayStyle.TITLE


class Music(BaseModel):
    #: File name in the music library.
    file: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
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


class Zoom(BaseModel):
    """A zoom-in on top of the framing, centred on the crop (so on the tracked face).
    Times are on the source timeline, like captions and shots."""

    start: float = Field(ge=0)
    end: float
    #: Magnification relative to the framed picture.
    scale: float = Field(default=1.15, ge=1, le=2)
    #: Seconds to ease in from 1x; 0 is a hard punch-in.
    ramp: float = Field(default=0, ge=0)


class Edl(BaseModel):
    """Edit decision list: everything needed to preview or render one clip."""

    aspect: AspectRatio = AspectRatio.VERTICAL
    crop: Crop = Field(default_factory=Crop)
    #: Left and right halves of the source stacked top/bottom (e.g. OmeTV's two cameras);
    #: ``crop`` frames each half the same way.
    split_screen: bool = False
    tracking: Tracking | None = None
    #: Kept stretches of the source, played back to back.
    ranges: list[TimeSpan]
    captions: Captions
    overlays: list[Overlay] = Field(default_factory=list)
    music: Music | None = None
    #: Sorted, non-overlapping; ignored with ``split_screen``.
    zooms: list[Zoom] = Field(default_factory=list)
    #: Streamer mode; when set, split screen and face tracking are ignored.
    facecam: Facecam | None = None
    #: Stories: the talking narrator, drawn over the picture and under the captions.
    character: CharacterTrack | None = None

    @classmethod
    def for_span(cls, span: TimeSpan, words: list[Word]) -> "Edl":
        """Untouched clip: one range, captioned with the words spoken inside it."""
        inside = [w for w in words if w.start >= span.start and w.end <= span.end]
        return cls(ranges=[span], captions=Captions(words=inside))
