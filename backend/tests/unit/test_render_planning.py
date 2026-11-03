"""Python ports of the editor's maths — cases mirror frontend/src/editor/*.test.ts."""

import pytest

from src.domain.enums.aspect_ratio_enum import AspectRatio
from src.domain.enums.caption_style_enum import CaptionStyle
from src.domain.models.edl import Captions, Crop, Edl, Overlay, Shot, Tracking
from src.domain.models.speech import TimeSpan
from src.domain.models.transcript import Word
from src.domain.services.caption_pages import hide_time, paginate
from src.domain.services.edl_timing import output_duration, source_to_output
from src.domain.services.framing import crop_at, crop_window
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


def test_split_screen_stacks_the_left_half_over_the_right():
    edl = Edl(ranges=[TimeSpan(start=0, end=5)], captions=Captions(words=[]), split_screen=True)
    # Each 960x1080 half fills a 1080x960 pane: a 9:8 window, full width, centred.
    assert [c.model_dump() for c in plan_render(edl, 1920, 1080).crops] == [
        {"x": 0, "y": 113, "width": 960, "height": 854},
        {"x": 960, "y": 113, "width": 960, "height": 854},
    ]


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


def tracked(enabled=True, scale=1.0):
    return Edl(
        ranges=[TimeSpan(start=10, end=14), TimeSpan(start=20, end=26)],
        captions=Captions(words=[]),
        crop=Crop(x=0.5, y=0.5, scale=scale),
        split_screen=True,  # ignored while tracking is on
        tracking=Tracking(
            enabled=enabled,
            span=TimeSpan(start=8, end=28),
            shots=[
                Shot(start=8, face=0, x=0.2, y=0.5),
                Shot(start=12, face=1, x=0.8, y=0.5),
                Shot(start=16, face=0, x=0.2, y=0.5),  # inside the cut: never shown
                Shot(start=23, face=1, x=0.8, y=0.5),
            ],
        ),
    )


def test_crop_at_follows_the_shot_and_keeps_the_shared_zoom():
    edl = tracked(scale=2)
    assert crop_at(edl, 9) == Crop(x=0.2, y=0.5, scale=2)
    assert crop_at(edl, 12) == Crop(x=0.8, y=0.5, scale=2)
    assert crop_at(edl, 5) == Crop(x=0.2, y=0.5, scale=2)  # before the span: first shot
    assert crop_at(tracked(enabled=False), 12) == Crop()


def test_tracked_plan_moves_the_crop_on_the_output_timeline():
    plan = plan_render(tracked(), 1920, 1080)
    # 9:16 window of a 1080p source is 608 wide; x=0.2 → 80, x=0.8 → 1232.
    assert [c.model_dump() for c in plan.crops] == [{"x": 80, "y": 0, "width": 608, "height": 1080}]
    # Output: range 1 is 0-4 s (cut to face 1 at source 12 → 2 s); range 2 starts at 4 s
    # on face 0 (source 20 is in the shot from 16) and cuts to face 1 at source 23 → 7 s.
    assert [(m.time, m.x) for m in plan.crop_moves] == [(0, 80), (2, 1232), (4, 80), (7, 1232)]


def test_tracking_off_plans_a_still_crop():
    plan = plan_render(tracked(enabled=False), 1920, 1080)
    assert plan.crop_moves == []
    assert len(plan.crops) == 2  # the split screen applies again
