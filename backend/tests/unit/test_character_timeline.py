"""Mirrored by frontend/src/editor/character.test.ts — keep the cases identical."""

import pytest

from src.domain.enums.aspect_ratio_enum import AspectRatio
from src.domain.enums.emotion_enum import Emotion
from src.domain.models.character import CharacterTrack, Mood, MouthCue
from src.domain.services.character_timeline import (
    blink_starts,
    blinking,
    bob_at,
    character_box,
    character_state,
    merge_moods,
    mouth_at,
)

CUES = [
    MouthCue(start=0.0, end=0.3, shape="X"),
    MouthCue(start=0.3, end=0.5, shape="B"),
    MouthCue(start=0.5, end=0.9, shape="D"),
]


def test_box_is_centred_and_even_sized():
    track = CharacterTrack(name="guy")  # x .5, y .78, scale .42
    assert character_box(AspectRatio.VERTICAL, track) == (271, 1095, 538, 806)
    assert character_box(AspectRatio.SQUARE, CharacterTrack(name="guy", scale=0.5, x=0.2)) == (
        36,
        572,
        360,
        540,
    )


def test_mouth_follows_cues_and_rests_outside_them():
    assert mouth_at(CUES, 0.0) == "X"
    assert mouth_at(CUES, 0.35) == "B"
    assert mouth_at(CUES, 0.5) == "D"
    assert mouth_at(CUES, 0.95) == "X"
    assert mouth_at([], 1.0) == "X"


def test_blinks_are_deterministic_two_to_five_seconds_apart():
    starts = blink_starts(30)
    assert starts[:3] == [2.0, 6.762, 9.63]
    gaps = [b - a for a, b in zip([0.0, *starts], starts, strict=False)]
    assert all(2 <= g <= 5 for g in gaps)
    assert blinking(starts, 2.05) and not blinking(starts, 2.2) and not blinking(starts, 1.0)


def test_bob_is_a_gentle_sine():
    assert bob_at(0) == 0
    assert bob_at(0.5) == pytest.approx(0.008)
    assert bob_at(1.5) == pytest.approx(-0.008)


def test_state_combines_mood_mouth_and_blink():
    moods = [Mood(start=0.4, end=3, emotion=Emotion.SHOCKED)]
    state = character_state(CUES, moods, blink_starts(10), 0.6)
    assert (state.expression, state.mouth, state.blink) == (Emotion.SHOCKED, "D", False)
    assert character_state(CUES, moods, [], 3.5).expression is Emotion.NEUTRAL


def test_moods_merge_drop_neutral_and_flickers():
    merged = merge_moods(
        [
            (0, 3, Emotion.HAPPY),
            (3.5, 6, Emotion.HAPPY),  # joins the first
            (6, 7, Emotion.NEUTRAL),  # dropped
            (8, 9, Emotion.SAD),  # too short
            (10, 14, Emotion.ANGRY),
        ]
    )
    assert [(m.start, m.end, m.emotion) for m in merged] == [
        (0, 6, Emotion.HAPPY),
        (10, 14, Emotion.ANGRY),
    ]
