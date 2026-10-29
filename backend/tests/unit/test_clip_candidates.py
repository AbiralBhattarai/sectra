from src.domain.models.clip import ClipCandidate
from src.domain.services.clip_candidates import select_clips
from tests.unit.transcript_builders import evenly


def candidate(start, end, score=50, title="t"):
    return ClipCandidate(
        start_segment=start, end_segment=end, title=title, hook="h", score=score, reason="r"
    )


def spans(selected):
    return [(span.start, span.end) for _, span in selected]


SEGMENTS = evenly(20)  # 0-200 s in 10 s segments


def pick(candidates, min_s=15, max_s=60, count=10):
    return select_clips(candidates, SEGMENTS, min_s, max_s, count)


def test_segment_ids_resolve_to_word_times():
    assert spans(pick([candidate(2, 4)])) == [(20.0, 50.0)]


def test_too_short_grows_forward_on_segment_boundaries():
    assert spans(pick([candidate(3, 3)])) == [(30.0, 50.0)]


def test_too_short_at_the_end_grows_backward():
    assert spans(pick([candidate(19, 19)])) == [(180.0, 200.0)]


def test_too_long_is_trimmed_from_the_end():
    assert spans(pick([candidate(0, 9)])) == [(0.0, 60.0)]


def test_unknown_or_reversed_ids_are_dropped():
    assert pick([candidate(5, 99), candidate(6, 4), candidate(-1, 2)]) == []


def test_overlapping_duplicates_keep_the_higher_score():
    selected = pick(
        [candidate(2, 4, score=60, title="low"), candidate(2, 5, score=90, title="high")]
    )
    assert [c.title for c, _ in selected] == ["high"]


def test_count_keeps_best_scores_and_result_is_in_time_order():
    candidates = [candidate(i * 4, i * 4 + 2, score=s) for i, s in enumerate([10, 80, 30, 90, 20])]
    selected = pick(candidates, count=2)
    assert [c.score for c, _ in selected] == [80, 90]
    assert spans(selected) == [(40.0, 70.0), (120.0, 150.0)]


def test_impossible_lengths_are_dropped():
    # A single 10 s segment can't reach 15 s when the whole video is that segment.
    assert select_clips([candidate(0, 0)], evenly(1), 15, 60, 10) == []
