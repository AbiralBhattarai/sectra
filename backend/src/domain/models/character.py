from typing import Literal

from pydantic import BaseModel, Field

from src.domain.enums.emotion_enum import Emotion

#: Every character's layers share one canvas of this width:height (1000×1500 bundled).
CANVAS_ASPECT = 2 / 3

#: Rhubarb Lip Sync's mouth shapes. A–F are the basic set; G, H and X (rest) are extended.
MouthShape = Literal["A", "B", "C", "D", "E", "F", "G", "H", "X"]
MOUTH_SHAPES: tuple[str, ...] = ("A", "B", "C", "D", "E", "F", "G", "H", "X")


class MouthCue(BaseModel):
    """From ``start`` to ``end`` (source time) the mouth has ``shape``."""

    start: float
    end: float
    shape: MouthShape


class LipSync(BaseModel):
    """``lipsync.json``: the narrator's mouth over the whole narration."""

    cues: list[MouthCue]


class Mood(BaseModel):
    """The character's expression from ``start`` to ``end`` (source time)."""

    start: float = Field(ge=0)
    end: float
    emotion: Emotion


class CharacterTrack(BaseModel):
    """The talking narrator drawn over the picture (under the captions). The box is
    centred at (x, y), fractions of the frame, and ``scale`` of the frame tall."""

    name: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,39}$")
    x: float = Field(default=0.5, ge=0, le=1)
    y: float = Field(default=0.78, ge=0, le=1)
    scale: float = Field(default=0.42, ge=0.1, le=1)
    enabled: bool = True
    #: Sorted, non-overlapping; gaps are neutral.
    moods: list[Mood] = Field(default_factory=list)
