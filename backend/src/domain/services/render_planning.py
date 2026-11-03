from src.domain.enums.caption_style_enum import CaptionStyle
from src.domain.models.edl import Edl
from src.domain.models.render import CaptionCue, CropBox, CropMove, RenderPlan, TimedText
from src.domain.services.caption_pages import hide_time, paginate
from src.domain.services.edl_timing import output_duration, source_to_output
from src.domain.services.framing import OUTPUT_SIZES, crop_at, crop_window, tracking_on

_MIN_OVERLAY_SECONDS = 0.1


def plan_render(edl: Edl, source_width: int, source_height: int) -> RenderPlan:
    width, height = OUTPUT_SIZES[edl.aspect]
    tracking = tracking_on(edl)
    split = edl.split_screen and not tracking  # tracking wins; the UI keeps them exclusive
    moves = _crop_moves(edl, source_width, source_height) if tracking else []
    first = crop_at(edl, edl.ranges[0].start)
    x, y, crop_width, crop_height = crop_window(
        source_width, source_height, edl.aspect, first, split
    )
    crops = [CropBox(x=x, y=y, width=crop_width, height=crop_height)]
    if split:
        crops.append(crops[0].model_copy(update={"x": x + source_width // 2}))
    duration = output_duration(edl.ranges)
    overlays = [
        o.model_copy(update={"end": min(o.end, duration)})
        for o in edl.overlays
        if min(o.end, duration) - o.start >= _MIN_OVERLAY_SECONDS
    ]
    return RenderPlan(
        ranges=edl.ranges,
        crops=crops,
        crop_moves=moves if len(moves) > 1 else [],
        width=width,
        height=height,
        duration=duration,
        caption_style=edl.captions.style,
        captions=_cues(edl, edl.captions.style),
        subtitles=_cues(edl, CaptionStyle.CLEAN),
        overlays=overlays,
        music_volume=edl.music.volume if edl.music else None,
        duck_music=bool(edl.music and edl.music.duck),
    )


def _crop_moves(edl: Edl, source_width: int, source_height: int) -> list[CropMove]:
    """Where the crop window jumps on the output timeline: at each range start and at
    each shot start inside a range. Zoom is shared, so only the position changes."""
    moves: list[CropMove] = []
    elapsed = 0.0
    for span in edl.ranges:
        starts = [s.start for s in edl.tracking.shots if span.start < s.start < span.end]
        for t in [span.start, *starts]:
            x, y, _, _ = crop_window(source_width, source_height, edl.aspect, crop_at(edl, t))
            if not moves or (moves[-1].x, moves[-1].y) != (x, y):
                moves.append(CropMove(time=round(elapsed + t - span.start, 3), x=x, y=y))
        elapsed += span.duration
    return moves


def _cues(edl: Edl, style: CaptionStyle) -> list[CaptionCue]:
    """Paginate in source time (as the preview does), then move to output time."""
    pages = paginate(edl.captions.words, style)

    def out(t: float) -> float:
        return round(source_to_output(t, edl.ranges), 3)

    cues = []
    for index, page in enumerate(pages):
        words = [TimedText(text=w.text, start=out(w.start), end=out(w.end)) for w in page]
        cues.append(CaptionCue(words=words, start=words[0].start, end=out(hide_time(pages, index))))
    return cues
