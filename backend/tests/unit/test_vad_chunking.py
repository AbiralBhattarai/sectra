import pytest

from src.domain.models.speech import TimeSpan
from src.domain.services.vad_chunking import build_chunks


def s(start, end):
    return TimeSpan(start=start, end=end)


def spans(chunks):
    return [(round(c.start, 2), round(c.end, 2)) for c in chunks]


def test_close_segments_merge_into_one_padded_chunk():
    chunks = build_chunks([s(1, 3), s(3.5, 6)], duration=100)
    assert spans(chunks) == [(0.8, 6.2)]


def test_long_silence_starts_a_new_chunk():
    chunks = build_chunks([s(1, 3), s(10, 12)], duration=100)
    assert spans(chunks) == [(0.8, 3.2), (9.8, 12.2)]


def test_chunks_break_in_pauses_to_respect_max_length():
    segments = [s(0, 10), s(11, 20), s(21, 29), s(30, 40)]
    chunks = build_chunks(segments, duration=100, max_chunk=30)
    assert spans(chunks) == [(0.0, 29.2), (29.8, 40.2)]
    assert all(c.duration <= 30 for c in chunks)


def test_adjacent_chunks_never_overlap():
    # Gap of 0.3 s is narrower than 2 × padding, and the length cap forces a split.
    chunks = build_chunks([s(0, 25), s(25.3, 35)], duration=100, max_chunk=30)
    assert chunks[0].end <= chunks[1].start


def test_segment_longer_than_max_is_split_evenly():
    chunks = build_chunks([s(0, 75)], duration=75, max_chunk=30)
    assert spans(chunks) == [(0.0, 25.0), (25.0, 50.0), (50.0, 75.0)]


def test_padding_is_clamped_to_the_video():
    chunks = build_chunks([s(0.1, 4.95)], duration=5)
    assert spans(chunks) == [(0.0, 5.0)]


@pytest.mark.parametrize("segments", [[]])
def test_no_speech_no_chunks(segments):
    assert build_chunks(segments, duration=10) == []
