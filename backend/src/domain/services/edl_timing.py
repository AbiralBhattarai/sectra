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
