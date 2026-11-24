"""What the narrator character looks like at a given moment. Mirrors
frontend/src/editor/character.ts — change both together (the tests are mirrored), or
the export won't match the preview."""

import math
from bisect import bisect_right
from dataclasses import dataclass

from src.domain.enums.aspect_ratio_enum import AspectRatio
from src.domain.enums.emotion_enum import Emotion
from src.domain.models.character import CANVAS_ASPECT, CharacterTrack, Mood, MouthCue
from src.domain.services.framing import OUTPUT_SIZES

#: Rest mouth, used between cues and when there is no lip sync at all.
REST = "X"
BLINK_SECONDS = 0.12
#: Blinks start every 2–5 s (deterministic, so preview and render agree).
_BLINK_MIN, _BLINK_SPREAD = 2.0, 3.0
#: Park–Miller generator: exact in both Python ints and JS doubles.
_PM_MODULUS, _PM_MULTIPLIER, _PM_SEED = 2147483647, 16807, 7
#: Gentle idle bob: this share of the box height, this many cycles per second.
BOB_AMPLITUDE, BOB_HZ = 0.008, 0.5
#: Moods shorter than this after merging are dropped (a face flicker looks like a glitch).
MIN_MOOD_SECONDS = 1.5
#: Same-emotion moods closer than this merge into one.
_MOOD_JOIN_GAP = 1.0


@dataclass(frozen=True)
class CharacterState:
    expression: Emotion
    mouth: str
    blink: bool
    #: Vertical offset as a fraction of the box height (positive = down).
    bob: float


def character_box(aspect: AspectRatio, track: CharacterTrack) -> tuple[int, int, int, int]:
    """(x, y, width, height) of the character's box in output pixels; may reach past the
    frame edges (the overlay clips it)."""
    out_width, out_height = OUTPUT_SIZES[aspect]
    height = _even(track.scale * out_height)
    width = _even(height * CANVAS_ASPECT)
    x = math.floor(track.x * out_width - width / 2 + 0.5)
    y = math.floor(track.y * out_height - height / 2 + 0.5)
    return x, y, width, height


def mouth_at(cues: list[MouthCue], t: float) -> str:
    """The mouth shape at source time ``t``; cues are sorted and non-overlapping."""
    index = bisect_right([c.start for c in cues], t) - 1
    if index >= 0 and t < cues[index].end:
        return cues[index].shape
    return REST


def mood_at(moods: list[Mood], t: float) -> Emotion:
    for mood in moods:
        if mood.start <= t < mood.end:
            return mood.emotion
    return Emotion.NEUTRAL


def blink_starts(until: float) -> list[float]:
    """Source times at which the character blinks, from 0 up to ``until``."""
    starts: list[float] = []
    seed = _PM_SEED
    t = 0.0
    while True:
        seed = seed * _PM_MULTIPLIER % _PM_MODULUS
        t += _BLINK_MIN + _BLINK_SPREAD * seed / _PM_MODULUS
        if t > until:
            return starts
        starts.append(round(t, 3))


def blinking(starts: list[float], t: float) -> bool:
    index = bisect_right(starts, t) - 1
    return index >= 0 and t < starts[index] + BLINK_SECONDS


def bob_at(t: float) -> float:
    return BOB_AMPLITUDE * math.sin(2 * math.pi * BOB_HZ * t)


def character_state(
    cues: list[MouthCue], moods: list[Mood], blinks: list[float], t: float
) -> CharacterState:
    """Everything that changes over time, at source time ``t``."""
    return CharacterState(
        expression=mood_at(moods, t),
        mouth=mouth_at(cues, t),
        blink=blinking(blinks, t),
        bob=bob_at(t),
    )


def merge_moods(spans: list[tuple[float, float, Emotion]]) -> list[Mood]:
    """Per-segment emotions → sorted, non-overlapping moods: neutral ones dropped,
    neighbours with the same emotion joined, flickers shorter than
    ``MIN_MOOD_SECONDS`` dropped."""
    merged: list[list] = []
    for start, end, emotion in sorted(spans):
        if emotion is Emotion.NEUTRAL or end <= start:
            continue
        if merged and merged[-1][1] > start:
            start = merged[-1][1]  # overlapping input: the earlier one keeps its time
            if end <= start:
                continue
        last = merged[-1] if merged else None
        if last and last[2] is emotion and start - last[1] <= _MOOD_JOIN_GAP:
            last[1] = end
        else:
            merged.append([start, end, emotion])
    return [
        Mood(start=round(s, 3), end=round(e, 3), emotion=emotion)
        for s, e, emotion in merged
        if e - s >= MIN_MOOD_SECONDS
    ]


def _even(value: float) -> int:
    return max(2, math.floor(value / 2 + 0.5) * 2)
