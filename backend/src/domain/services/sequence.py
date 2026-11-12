"""The main track's timeline: where each segment plays in the output, and how output time
maps back to media time. Mirrors frontend/src/editor/sequence.ts; change both together."""

from dataclasses import dataclass

from src.domain.enums.caption_style_enum import CaptionStyle
from src.domain.models.edl import Edl, Segment, VideoSegment
from src.domain.models.render import CaptionCue, TimedText
from src.domain.models.transcript import Word
from src.domain.services.caption_pages import hide_time, paginate

#: Tolerance for word/segment edge comparisons (float noise from the browser).
EPSILON = 1e-6


@dataclass(frozen=True)
class Placed:
    """A segment on the output timeline."""

    index: int
    segment: Segment
    #: Output time it starts and ends, overlaps with its neighbours' transitions included.
    start: float
    end: float
    #: The part it "owns" for captions and output-time lookups: each transition is split
    #: at its midpoint between the two segments.
    own_start: float
    own_end: float


def segment_length(segment: Segment) -> float:
    """Output seconds the segment lasts, before any transition overlap."""
    if isinstance(segment, VideoSegment):
        return (segment.end - segment.start) / segment.speed
    return segment.duration


def transition_in(segments: list[Segment], index: int) -> float:
    """Seconds segment ``index`` overlaps the one before it."""
    segment = segments[index]
    return segment.transition.duration if index > 0 and segment.transition else 0.0


def layout(segments: list[Segment]) -> list[Placed]:
    placed: list[Placed] = []
    elapsed = 0.0
    for index, segment in enumerate(segments):
        overlap = transition_in(segments, index)
        start = elapsed - overlap
        end = start + segment_length(segment)
        next_overlap = transition_in(segments, index + 1) if index + 1 < len(segments) else 0.0
        placed.append(
            Placed(index, segment, start, end, start + overlap / 2, end - next_overlap / 2)
        )
        elapsed = end
    return placed


def output_duration(segments: list[Segment]) -> float:
    return layout(segments)[-1].end if segments else 0.0


def placed_at(placed: list[Placed], t: float) -> Placed | None:
    """The segment owning output time ``t`` (the last one at the very end)."""
    for p in placed:
        if p.own_start <= t < p.own_end:
            return p
    return placed[-1] if placed and abs(t - placed[-1].own_end) < EPSILON else None


def media_time(p: Placed, t: float) -> float:
    """Media time shown at output time ``t`` inside ``p``: source seconds for video and
    freeze segments, seconds into the image for images."""
    segment = p.segment
    local = min(max(t - p.start, 0.0), segment_length(segment))
    if isinstance(segment, VideoSegment):
        return segment.start + local * segment.speed
    if segment.kind == "freeze":
        return segment.at
    return local


def output_time(p: Placed, source_t: float) -> float:
    """Where source time ``source_t`` of a video segment plays in the output."""
    segment = p.segment
    if isinstance(segment, VideoSegment):
        return p.start + (source_t - segment.start) / segment.speed
    return p.start


def is_clip_video(segment: Segment) -> bool:
    """Shows the clip's own video, so captions, tracking and split screen apply."""
    return segment.kind in ("video", "freeze") and segment.media is None


def words_inside(words: list[Word], start: float, end: float) -> list[Word]:
    return [w for w in words if w.start >= start - EPSILON and w.end <= end + EPSILON]


def caption_cues(edl: Edl, style: CaptionStyle) -> list[CaptionCue]:
    """Caption pages on the output timeline. Each clip-video segment paginates the words
    inside it on its own (a duplicated segment shows them again), and its pages are cut
    to the part of the timeline it owns."""
    cues: list[CaptionCue] = []
    for p in layout(edl.segments):
        segment = p.segment
        if not (isinstance(segment, VideoSegment) and segment.media is None):
            continue
        pages = paginate(words_inside(edl.captions.words, segment.start, segment.end), style)

        def out(t: float, p: Placed = p) -> float:
            return round(min(max(output_time(p, t), p.own_start), p.own_end), 3)

        for index, page in enumerate(pages):
            start = out(page[0].start)
            end = out(min(hide_time(pages, index), segment.end))
            if end - start < 1e-3:
                continue
            words = [TimedText(text=w.text, start=out(w.start), end=out(w.end)) for w in page]
            cues.append(CaptionCue(words=words, start=start, end=end))
    return cues
