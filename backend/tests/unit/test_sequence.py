"""Main-track timeline maths — cases mirror frontend/src/editor/sequence.test.ts."""

import pytest

from src.domain.enums.caption_style_enum import CaptionStyle
from src.domain.models.edl import FreezeSegment, ImageSegment, Transition
from src.domain.services.sequence import (
    caption_cues,
    layout,
    media_time,
    output_duration,
    output_time,
    placed_at,
)
from tests.unit.edl_builders import edl, seg, words


def spans(placed):
    return [(round(p.start, 3), round(p.end, 3)) for p in placed]


def test_segments_play_back_to_back_at_their_speed():
    track = [seg(10, 14), seg(20, 26, speed=2), FreezeSegment(id="f", at=30, duration=1.5)]
    assert spans(layout(track)) == [(0, 4), (4, 7), (7, 8.5)]
    assert output_duration(track) == 8.5


def test_a_transition_overlaps_the_previous_segment_and_splits_ownership():
    track = [seg(0, 4), seg(10, 14, transition=Transition(duration=1)), seg(20, 22)]
    placed = layout(track)
    assert spans(placed) == [(0, 4), (3, 7), (7, 9)]
    assert [(p.own_start, p.own_end) for p in placed] == [(0, 3.5), (3.5, 7), (7, 9)]
    assert output_duration(track) == 9


def test_the_first_segment_ignores_its_transition():
    assert spans(layout([seg(0, 4, transition=Transition(duration=1))])) == [(0, 4)]


def test_lookups_between_output_and_media_time():
    placed = layout(
        [seg(10, 14), seg(20, 26, speed=2), ImageSegment(id="i", image="a.png", duration=2)]
    )
    assert placed_at(placed, 3.9).index == 0
    assert placed_at(placed, 4).index == 1
    assert placed_at(placed, 9).index == 2  # the very end belongs to the last segment
    assert placed_at(placed, 9.5) is None
    assert media_time(placed[1], 5) == 22
    assert media_time(placed[2], 8) == 1
    assert output_time(placed[1], 22) == 5


SPOKEN = words(("hello", 10.2, 10.6), ("there.", 10.7, 11.0), ("again", 20.5, 21.0))


def test_captions_follow_each_segment_onto_the_output_timeline():
    cues = caption_cues(edl((10, 12), (20, 23), captions=SPOKEN), CaptionStyle.BOLD_HIGHLIGHT)
    assert [[(w.text, w.start, w.end) for w in c.words] for c in cues] == [
        [("hello", 0.2, 0.6), ("there.", 0.7, 1.0)],
        [("again", 2.5, 3.0)],
    ]
    assert cues[0].end == pytest.approx(1.3)  # held after the last word
    assert cues[1].end == pytest.approx(3.3)


def test_reordered_duplicated_and_sped_up_segments_bring_their_captions():
    clip = edl(
        seg(20, 23, id="b", speed=2), seg(10, 12, id="a"), seg(10, 12, id="a2"), captions=SPOKEN
    )
    cues = caption_cues(clip, CaptionStyle.CLEAN)
    assert [(c.words[0].text, c.start) for c in cues] == [
        ("again", 0.25),
        ("hello", 1.7),
        ("hello", 3.7),
    ]
    assert cues[0].words[0].end == 0.5


def test_captions_are_cut_at_the_middle_of_a_transition():
    clip = edl(seg(10, 12), seg(20, 23, transition=Transition(duration=1)), captions=SPOKEN)
    first, second = caption_cues(clip, CaptionStyle.CLEAN)
    # Segment 1 owns 0-1.5 s; its page would hold until 1.3 s, inside its share.
    assert (first.start, first.end) == (0.2, 1.3)
    # Segment 2 starts at 1 s (source 20); "again" at source 20.5 → 1.5 s.
    assert second.start == 1.5


def test_other_media_has_no_captions():
    clip = edl(seg(10, 12, media="00000000-0000-0000-0000-000000000001"), captions=SPOKEN)
    assert caption_cues(clip, CaptionStyle.CLEAN) == []
