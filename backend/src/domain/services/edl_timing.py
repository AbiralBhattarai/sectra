"""Source ↔ output time. Mirrors frontend/src/editor/edlOps.ts."""

from src.domain.models.speech import TimeSpan


def output_duration(ranges: list[TimeSpan]) -> float:
    return sum(r.duration for r in ranges)


def source_to_output(t: float, ranges: list[TimeSpan]) -> float:
    """Where source time ``t`` lands in the rendered clip (cuts collapse onto the next range)."""
    elapsed = 0.0
    for r in ranges:
        if t < r.start:
            return elapsed
        if t <= r.end:
            return elapsed + (t - r.start)
        elapsed += r.duration
    return elapsed


def output_to_source(o: float, ranges: list[TimeSpan]) -> float:
    """Source time shown at output time ``o``."""
    remaining = max(0.0, o)
    for r in ranges:
        if remaining <= r.duration:
            return r.start + remaining
        remaining -= r.duration
    return ranges[-1].end if ranges else 0.0
