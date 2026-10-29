"""Python ports of the editor's maths — cases mirror frontend/src/editor/*.test.ts."""

import pytest

from src.domain.enums.aspect_ratio_enum import AspectRatio
from src.domain.enums.caption_style_enum import CaptionStyle
from src.domain.models.edl import Captions, Crop, Edl, Overlay
from src.domain.models.speech import TimeSpan
from src.domain.models.transcript import Word
from src.domain.services.caption_pages import hide_time, paginate
from src.domain.services.edl_timing import output_duration, source_to_output
from src.domain.services.framing import crop_window
from src.domain.services.render_planning import plan_render


def words(*specs):
    return [Word(text=t, start=s, end=e) for t, s, e in specs]


SAMPLE = words(
    ("one", 0, 0.3), ("two", 0.3, 0.6), ("three", 0.6, 0.9), ("four.", 0.9, 1.2),
    ("five", 2.5, 2.8), ("six", 2.8, 3.1),
)  # fmt: skip


def texts(pages):
    return [" ".join(w.text for w in page) for page in pages]


def test_paginate_matches_the_preview():
    assert texts(paginate(SAMPLE, CaptionStyle.BOLD_HIGHLIGHT)) == [
        "one two three",
        "four.",
        "five six",
    ]
    assert texts(paginate(SAMPLE, CaptionStyle.CLEAN)) == ["one two three four.", "five six"]
    assert paginate(SAMPLE, CaptionStyle.NONE) == []


def test_hide_time_holds_until_next_page():
    pages = paginate(
        words(("a", 0, 0.5), ("b.", 0.5, 1), ("c", 3, 3.5)), CaptionStyle.BOLD_HIGHLIGHT
    )
    assert hide_time(pages, 0) == pytest.approx(1.3)
    assert hide_time(pages, 1) == pytest.approx(3.8)


@pytest.mark.parametrize(
    ("aspect", "crop", "expected"),
    [
        (AspectRatio.VERTICAL, Crop(), (656, 0, 608, 1080)),
        (AspectRatio.VERTICAL, Crop(x=0, y=0.5, scale=2), (0, 270, 304, 540)),
        (AspectRatio.LANDSCAPE, Crop(), (0, 0, 1920, 1080)),
        (AspectRatio.SQUARE, Crop(x=1, y=0.5), (840, 0, 1080, 1080)),
    ],
)
def test_crop_window_matches_the_preview_rounded_to_even(aspect, crop, expected):
    assert crop_window(1920, 1080, aspect, crop) == expected


def test_time_mapping():
    ranges = [TimeSpan(start=10, end=14), TimeSpan(start=20, end=26)]
    assert output_duration(ranges) == 10
    assert source_to_output(12, ranges) == 2
    assert source_to_output(17, ranges) == 4
    assert source_to_output(21, ranges) == 5


def test_plan_moves_captions_and_overlays_to_output_time():
    edl = Edl(
        ranges=[TimeSpan(start=10, end=12), TimeSpan(start=20, end=23)],
        captions=Captions(
            words=words(("hello", 10.2, 10.6), ("there.", 10.7, 11.0), ("again", 20.5, 21.0)),
            style=CaptionStyle.BOLD_HIGHLIGHT,
        ),
        overlays=[
            Overlay(text="Hook", start=0, end=2),
            Overlay(text="Too late", start=4.95, end=8),  # starts after the clip, minus 0.05 s
            Overlay(text="Clipped", start=4, end=9),
        ],
    )

    plan = plan_render(edl, 1920, 1080)

    assert (plan.width, plan.height, plan.duration) == (1080, 1920, 5)
    first, second = plan.captions
    assert [(w.text, w.start, w.end) for w in first.words] == [
        ("hello", 0.2, 0.6),
        ("there.", 0.7, 1.0),
    ]
    assert first.end == pytest.approx(1.3)
    assert (second.start, second.end) == (2.5, 3.3)
    assert [(o.text, o.end) for o in plan.overlays] == [("Hook", 2), ("Clipped", 5)]
    # The .srt always uses sentence-style grouping.
    assert [" ".join(w.text for w in c.words) for c in plan.subtitles] == ["hello there.", "again"]
