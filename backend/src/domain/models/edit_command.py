"""Edit commands: every change to a clip's EDL is a list of these, applied in order by
``domain/services/edl_commands.py``. The editor and (later) an MCP server send the same
commands; descriptions double as the JSON Schema an LLM reads.

Conventions: items are addressed by id. "Output time" is seconds into the finished clip;
"source time" is seconds on a segment's video."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.domain.enums.aspect_ratio_enum import AspectRatio
from src.domain.enums.broll_layout_enum import BrollLayout
from src.domain.enums.caption_style_enum import CaptionStyle
from src.domain.enums.color_preset_enum import ColorPreset
from src.domain.enums.overlay_style_enum import OverlayStyle
from src.domain.enums.transition_type_enum import TransitionType
from src.domain.models.edl import SAFE_FILE_NAME, Color, Crop


class _Command(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Main track ------------------------------------------------------------------------


class Split(_Command):
    """Cut the main track in two at an output time."""

    op: Literal["split"] = "split"
    at: float = Field(ge=0, description="Output time to cut at")


class Trim(_Command):
    """Change where a segment starts/ends. Later segments move to close or open the gap
    (ripple). Video segments take source times; freeze and image segments a duration."""

    op: Literal["trim"] = "trim"
    segment_id: str
    start: float | None = Field(default=None, ge=0, description="New in point, source time")
    end: float | None = Field(default=None, ge=0, description="New out point, source time")
    duration: float | None = Field(
        default=None, gt=0, description="New length of a freeze or image segment (seconds)"
    )


class Delete(_Command):
    """Remove segments; the rest close up (ripple)."""

    op: Literal["delete"] = "delete"
    segment_ids: list[str] = Field(min_length=1)


class Move(_Command):
    """Reorder: move a segment to a new position on the main track."""

    op: Literal["move"] = "move"
    segment_id: str
    to_index: int = Field(ge=0, description="Position after the move; 0 = first")


class Duplicate(_Command):
    """Insert a copy of a segment (all its settings) right after it, or at ``to_index``."""

    op: Literal["duplicate"] = "duplicate"
    segment_id: str
    to_index: int | None = Field(
        default=None, ge=0, description="Position of the copy; omit for right after the original"
    )


class Insert(_Command):
    """Insert a stretch of video as a new segment."""

    op: Literal["insert"] = "insert"
    start: float = Field(ge=0, description="In point, source time")
    end: float = Field(gt=0, description="Out point, source time")
    media: UUID | None = Field(
        default=None, description="Video to take it from; omit for the clip's own video"
    )
    at_index: int | None = Field(
        default=None, ge=0, description="Position on the main track; omit to append"
    )


class InsertImage(_Command):
    """Insert a still image from the image library as a new segment."""

    op: Literal["insert_image"] = "insert_image"
    image: str = Field(pattern=SAFE_FILE_NAME, description="Image library file name")
    duration: float = Field(default=3.0, gt=0, le=60)
    at_index: int | None = Field(default=None, ge=0, description="Omit to append")


class FreezeFrame(_Command):
    """Hold the frame shown at an output time still for a while (the video splits around
    it and resumes afterwards)."""

    op: Literal["freeze_frame"] = "freeze_frame"
    at: float = Field(ge=0, description="Output time of the frame to freeze")
    duration: float = Field(default=1.0, gt=0, le=60)


class UpdateSegment(_Command):
    """Change properties of one or more segments; omitted fields stay as they are.
    Speed, volume and audio fades apply to video segments only."""

    op: Literal["update_segment"] = "update_segment"
    segment_ids: list[str] = Field(min_length=1)
    speed: float | None = Field(default=None, ge=0.25, le=4, description="Playback speed")
    volume: float | None = Field(default=None, ge=0, le=2, description="0 mutes, 1 = original")
    audio_fade_in: float | None = Field(default=None, ge=0, description="Seconds")
    audio_fade_out: float | None = Field(default=None, ge=0, description="Seconds")
    color: Color | None = Field(default=None, description="Colour grade (replaces the current one)")
    color_preset: ColorPreset | None = Field(
        default=None, description="Named look instead of color"
    )
    crop: Crop | None = Field(default=None, description="Framing for these segments only")
    crop_to: Crop | None = Field(
        default=None, description="Ken Burns: animate the framing from crop to this"
    )
    clear_crop: bool = Field(
        default=False, description="Drop crop and crop_to; follow the clip's framing again"
    )


class SetTransition(_Command):
    """Add or change the transition into a segment from the one before it."""

    op: Literal["set_transition"] = "set_transition"
    segment_id: str
    type: TransitionType = TransitionType.FADE
    duration: float = Field(
        default=0.5, gt=0, le=5, description="Seconds; at most half of either segment"
    )


class RemoveTransition(_Command):
    """Make the cut into a segment a hard cut again."""

    op: Literal["remove_transition"] = "remove_transition"
    segment_id: str


# --- Whole clip ------------------------------------------------------------------------


class UpdateClip(_Command):
    """Change clip-wide settings; omitted fields stay as they are."""

    op: Literal["update_clip"] = "update_clip"
    aspect: AspectRatio | None = None
    crop: Crop | None = Field(default=None, description="Default framing of the clip's video")
    split_screen: bool | None = Field(
        default=None, description="Stack the left half of the video over the right half"
    )
    tracking_enabled: bool | None = Field(
        default=None, description="Follow the active speaker (face tracking must have run)"
    )
    fade_in: float | None = Field(default=None, ge=0, le=5, description="From black, seconds")
    fade_out: float | None = Field(default=None, ge=0, le=5, description="To black, seconds")
    caption_style: CaptionStyle | None = None


class SetMusic(_Command):
    """Add background music (looped under the whole clip) or change it."""

    op: Literal["set_music"] = "set_music"
    file: str = Field(pattern=SAFE_FILE_NAME, description="Music library file name")
    volume: float = Field(default=0.15, ge=0, le=1)
    duck: bool = Field(default=True, description="Lower the music while someone speaks")


class RemoveMusic(_Command):
    op: Literal["remove_music"] = "remove_music"


# --- Captions --------------------------------------------------------------------------


class WordEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=0, description="Index into the caption words")
    text: str = Field(min_length=1, max_length=100)


class EditWords(_Command):
    """Correct the text of caption words (timing stays)."""

    op: Literal["edit_words"] = "edit_words"
    words: list[WordEdit] = Field(min_length=1)


class DeleteWords(_Command):
    """Hide caption words (the audio is unchanged)."""

    op: Literal["delete_words"] = "delete_words"
    indices: list[int] = Field(min_length=1)


class RestoreWords(_Command):
    """Refill captions from the transcript, discarding edits, between two source times
    (omit both for the whole clip)."""

    op: Literal["restore_words"] = "restore_words"
    start: float | None = Field(default=None, ge=0, description="Source time")
    end: float | None = Field(default=None, ge=0, description="Source time")


# --- Text overlays ---------------------------------------------------------------------


class AddOverlay(_Command):
    """Add on-screen text between two output times."""

    op: Literal["add_overlay"] = "add_overlay"
    text: str = Field(min_length=1, max_length=200)
    start: float = Field(ge=0, description="Output time")
    end: float = Field(gt=0, description="Output time")
    x: float = Field(default=0.5, ge=0, le=1, description="Centre, fraction of frame width")
    y: float = Field(default=0.12, ge=0, le=1, description="Centre, fraction of frame height")
    style: OverlayStyle = OverlayStyle.TITLE


class UpdateOverlay(_Command):
    op: Literal["update_overlay"] = "update_overlay"
    id: str
    text: str | None = Field(default=None, min_length=1, max_length=200)
    start: float | None = Field(default=None, ge=0)
    end: float | None = Field(default=None, gt=0)
    x: float | None = Field(default=None, ge=0, le=1)
    y: float | None = Field(default=None, ge=0, le=1)
    style: OverlayStyle | None = None


class RemoveOverlay(_Command):
    op: Literal["remove_overlay"] = "remove_overlay"
    id: str


# --- B-roll ----------------------------------------------------------------------------


class AddBroll(_Command):
    """Lay a video or image over the main track (full frame or picture-in-picture)."""

    op: Literal["add_broll"] = "add_broll"
    media: UUID | None = Field(default=None, description="Video id (give this or image)")
    image: str | None = Field(default=None, pattern=SAFE_FILE_NAME, description="Image file name")
    start: float = Field(ge=0, description="Output time")
    duration: float = Field(gt=0, description="Seconds")
    media_start: float = Field(default=0.0, ge=0, description="Where in the video to start")
    layout: BrollLayout = BrollLayout.FULL
    x: float = Field(default=0.72, ge=0, le=1, description="Picture-in-picture centre")
    y: float = Field(default=0.25, ge=0, le=1, description="Picture-in-picture centre")
    size: float = Field(default=0.4, ge=0.1, le=1, description="Picture-in-picture width")
    volume: float = Field(default=0.0, ge=0, le=2, description="Its own sound; 0 = silent")
    fade: float = Field(default=0.0, ge=0, description="Fade in and out, seconds")


class UpdateBroll(_Command):
    op: Literal["update_broll"] = "update_broll"
    id: str
    start: float | None = Field(default=None, ge=0)
    duration: float | None = Field(default=None, gt=0)
    media_start: float | None = Field(default=None, ge=0)
    layout: BrollLayout | None = None
    x: float | None = Field(default=None, ge=0, le=1)
    y: float | None = Field(default=None, ge=0, le=1)
    size: float | None = Field(default=None, ge=0.1, le=1)
    volume: float | None = Field(default=None, ge=0, le=2)
    fade: float | None = Field(default=None, ge=0)


class RemoveBroll(_Command):
    op: Literal["remove_broll"] = "remove_broll"
    id: str


# --- Markers ---------------------------------------------------------------------------


class AddMarker(_Command):
    op: Literal["add_marker"] = "add_marker"
    time: float = Field(ge=0, description="Output time")
    label: str = Field(default="", max_length=100)


class RemoveMarker(_Command):
    op: Literal["remove_marker"] = "remove_marker"
    id: str


# --- Face tracking ---------------------------------------------------------------------


class ReframeShot(_Command):
    """Move the framing of one face-tracking shot (zoom stays the clip's)."""

    op: Literal["reframe_shot"] = "reframe_shot"
    index: int = Field(ge=0, description="Index into the tracking shots")
    x: float = Field(ge=0, le=1, description="Crop centre, fraction of the video width")
    y: float = Field(ge=0, le=1, description="Crop centre, fraction of the video height")


EditCommand = Annotated[
    Split | Trim | Delete | Move | Duplicate | Insert | InsertImage | FreezeFrame
    | UpdateSegment | SetTransition | RemoveTransition
    | UpdateClip | SetMusic | RemoveMusic
    | EditWords | DeleteWords | RestoreWords
    | AddOverlay | UpdateOverlay | RemoveOverlay
    | AddBroll | UpdateBroll | RemoveBroll
    | AddMarker | RemoveMarker
    | ReframeShot,
    Field(discriminator="op"),
]  # fmt: skip
