"""Python ports of the editor's maths — cases mirror frontend/src/editor/*.test.ts."""

from uuid import UUID

import pytest

from src.domain.enums.aspect_ratio_enum import AspectRatio
from src.domain.enums.broll_layout_enum import BrollLayout
from src.domain.enums.caption_style_enum import CaptionStyle
from src.domain.exceptions import MediaProcessingException
from src.domain.models.edl import (
    BrollItem,
    Color,
    Crop,
    FreezeSegment,
    ImageSegment,
    Overlay,
    Shot,
    Tracking,
    Transition,
)
from src.domain.models.render import MediaSource
from src.domain.models.speech import TimeSpan
from src.domain.services.caption_pages import hide_time, paginate
from src.domain.services.framing import crop_at, crop_window
from src.domain.services.render_planning import media_keys, plan_render
from tests.unit.edl_builders import edl, seg, sources, words

SAMPLE = words(
    ("one", 0, 0.3), ("two", 0.3, 0.6), ("three", 0.6, 0.9), ("four.", 0.9, 1.2),
    ("five", 2.5, 2.8), ("six", 2.8, 3.1),
)  # fmt: skip
B_ROLL = UUID("00000000-0000-0000-0000-0000000000b0")


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
    plan = plan_render(edl((0, 5), split_screen=True), sources())
    # Each 960x1080 half fills a 1080x960 pane: a 9:8 window, full width, centred.
    assert [c.model_dump() for c in plan.segments[0].crops] == [
        {"x": 0, "y": 113, "width": 960, "height": 854},
        {"x": 960, "y": 113, "width": 960, "height": 854},
    ]


def test_plan_resolves_segments_captions_and_overlays_to_output_time():
    clip = edl(
        (10, 12),
        seg(20, 23, id="s2", speed=1.5, volume=0.5, transition=Transition(duration=0.5)),
        captions=words(("hello", 10.2, 10.6), ("there.", 10.7, 11.0), ("again", 20.5, 21.0)),
        overlays=[
            Overlay(text="Hook", start=0, end=2),
            Overlay(text="Too late", start=3.45, end=8),  # starts 0.05 s before the end
            Overlay(text="Clipped", start=3, end=9),
        ],
    )
    plan = plan_render(clip, sources())

    assert (plan.width, plan.height, plan.duration) == (1080, 1920, 3.5)
    first, second = plan.segments
    assert (first.source_start, first.source_duration, first.length, first.offset) == (10, 2, 2, 0)
    assert (second.speed, second.volume, second.length, second.offset) == (1.5, 0.5, 2, 1.5)
    assert first.transition is None and second.transition.duration == 0.5
    assert [(w.text, w.start) for c in plan.captions for w in c.words] == [
        ("hello", 0.2),
        ("there.", 0.7),
        ("again", 1.833),
    ]
    assert [(o.text, o.end) for o in plan.overlays] == [("Hook", 2), ("Clipped", 3.5)]
    assert [" ".join(w.text for w in c.words) for c in plan.subtitles] == ["hello there.", "again"]


def test_freeze_and_image_segments_are_silent_stills():
    clip = edl(
        (10, 12),
        FreezeSegment(id="f", at=11, duration=1),
        ImageSegment(id="i", image="logo.png", duration=2, color=Color(saturation=0)),
    )
    assert media_keys(clip) == {"main", "image:logo.png"}
    plan = plan_render(
        clip, sources(**{"image:logo.png": MediaSource(width=800, height=800, has_audio=False)})
    )
    _, freeze, image = plan.segments
    assert (freeze.kind, freeze.source_start, freeze.length, freeze.has_audio) == (
        "freeze",
        11,
        1,
        False,
    )
    assert (image.kind, image.input, image.source_width) == ("image", "image:logo.png", 800)
    assert image.color == Color(saturation=0)
    assert plan.segments[0].color is None  # neutral grades are left out
    assert plan.duration == 5


def test_missing_media_fails_the_render():
    with pytest.raises(MediaProcessingException, match="image:x.png"):
        plan_render(edl((0, 2), ImageSegment(image="x.png", duration=1)), sources())


def test_ken_burns_plans_the_start_and_end_windows():
    clip = edl(seg(0, 4, crop=Crop(x=0.5, y=0.5), crop_to=Crop(x=0.5, y=0.5, scale=2)))
    planned = plan_render(clip, sources()).segments[0]
    assert planned.crops[0].model_dump() == {"x": 656, "y": 0, "width": 608, "height": 1080}
    assert planned.crop_to.model_dump() == {"x": 808, "y": 270, "width": 304, "height": 540}


def test_broll_layouts():
    clip = edl(
        (0, 10),
        broll=[
            BrollItem(id="full", media=B_ROLL, start=1, duration=3, media_start=5, volume=0.5),
            BrollItem(
                id="pip", image="a.png", start=8, duration=5, layout=BrollLayout.PIP, x=1, y=0
            ),
        ],
    )
    plan = plan_render(
        clip,
        sources(**{
            str(B_ROLL): MediaSource(width=1280, height=720, has_audio=True),
            "image:a.png": MediaSource(width=400, height=200, has_audio=False),
        }),
    )  # fmt: skip
    full, pip = plan.broll
    assert (full.x, full.y, full.width, full.height) == (0, 0, 1080, 1920)
    assert full.crop.model_dump() == {"x": 438, "y": 0, "width": 404, "height": 720}
    assert (full.has_audio, full.media_start) == (True, 5)
    # 40% of 1080 wide, 2:1 → 432x216, pushed into the top-right corner; cut at the clip's end.
    assert (pip.x, pip.y, pip.width, pip.height, pip.duration) == (648, 0, 432, 216, 2)
    assert pip.has_audio is False


def tracked(enabled=True, scale=1.0):
    return edl(
        (10, 14),
        (20, 26),
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
    clip = tracked(scale=2)
    segment = clip.segments[0]
    assert crop_at(clip, segment, 9) == Crop(x=0.2, y=0.5, scale=2)
    assert crop_at(clip, segment, 12) == Crop(x=0.8, y=0.5, scale=2)
    assert crop_at(clip, segment, 5) == Crop(x=0.2, y=0.5, scale=2)  # before the span: first shot
    off = tracked(enabled=False)
    assert crop_at(off, off.segments[0], 12) == Crop()


def test_a_segment_crop_overrides_tracking_and_ken_burns_interpolates():
    clip = tracked()
    own = seg(10, 14, crop=Crop(x=0.1, y=0.5), crop_to=Crop(x=0.3, y=0.5, scale=3))
    assert crop_at(clip, own, 12) == Crop(x=0.2, y=0.5, scale=2)


def test_tracked_plan_moves_the_crop_on_each_segments_timeline():
    first, second = plan_render(tracked(), sources()).segments
    # 9:16 window of a 1080p source is 608 wide; x=0.2 → 80, x=0.8 → 1232.
    assert [c.model_dump() for c in first.crops] == [
        {"x": 80, "y": 0, "width": 608, "height": 1080}
    ]
    # Segment 1 cuts to face 1 at source 12 (2 s in); segment 2 starts on face 0 (source
    # 20 is in the shot from 16) and cuts to face 1 at source 23 (3 s in).
    assert [(m.time, m.x) for m in first.crop_moves] == [(0, 80), (2, 1232)]
    assert [(m.time, m.x) for m in second.crop_moves] == [(0, 80), (3, 1232)]


def test_tracking_off_plans_a_still_crop():
    first = plan_render(tracked(enabled=False), sources()).segments[0]
    assert first.crop_moves == []
    assert len(first.crops) == 2  # the split screen applies again
