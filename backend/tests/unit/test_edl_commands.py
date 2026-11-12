from uuid import UUID

import pytest
from pydantic import TypeAdapter

from src.domain.enums.color_preset_enum import ColorPreset
from src.domain.enums.transition_type_enum import TransitionType
from src.domain.exceptions import AppValidationException
from src.domain.models.edit_command import EditCommand
from src.domain.models.edl import Color, Crop, FreezeSegment, Shot, Tracking, Transition
from src.domain.models.speech import TimeSpan
from src.domain.services.color_grading import PRESETS
from src.domain.services.edl_commands import EditContext, apply_all, merge_tracking
from tests.unit.edl_builders import Ids, edl, seg, words

CLIP_VIDEO = UUID("00000000-0000-0000-0000-000000000001")
OTHER = UUID("00000000-0000-0000-0000-000000000002")
TRANSCRIPT = words(
    ("one", 1.0, 1.4), ("two", 2.0, 2.4), ("three", 3.0, 3.4), ("four", 4.0, 4.4),
    ("five", 5.0, 5.4), ("six", 6.0, 6.4), ("seven", 7.0, 7.4), ("eight", 8.0, 8.4),
)  # fmt: skip
COMMAND = TypeAdapter(EditCommand)


def run(clip, *commands, media=None):
    ctx = EditContext(
        clip_video=CLIP_VIDEO,
        source_duration=30,
        transcript=TRANSCRIPT,
        media_durations=media or {},
        new_id=Ids(),
    )
    return apply_all(clip, [COMMAND.validate_python(c) for c in commands], ctx)


def base():
    """Segments s1 = 1–5 s, s2 = 6–9 s (output 0–4, 4–7), captioned from the transcript."""
    inside = [w for w in TRANSCRIPT if w.start >= 1 and w.end <= 5 or w.start >= 6 and w.end <= 9]
    return edl((1, 5), (6, 9), captions=inside)


def bounds(clip):
    return [(s.id, getattr(s, "start", None), getattr(s, "end", None)) for s in clip.segments]


def caption_text(clip):
    return " ".join(w.text for w in clip.captions.words)


def test_split_at_an_output_time():
    clip = run(base(), {"op": "split", "at": 5})
    assert bounds(clip) == [("s1", 1, 5), ("s2", 6, 7), ("n1", 7, 9)]


@pytest.mark.parametrize(("at", "message"), [(4.05, "too close"), (8, "past the end")])
def test_split_errors(at, message):
    with pytest.raises(AppValidationException, match=f"Command 1 \\(split\\): .*{message}"):
        run(base(), {"op": "split", "at": at})


def test_trim_ripples_and_brings_back_captions():
    clip = run(base(), {"op": "trim", "segment_id": "s1", "start": 2, "end": 4.5})
    assert bounds(clip) == [("s1", 2, 4.5), ("s2", 6, 9)]
    assert caption_text(clip) == "two three four six seven eight"
    clip = run(clip, {"op": "trim", "segment_id": "s1", "start": 0})
    assert caption_text(clip).startswith("one two")


def test_edited_words_survive_trims():
    clip = run(base(), {"op": "edit_words", "words": [{"index": 1, "text": "TWO"}]})
    clip = run(clip, {"op": "trim", "segment_id": "s1", "end": 3.5})
    assert caption_text(clip) == "one TWO three six seven eight"


def test_trim_errors():
    with pytest.raises(AppValidationException, match="shorter than"):
        run(base(), {"op": "trim", "segment_id": "s1", "end": 1.05})
    with pytest.raises(AppValidationException, match="runs past the end"):
        run(base(), {"op": "trim", "segment_id": "s2", "end": 31})
    with pytest.raises(AppValidationException, match=r"No segment 'zz' \(segments: s1, s2\)"):
        run(base(), {"op": "trim", "segment_id": "zz", "end": 3})


def test_delete_move_duplicate():
    clip = run(base(), {"op": "duplicate", "segment_id": "s1"})
    assert bounds(clip) == [("s1", 1, 5), ("n1", 1, 5), ("s2", 6, 9)]
    clip = run(clip, {"op": "move", "segment_id": "s2", "to_index": 0})
    assert [s.id for s in clip.segments] == ["s2", "s1", "n1"]
    pasted = run(clip, {"op": "update_segment", "segment_ids": ["s1"], "speed": 2})
    pasted = apply_all(
        pasted,
        [COMMAND.validate_python({"op": "duplicate", "segment_id": "s1", "to_index": 0})],
        EditContext(CLIP_VIDEO, 30, TRANSCRIPT, new_id=lambda: "pasted"),
    )
    assert [s.id for s in pasted.segments] == ["pasted", "s2", "s1", "n1"]
    assert pasted.segments[0].speed == 2  # a copy keeps every setting
    clip = run(clip, {"op": "delete", "segment_ids": ["s1", "n1"]})
    assert bounds(clip) == [("s2", 6, 9)]
    assert caption_text(clip) == "six seven eight"
    with pytest.raises(AppValidationException, match="at least one segment"):
        run(clip, {"op": "delete", "segment_ids": ["s2"]})


def test_moving_a_segment_first_drops_its_transition():
    clip = run(
        base(), {"op": "set_transition", "segment_id": "s2", "type": "wipeleft", "duration": 1}
    )
    assert clip.segments[1].transition == Transition(type=TransitionType.WIPE_LEFT, duration=1)
    clip = run(clip, {"op": "move", "segment_id": "s2", "to_index": 0})
    assert clip.segments[0].transition is None


def test_transition_rules():
    with pytest.raises(AppValidationException, match="nothing to transition from"):
        run(base(), {"op": "set_transition", "segment_id": "s1"})
    with pytest.raises(AppValidationException, match="longer than half"):
        run(base(), {"op": "set_transition", "segment_id": "s2", "duration": 2})
    clip = run(
        base(),
        {"op": "set_transition", "segment_id": "s2"},
        {"op": "remove_transition", "segment_id": "s2"},
    )
    assert clip.segments[1].transition is None


def test_insert_from_the_clip_video_and_from_other_media():
    clip = run(
        base(),
        {"op": "insert", "start": 20, "end": 22, "at_index": 0, "media": str(CLIP_VIDEO)},
        {"op": "insert", "start": 0, "end": 3, "media": str(OTHER)},
        {"op": "insert_image", "image": "logo.png", "duration": 2, "at_index": 1},
        media={OTHER: 10},
    )
    kinds = [(s.kind, getattr(s, "media", None)) for s in clip.segments]
    assert kinds == [
        ("video", None),
        ("image", None),
        ("video", None),
        ("video", None),
        ("video", OTHER),
    ]
    with pytest.raises(AppValidationException, match="isn't ready"):
        run(base(), {"op": "insert", "start": 0, "end": 3, "media": str(OTHER)})


def test_freeze_frame_splits_around_the_frame():
    clip = run(base(), {"op": "freeze_frame", "at": 2, "duration": 1.5})
    assert [s.kind for s in clip.segments] == ["video", "freeze", "video", "video"]
    freeze = clip.segments[1]
    assert isinstance(freeze, FreezeSegment) and (freeze.at, freeze.duration) == (3, 1.5)
    # The frame takes the first new id, the second half of the split the next.
    assert bounds(clip)[0] == ("s1", 1, 3) and bounds(clip)[2] == ("n2", 3, 5)


def test_update_segment_audio_and_look():
    clip = run(
        base(),
        {"op": "update_segment", "segment_ids": ["s1", "s2"], "speed": 2, "volume": 0, "color_preset": "bw"},
        {"op": "update_segment", "segment_ids": ["s2"], "crop": {"x": 0.2, "y": 0.5}, "crop_to": {"x": 0.8, "y": 0.5, "scale": 2}},
    )  # fmt: skip
    s1, s2 = clip.segments
    assert (s1.speed, s1.volume, s1.color) == (2, 0, PRESETS[ColorPreset.BW])
    assert (s2.crop, s2.crop_to) == (Crop(x=0.2, y=0.5), Crop(x=0.8, y=0.5, scale=2))
    clip = run(clip, {"op": "update_segment", "segment_ids": ["s2"], "clear_crop": True})
    assert (clip.segments[1].crop, clip.segments[1].crop_to) == (None, None)


def test_update_segment_errors():
    with pytest.raises(AppValidationException, match="not both"):
        run(
            base(),
            {"op": "update_segment", "segment_ids": ["s1"], "color": {}, "color_preset": "bw"},
        )
    with pytest.raises(AppValidationException, match="needs a crop"):
        run(base(), {"op": "update_segment", "segment_ids": ["s1"], "crop_to": {}})
    frozen = run(base(), {"op": "freeze_frame", "at": 2})
    with pytest.raises(AppValidationException, match="apply to video segments"):
        run(frozen, {"op": "update_segment", "segment_ids": [frozen.segments[1].id], "speed": 2})


def test_splitting_a_ken_burns_segment_keeps_the_motion_continuous():
    clip = edl(seg(0, 4, id="k", crop=Crop(x=0.2, y=0.5), crop_to=Crop(x=0.6, y=0.5)))
    first, second = run(clip, {"op": "split", "at": 1}).segments
    assert first.crop_to == second.crop == Crop(x=0.3, y=0.5)
    assert second.crop_to == Crop(x=0.6, y=0.5)


def test_update_clip_keeps_split_screen_and_tracking_exclusive():
    tracking = Tracking(span=TimeSpan(start=0, end=10), shots=[Shot(start=0, face=0, x=0.5, y=0.5)])
    clip = base().model_copy(update={"tracking": tracking})
    clip = run(clip, {"op": "update_clip", "split_screen": True, "aspect": "1:1", "fade_in": 0.5})
    assert (clip.split_screen, clip.tracking.enabled, clip.aspect.value, clip.fade_in) == (
        True,
        False,
        "1:1",
        0.5,
    )
    clip = run(clip, {"op": "update_clip", "tracking_enabled": True, "caption_style": "clean"})
    assert (clip.split_screen, clip.tracking.enabled, clip.captions.style.value) == (
        False,
        True,
        "clean",
    )
    with pytest.raises(AppValidationException, match="request it first"):
        run(base(), {"op": "update_clip", "tracking_enabled": True})


def test_caption_word_commands():
    clip = run(base(), {"op": "delete_words", "indices": [0, 1]})
    assert caption_text(clip) == "three four six seven eight"
    with pytest.raises(AppValidationException, match="No caption word 9"):
        run(clip, {"op": "edit_words", "words": [{"index": 9, "text": "x"}]})
    restored = run(clip, {"op": "restore_words", "start": 0, "end": 2.5})
    assert caption_text(restored) == "one two three four six seven eight"


def test_overlays_broll_markers_and_music():
    clip = run(
        base(),
        {"op": "add_overlay", "text": "Hook", "start": 0, "end": 2},
        {"op": "add_broll", "image": "a.png", "start": 1, "duration": 2},
        {"op": "add_marker", "time": 3, "label": "beat"},
        {"op": "set_music", "file": "beat.mp3"},
    )
    assert [o.id for o in clip.overlays] == ["n1"] and clip.broll[0].id == "n2"
    clip = run(
        clip,
        {"op": "update_overlay", "id": "n1", "text": "New hook", "end": 3},
        {"op": "update_broll", "id": "n2", "layout": "pip", "fade": 0.5},
        {"op": "remove_marker", "id": "n3"},
        {"op": "remove_music"},
    )
    assert (clip.overlays[0].text, clip.overlays[0].end) == ("New hook", 3)
    assert (clip.broll[0].layout.value, clip.broll[0].fade) == ("pip", 0.5)
    assert clip.markers == [] and clip.music is None
    with pytest.raises(AppValidationException, match="ends before it starts"):
        run(clip, {"op": "update_overlay", "id": "n1", "end": 0.05})
    with pytest.raises(AppValidationException, match="No B-roll 'zz'"):
        run(clip, {"op": "remove_broll", "id": "zz"})


def test_a_failing_command_names_its_position_and_changes_nothing():
    clip = base()
    with pytest.raises(AppValidationException, match=r"^Command 2 \(trim\)"):
        run(clip, {"op": "split", "at": 2}, {"op": "trim", "segment_id": "nope", "end": 3})
    assert bounds(clip) == [("s1", 1, 5), ("s2", 6, 9)]


def test_unknown_fields_are_rejected():
    with pytest.raises(ValueError, match="extra"):
        COMMAND.validate_python({"op": "split", "at": 1, "when": 2})


def test_reframe_shot():
    tracking = Tracking(span=TimeSpan(start=0, end=10), shots=[Shot(start=0, face=0, x=0.5, y=0.5)])
    clip = run(
        base().model_copy(update={"tracking": tracking}),
        {"op": "reframe_shot", "index": 0, "x": 0.2, "y": 0.4},
    )
    assert (clip.tracking.shots[0].x, clip.tracking.shots[0].y) == (0.2, 0.4)
    with pytest.raises(AppValidationException, match="No face-tracking shot 1"):
        run(clip, {"op": "reframe_shot", "index": 1, "x": 0, "y": 0})


def test_merge_tracking_keeps_the_old_shots_and_turns_split_screen_off():
    old = Tracking(span=TimeSpan(start=4, end=10), shots=[Shot(start=4, face=0, x=0.1, y=0.5)])
    fresh = Tracking(
        span=TimeSpan(start=0, end=14),
        shots=[Shot(start=0, face=1, x=0.9, y=0.5), Shot(start=8, face=1, x=0.9, y=0.5)],
    )
    clip = merge_tracking(base().model_copy(update={"tracking": old, "split_screen": True}), fresh)
    assert clip.split_screen is False
    assert clip.tracking.span == TimeSpan(start=0, end=14)
    assert [(s.start, s.x) for s in clip.tracking.shots] == [(0, 0.9), (4, 0.1), (10, 0.9)]


def test_colour_presets_are_plain_colours():
    assert PRESETS[ColorPreset.NONE] == Color()
