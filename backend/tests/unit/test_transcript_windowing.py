from src.domain.services.transcript_windowing import window_segments
from tests.unit.transcript_builders import evenly, seg


def ids(windows):
    return [[s.id for s in window] for window in windows]


def test_short_transcript_is_one_window():
    assert ids(window_segments(evenly(5), window=300)) == [[0, 1, 2, 3, 4]]


def test_windows_overlap_and_cover_everything():
    windows = window_segments(evenly(30), window=100, overlap=30)  # 10 s segments
    assert ids(windows)[:2] == [list(range(0, 10)), list(range(7, 17))]
    covered = {s.id for window in windows for s in window}
    assert covered == set(range(30))
    assert all(window[-1].end - window[0].start <= 100 for window in windows)


def test_overlong_segment_gets_its_own_window_and_progress_continues():
    segments = [seg(0, 0, 10), seg(1, 10, 500), seg(2, 500, 510)]
    assert ids(window_segments(segments, window=100, overlap=30)) == [[0], [1], [2]]


def test_empty_transcript():
    assert window_segments([]) == []
