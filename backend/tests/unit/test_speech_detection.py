import pytest

from src.domain.services.speech_detection import speech_segments

FRAME = 0.1


def spans(segments):
    return [(round(s.start, 2), round(s.end, 2)) for s in segments]


def test_speech_between_silences():
    probabilities = [0.0] * 5 + [0.9] * 10 + [0.0] * 5
    assert spans(speech_segments(probabilities, FRAME, min_silence=0.2)) == [(0.5, 1.5)]


def test_short_dips_do_not_split_speech():
    # One quiet frame (0.1 s) is shorter than min_silence (0.2 s).
    probabilities = [0.9] * 5 + [0.0] + [0.9] * 5 + [0.0] * 5
    assert spans(speech_segments(probabilities, FRAME, min_silence=0.2)) == [(0.0, 1.1)]


def test_hysteresis_keeps_speech_between_thresholds():
    # 0.4 is under the 0.5 start threshold but above the 0.35 release threshold.
    probabilities = [0.9] * 3 + [0.4] * 5 + [0.0] * 5
    assert spans(speech_segments(probabilities, FRAME, min_silence=0.2)) == [(0.0, 0.8)]


def test_blips_shorter_than_min_speech_are_dropped():
    probabilities = [0.0] * 3 + [0.9] * 2 + [0.0] * 5
    assert speech_segments(probabilities, FRAME, min_silence=0.2, min_speech=0.25) == []


def test_speech_running_to_the_end_is_closed():
    probabilities = [0.0] * 2 + [0.9] * 8
    assert spans(speech_segments(probabilities, FRAME)) == [(0.2, 1.0)]


@pytest.mark.parametrize("probabilities", [[], [0.0] * 10])
def test_no_speech(probabilities):
    assert speech_segments(probabilities, FRAME) == []
