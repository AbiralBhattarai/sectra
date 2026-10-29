from src.domain.exceptions import AppValidationException
from src.domain.models.edl import Edl
from src.domain.models.speech import TimeSpan

#: Shortest range the editor can produce; anything smaller is a slip of the mouse.
MIN_RANGE_SECONDS = 0.1


def validate_edl(edl: Edl, source_duration: float) -> None:
    """Reject edits the renderer couldn't honour: ranges must be non-empty, inside
    the source, in order and non-overlapping."""
    if not edl.ranges:
        raise AppValidationException("A clip needs at least one range")
    previous_end = 0.0
    for index, span in enumerate(edl.ranges):
        if span.duration < MIN_RANGE_SECONDS:
            raise AppValidationException(f"Range {index + 1} is shorter than {MIN_RANGE_SECONDS}s")
        if span.start < previous_end - 1e-6:
            raise AppValidationException(f"Range {index + 1} overlaps or precedes the one before")
        if span.end > source_duration + 1e-3:
            raise AppValidationException(f"Range {index + 1} ends after the video does")
        previous_end = span.end
    for index, overlay in enumerate(edl.overlays):
        if not overlay.text.strip():
            raise AppValidationException(f"Overlay {index + 1} has no text")
        if overlay.end - overlay.start < MIN_RANGE_SECONDS:
            raise AppValidationException(f"Overlay {index + 1} ends before it starts")


def edl_bounds(edl: Edl) -> TimeSpan:
    """Source span from the first kept second to the last."""
    return TimeSpan(start=edl.ranges[0].start, end=edl.ranges[-1].end)
