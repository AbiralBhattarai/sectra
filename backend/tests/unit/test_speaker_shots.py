import pytest

from src.domain.models.face_track import FaceTrack
from src.domain.models.speech import TimeSpan
from src.domain.services.speaker_shots import build_shots

SPAN = TimeSpan(start=100, end=110)
FPS = 10  # small frame rate keeps the score lists readable


def track(id, scores, first_frame=0, centre=(0.25, 0.5)):
    return FaceTrack(id=id, first_frame=first_frame, centres=[centre] * len(scores), scores=scores)


def summary(shots):
    return [(s.start, s.face) for s in shots]


def test_cuts_to_whoever_speaks_and_centres_on_them():
    a = track(0, [2.0] * 30 + [-2.0] * 30, centre=(0.25, 0.4))
    b = track(1, [-2.0] * 30 + [2.0] * 30, centre=(0.75, 0.5))
    shots = build_shots([a, b], SPAN, FPS, min_shot_seconds=1)
    assert summary(shots) == [(100, 0), (103, 1)]
    assert (shots[0].x, shots[0].y, shots[1].x) == (0.25, 0.4, 0.75)


def test_silence_holds_the_last_speaker_and_the_lead_in_goes_to_the_main_speaker():
    a = track(0, [-2.0] * 20 + [2.0] * 10 + [-2.0] * 30)
    b = track(1, [-2.0] * 40 + [2.0] * 20, centre=(0.8, 0.5))
    # Nobody speaks for 2 s (b speaks most → it gets the lead-in), then a, then silence
    # (a is held), then b.
    assert summary(build_shots([a, b], SPAN, FPS, min_shot_seconds=1)) == [
        (100, 1),
        (102, 0),
        (104, 1),
    ]


def test_short_runs_merge_into_the_longer_neighbour():
    a = track(0, [2.0] * 30 + [-2.0] * 5 + [2.0] * 10)
    b = track(1, [-2.0] * 30 + [2.0] * 5 + [-2.0] * 10, centre=(0.8, 0.5))
    # b's 0.5 s interjection is shorter than 1.5 s, so it never gets a shot.
    assert summary(build_shots([a, b], SPAN, FPS, min_shot_seconds=1.5)) == [(100, 0)]


def test_pieces_of_one_person_are_joined_and_faces_numbered_by_appearance():
    left = (0.2, 0.5)
    first = track(7, [2.0] * 20, centre=left)
    second = track(9, [2.0] * 20, first_frame=30, centre=(0.22, 0.5))  # lost for 1 s
    other = track(4, [-2.0] * 60, centre=(0.8, 0.5))
    shots = build_shots([second, other, first], SPAN, FPS, min_shot_seconds=1)
    # One person throughout: the 1 s gap scores as silence and holds them, so no cut.
    assert summary(shots) == [(100, 0)]


def test_a_face_that_leaves_is_framed_where_it_was_seen():
    a = track(0, [2.0] * 20, centre=(0.2, 0.5))
    b = track(1, [-2.0] * 40 + [2.0] * 20, centre=(0.8, 0.5), first_frame=0)
    shots = build_shots([a, b], SPAN, FPS, min_shot_seconds=1)
    assert summary(shots) == [(100, 0), (104, 1)]
    assert shots[0].x == 0.2


def test_no_faces_no_shots():
    assert build_shots([], SPAN, FPS, min_shot_seconds=1) == []


def test_nobody_speaking_frames_the_face_seen_longest():
    shots = build_shots(
        [track(0, [-1.0] * 10), track(1, [-1.0] * 50, centre=(0.8, 0.5))], SPAN, FPS, 1
    )
    assert summary(shots) == [(100, 1)]


@pytest.mark.parametrize("min_shot", [0.1, 100])
def test_shots_always_start_at_the_span(min_shot):
    a = track(0, [2.0] * 10 + [-2.0] * 10)
    b = track(1, [-2.0] * 10 + [2.0] * 10, centre=(0.8, 0.5))
    assert build_shots([a, b], SPAN, FPS, min_shot)[0].start == SPAN.start
