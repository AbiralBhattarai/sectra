"""Splitting a narrated story into parts that each fit a platform's length limit."""

import math

from src.domain.models.speech import TimeSpan
from src.domain.models.transcript import Segment


def split_parts(segments: list[Segment], duration: float, max_seconds: float) -> list[TimeSpan]:
    """Parts that tile ``[0, duration]``, each at most ``max_seconds`` where the
    transcript allows. Cuts fall in the pause between two segments, as near as possible
    to equal lengths; if that leaves a part too long, segments are packed greedily."""
    if duration <= max_seconds or len(segments) < 2:
        return [TimeSpan(start=0.0, end=duration)]
    # Candidate cut points: the middle of each pause between consecutive segments.
    cuts = [(a.end + b.start) / 2 for a, b in zip(segments, segments[1:], strict=False)]
    count = math.ceil(duration / max_seconds)
    chosen: list[float] = []
    for k in range(1, count):
        target = duration * k / count
        later = [c for c in cuts if not chosen or c > chosen[-1]]
        if later:
            chosen.append(min(later, key=lambda c: abs(c - target)))
    parts = _tile(chosen, duration)
    if all(p.duration <= max_seconds for p in parts):
        return parts
    return _tile(_greedy(cuts, max_seconds), duration)


def _greedy(cuts: list[float], max_seconds: float) -> list[float]:
    """The latest cut that keeps each part within ``max_seconds``."""
    chosen: list[float] = []
    start = 0.0
    for index, cut in enumerate(cuts):
        following = cuts[index + 1] if index + 1 < len(cuts) else math.inf
        if following - start > max_seconds and cut > start:
            chosen.append(cut)
            start = cut
    return chosen


def _tile(cuts: list[float], duration: float) -> list[TimeSpan]:
    bounds = [0.0, *[round(c, 3) for c in cuts], duration]
    return [TimeSpan(start=a, end=b) for a, b in zip(bounds, bounds[1:], strict=False) if b > a]
