from uuid import UUID

import pytest

from src.domain.exceptions import AppValidationException
from src.domain.models.edl import (
    BrollItem,
    FreezeSegment,
    ImageSegment,
    Marker,
    Overlay,
    Shot,
    Tracking,
    Transition,
)
from src.domain.models.speech import TimeSpan
from src.domain.services.edl_rules import edl_bounds, validate_edl
from tests.unit.edl_builders import edl, seg

OTHER = UUID("00000000-0000-0000-0000-00000000000a")


def test_valid_edits_may_reorder_and_repeat_the_source():
    validate_edl(edl((12, 20), (1, 5), (1, 5)), source_duration=30)


@pytest.mark.parametrize(
    ("clip", "message"),
    [
        (edl(), "at least one segment"),
        (edl((1, 1.05)), "shorter than"),
        (edl((25, 31)), "runs past the end of its video"),
        (edl((1, 5), FreezeSegment(at=40, duration=1)), "runs past the end"),
        (edl(seg(1, 5, media=OTHER)), "isn't ready"),
        (edl((1, 2), seg(5, 6, transition=Transition(duration=0.6))), "longer than half"),
        (edl(seg(1, 2, audio_fade_in=0.6, audio_fade_out=0.6)), "audio fades"),
        (edl((1, 3), fade_in=1.5, fade_out=1), "fade in and fade out"),
        (edl(seg(1, 3, id="a"), seg(4, 6, id="a")), "share the id a"),
    ],
)
def test_invalid_edits_are_rejected(clip, message):
    with pytest.raises(AppValidationException, match=message):
        validate_edl(clip, source_duration=30)


def test_other_videos_are_checked_against_their_own_length():
    validate_edl(edl(seg(1, 5, media=OTHER)), 30, {OTHER: 6})
    with pytest.raises(AppValidationException, match="runs past"):
        validate_edl(edl(seg(1, 7, media=OTHER)), 30, {OTHER: 6})
    broll = BrollItem(media=OTHER, start=0, duration=3, media_start=4)
    with pytest.raises(AppValidationException, match="B-roll 1"):
        validate_edl(edl((0, 5), broll=[broll]), 30, {OTHER: 6})


def test_items_past_the_end_of_the_clip_are_allowed():
    """The render drops or cuts them, so shortening a clip never fails on them."""
    validate_edl(
        edl(
            (0, 2),
            overlays=[Overlay(text="Late", start=5, end=7)],
            broll=[BrollItem(image="a.png", start=4, duration=1)],
            markers=[Marker(time=9)],
        ),
        30,
    )


def test_bounds_span_the_clip_videos_first_and_last_second():
    assert edl_bounds(edl((9, 14), (3, 5), FreezeSegment(at=20, duration=1))) == TimeSpan(
        start=3, end=20
    )
    assert edl_bounds(edl(ImageSegment(image="a.png", duration=2))) is None


def test_overlays_need_text_and_positive_length():
    base = edl((0, 10))
    validate_edl(base.model_copy(update={"overlays": [Overlay(text="Hi", start=0, end=2)]}), 30)
    with pytest.raises(AppValidationException, match="no text"):
        validate_edl(base.model_copy(update={"overlays": [Overlay(text="  ", start=0, end=2)]}), 30)
    with pytest.raises(AppValidationException, match="ends before it starts"):
        validate_edl(base.model_copy(update={"overlays": [Overlay(text="Hi", start=3, end=3)]}), 30)


@pytest.mark.parametrize(
    ("starts", "message"),
    [
        ((), "no shots"),
        ((2, 5), "start where tracking does"),
        ((1, 5, 5), "in order"),
    ],
)
def test_bad_shots_are_rejected(starts, message):
    tracked = edl((1, 9)).model_copy(
        update={
            "tracking": Tracking(
                span=TimeSpan(start=1, end=9),
                shots=[Shot(start=s, face=0, x=0.5, y=0.5) for s in starts],
            )
        }
    )
    with pytest.raises(AppValidationException, match=message):
        validate_edl(tracked, source_duration=30)
