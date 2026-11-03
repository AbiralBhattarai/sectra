import pytest

from src.domain.exceptions import AppValidationException
from src.domain.models.edl import Captions, Edl, Overlay, Shot, Tracking
from src.domain.models.speech import TimeSpan
from src.domain.services.edl_rules import edl_bounds, validate_edl


def edl(*ranges):
    return Edl(ranges=[TimeSpan(start=a, end=b) for a, b in ranges], captions=Captions(words=[]))


def test_valid_multi_range_edit():
    validate_edl(edl((1, 5), (5, 9), (12, 20)), source_duration=30)


@pytest.mark.parametrize(
    ("ranges", "message"),
    [
        ((), "at least one range"),
        (((1, 1.05),), "shorter than"),
        (((5, 9), (8, 12)), "overlaps"),
        (((10, 12), (1, 5)), "overlaps or precedes"),
        (((25, 31),), "ends after the video"),
    ],
)
def test_invalid_edits_are_rejected(ranges, message):
    with pytest.raises(AppValidationException, match=message):
        validate_edl(edl(*ranges), source_duration=30)


def test_bounds_span_first_to_last_range():
    assert edl_bounds(edl((3, 5), (9, 14))) == TimeSpan(start=3, end=14)


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
