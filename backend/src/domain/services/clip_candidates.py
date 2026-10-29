"""Turns LLM candidates into clips: resolve segment ids to times, fit the length
limits on segment boundaries, drop near-duplicates, keep the best."""

from src.domain.models.clip import ClipCandidate
from src.domain.models.speech import TimeSpan
from src.domain.models.transcript import Segment

#: Two clips overlapping more than this (intersection over union) are duplicates.
DUPLICATE_IOU = 0.5


def select_clips(
    candidates: list[ClipCandidate],
    segments: list[Segment],
    min_seconds: float,
    max_seconds: float,
    max_count: int,
) -> list[tuple[ClipCandidate, TimeSpan]]:
    by_id = {segment.id: index for index, segment in enumerate(segments)}
    fitted: list[tuple[ClipCandidate, TimeSpan]] = []
    for candidate in candidates:
        first = by_id.get(candidate.start_segment)
        last = by_id.get(candidate.end_segment)
        if first is None or last is None or last < first:
            continue  # hallucinated or reversed ids
        bounds = _fit(segments, first, last, min_seconds, max_seconds)
        if bounds is not None:
            fitted.append((candidate, _span(segments, *bounds)))

    kept: list[tuple[ClipCandidate, TimeSpan]] = []
    for candidate, span in sorted(fitted, key=lambda item: item[0].score, reverse=True):
        if all(_iou(span, other) <= DUPLICATE_IOU for _, other in kept):
            kept.append((candidate, span))
        if len(kept) == max_count:
            break
    return sorted(kept, key=lambda item: item[1].start)


def _fit(
    segments: list[Segment], first: int, last: int, min_seconds: float, max_seconds: float
) -> tuple[int, int] | None:
    """Grow (following segments first, then preceding) or shrink (from the end) the
    segment range until its duration is within limits; None when impossible."""

    def length(a: int, b: int) -> float:
        return _span(segments, a, b).duration

    while length(first, last) > max_seconds and last > first:
        last -= 1
    while length(first, last) < min_seconds:
        if last + 1 < len(segments) and length(first, last + 1) <= max_seconds:
            last += 1
        elif first > 0 and length(first - 1, last) <= max_seconds:
            first -= 1
        else:
            break
    if min_seconds <= length(first, last) <= max_seconds:
        return first, last
    return None


def _span(segments: list[Segment], first: int, last: int) -> TimeSpan:
    """From the first spoken word to the last, so clips don't open or close on silence."""
    start_segment, end_segment = segments[first], segments[last]
    start = start_segment.words[0].start if start_segment.words else start_segment.start
    end = end_segment.words[-1].end if end_segment.words else end_segment.end
    return TimeSpan(start=start, end=max(start, end))


def _iou(a: TimeSpan, b: TimeSpan) -> float:
    overlap = max(0.0, min(a.end, b.end) - max(a.start, b.start))
    union = max(a.end, b.end) - min(a.start, b.start)
    return overlap / union if union > 0 else 0.0
