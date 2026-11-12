from collections.abc import Mapping
from uuid import UUID

from src.domain.exceptions import AppValidationException
from src.domain.models.edl import Edl, FreezeSegment, VideoSegment
from src.domain.models.speech import TimeSpan
from src.domain.services.sequence import EPSILON, is_clip_video, output_duration, segment_length

#: Shortest segment the editor can produce; anything smaller is a slip of the mouse.
MIN_SEGMENT_SECONDS = 0.1


def validate_edl(
    edl: Edl, source_duration: float, media_durations: Mapping[UUID, float] | None = None
) -> None:
    """Reject edits the renderer couldn't honour. ``media_durations`` holds the length of
    every other video the EDL uses. Overlays, B-roll and markers past the end of the clip
    are allowed (the render drops or cuts them), so a ripple delete never fails on them."""
    media_durations = media_durations or {}
    if not edl.segments:
        raise AppValidationException("A clip needs at least one segment")
    _unique_ids(edl)
    lengths = [segment_length(s) for s in edl.segments]
    for index, segment in enumerate(edl.segments):
        label = f"Segment {index + 1} ({segment.id})"
        if lengths[index] < MIN_SEGMENT_SECONDS - EPSILON:
            raise AppValidationException(f"{label} is shorter than {MIN_SEGMENT_SECONDS}s")
        if isinstance(segment, VideoSegment | FreezeSegment):
            duration = (
                source_duration if segment.media is None else media_durations.get(segment.media)
            )
            if duration is None:
                raise AppValidationException(
                    f"{label} uses video {segment.media}, which isn't ready"
                )
            last = segment.end if isinstance(segment, VideoSegment) else segment.at
            if last > duration + 1e-3:
                raise AppValidationException(f"{label} runs past the end of its video")
        if (
            isinstance(segment, VideoSegment)
            and segment.audio_fade_in + segment.audio_fade_out > lengths[index] + EPSILON
        ):
            raise AppValidationException(f"{label}'s audio fades are longer than it is")
        if segment.transition and index > 0:
            half = min(lengths[index - 1], lengths[index]) / 2
            if segment.transition.duration > half + EPSILON:
                raise AppValidationException(
                    f"{label}'s transition ({segment.transition.duration:.2f}s) is longer than "
                    f"half of it or of the segment before ({half:.2f}s max)"
                )
    total = output_duration(edl.segments)
    if edl.fade_in + edl.fade_out > total + EPSILON:
        raise AppValidationException("The clip's fade in and fade out are longer than the clip")
    for index, overlay in enumerate(edl.overlays):
        if not overlay.text.strip():
            raise AppValidationException(f"Overlay {index + 1} ({overlay.id}) has no text")
        if overlay.end - overlay.start < MIN_SEGMENT_SECONDS:
            raise AppValidationException(
                f"Overlay {index + 1} ({overlay.id}) ends before it starts"
            )
    for index, item in enumerate(edl.broll):
        label = f"B-roll {index + 1} ({item.id})"
        if item.fade * 2 > item.duration + EPSILON:
            raise AppValidationException(f"{label}'s fades are longer than it is")
        if item.media is not None:
            duration = media_durations.get(item.media)
            if duration is None:
                raise AppValidationException(f"{label} uses video {item.media}, which isn't ready")
            if item.media_start + item.duration > duration + 1e-3:
                raise AppValidationException(f"{label} runs past the end of its video")
    if edl.tracking is not None:
        shots = edl.tracking.shots
        if not shots:
            raise AppValidationException("Face tracking has no shots")
        if abs(shots[0].start - edl.tracking.span.start) > EPSILON:
            raise AppValidationException("The first shot must start where tracking does")
        if any(b.start <= a.start for a, b in zip(shots, shots[1:], strict=False)):
            raise AppValidationException("Shots must be in order")


def edl_bounds(edl: Edl) -> TimeSpan | None:
    """Span of the clip's own video that the edit uses, first second to last; None when
    every segment comes from other media."""
    times: list[float] = []
    for segment in edl.segments:
        if isinstance(segment, VideoSegment) and segment.media is None:
            times += [segment.start, segment.end]
        elif isinstance(segment, FreezeSegment) and is_clip_video(segment):
            times.append(segment.at)
    return TimeSpan(start=min(times), end=max(times)) if times else None


def _unique_ids(edl: Edl) -> None:
    seen: set[str] = set()
    for item in [*edl.segments, *edl.overlays, *edl.broll, *edl.markers]:
        if item.id in seen:
            raise AppValidationException(f"Two items share the id {item.id}")
        seen.add(item.id)
