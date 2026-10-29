"""Compact transcript builders for tests."""

from src.domain.models.transcript import Segment, Transcript, Word


def seg(id: int, start: float, end: float, text: str = "") -> Segment:
    """A segment whose single word spans it exactly."""
    text = text or f"segment {id}"
    return Segment(
        id=id, start=start, end=end, text=text, words=[Word(text=text, start=start, end=end)]
    )


def evenly(count: int, length: float = 10.0) -> list[Segment]:
    """``count`` back-to-back segments of ``length`` seconds."""
    return [seg(i, i * length, (i + 1) * length) for i in range(count)]


def transcript(segments: list[Segment]) -> Transcript:
    return Transcript(language="en", segments=segments)
