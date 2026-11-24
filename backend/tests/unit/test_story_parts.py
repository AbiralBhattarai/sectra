from src.domain.services.story_parts import split_parts
from tests.unit.transcript_builders import seg


def spans(parts):
    return [(p.start, p.end) for p in parts]


def test_a_short_story_is_one_part():
    segments = [seg(0, 0.2, 5), seg(1, 5.5, 9)]
    assert spans(split_parts(segments, 9.5, 170)) == [(0, 9.5)]


def test_long_story_splits_evenly_in_pauses_and_tiles_the_timeline():
    # 30 sentences of 9.5 s with 0.5 s pauses: 300 s → two parts near 150 s.
    segments = [seg(i, i * 10, i * 10 + 9.5) for i in range(30)]
    parts = split_parts(segments, 300, 170)
    assert spans(parts) == [(0, 149.75), (149.75, 300)]


def test_parts_never_exceed_the_limit():
    lengths = [40, 40, 40, 5, 5, 40, 40, 40, 40]
    segments, t = [], 0.0
    for i, length in enumerate(lengths):
        segments.append(seg(i, t, t + length))
        t += length + 1
    parts = split_parts(segments, t, 100)
    assert all(p.duration <= 100 for p in parts)
    assert parts[0].start == 0 and parts[-1].end == t
    assert all(a.end == b.start for a, b in zip(parts, parts[1:], strict=False))
