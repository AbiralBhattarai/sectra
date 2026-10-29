"""Turns Silero VAD frame probabilities into speech segments.

A simplified port of Silero's ``get_speech_timestamps``: speech starts when a frame
reaches ``threshold`` and ends once probability has stayed below
``threshold - 0.15`` for ``min_silence`` seconds; segments shorter than
``min_speech`` are dropped.
"""

from src.domain.models.speech import TimeSpan


def speech_segments(
    probabilities: list[float],
    frame_seconds: float,
    threshold: float = 0.5,
    min_silence: float = 0.1,
    min_speech: float = 0.25,
) -> list[TimeSpan]:
    release = threshold - 0.15
    segments: list[TimeSpan] = []
    start: float | None = None
    silence_since: float | None = None

    for index, probability in enumerate(probabilities):
        now = index * frame_seconds
        if probability >= threshold:
            silence_since = None
            if start is None:
                start = now
        elif start is not None and probability < release:
            if silence_since is None:
                silence_since = now
            elif now - silence_since >= min_silence:
                _close(segments, start, silence_since, min_speech)
                start = silence_since = None

    if start is not None:
        _close(segments, start, len(probabilities) * frame_seconds, min_speech)
    return segments


def _close(segments: list[TimeSpan], start: float, end: float, min_speech: float) -> None:
    if end - start >= min_speech:
        segments.append(TimeSpan(start=start, end=end))
