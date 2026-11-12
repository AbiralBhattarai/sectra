from collections.abc import Mapping

from src.domain.enums.broll_layout_enum import BrollLayout
from src.domain.enums.caption_style_enum import CaptionStyle
from src.domain.exceptions import MediaProcessingException
from src.domain.models.edl import BrollItem, Crop, Edl, ImageSegment, Segment, VideoSegment
from src.domain.models.render import (
    CropBox,
    CropMove,
    MediaSource,
    PlannedBroll,
    PlannedSegment,
    RenderPlan,
)
from src.domain.services.framing import (
    OUTPUT_SIZES,
    crop_at,
    crop_window,
    follows_tracking,
    split_applies,
)
from src.domain.services.sequence import Placed, caption_cues, layout, output_duration

_MIN_OVERLAY_SECONDS = 0.1
#: Key of the clip's own video among a render's inputs.
MAIN = "main"


def media_key(item: Segment | BrollItem) -> str:
    """Which input a segment or B-roll item reads: the clip's video, another video (by
    id) or an image (``image:<file>``)."""
    image = getattr(item, "image", None)
    if image is not None:
        return f"image:{image}"
    media = getattr(item, "media", None)
    return MAIN if media is None else str(media)


def media_keys(edl: Edl) -> set[str]:
    return {media_key(item) for item in [*edl.segments, *edl.broll]}


def plan_render(edl: Edl, sources: Mapping[str, MediaSource]) -> RenderPlan:
    """``sources`` describes every input in ``media_keys(edl)``."""
    width, height = OUTPUT_SIZES[edl.aspect]
    duration = output_duration(edl.segments)
    overlays = [
        o.model_copy(update={"end": min(o.end, duration)})
        for o in edl.overlays
        if min(o.end, duration) - o.start >= _MIN_OVERLAY_SECONDS
    ]
    broll = [
        _plan_broll(item, _source(sources, item), width, height, duration)
        for item in edl.broll
        if duration - item.start >= _MIN_OVERLAY_SECONDS
    ]
    return RenderPlan(
        segments=[_plan_segment(edl, p, _source(sources, p.segment)) for p in layout(edl.segments)],
        broll=broll,
        width=width,
        height=height,
        duration=duration,
        fade_in=edl.fade_in,
        fade_out=edl.fade_out,
        caption_style=edl.captions.style,
        captions=caption_cues(edl, edl.captions.style),
        subtitles=caption_cues(edl, CaptionStyle.CLEAN),
        overlays=overlays,
        music_volume=edl.music.volume if edl.music else None,
        duck_music=bool(edl.music and edl.music.duck),
    )


def _source(sources: Mapping[str, MediaSource], item: Segment | BrollItem) -> MediaSource:
    key = media_key(item)
    if key not in sources:
        raise MediaProcessingException(f"Media {key} is missing")
    return sources[key]


def _plan_segment(edl: Edl, p: Placed, source: MediaSource) -> PlannedSegment:
    segment = p.segment
    sw, sh = source.width, source.height
    start_time = (
        segment.start if isinstance(segment, VideoSegment)
        else 0.0 if isinstance(segment, ImageSegment)
        else segment.at
    )  # fmt: skip
    split = split_applies(edl, segment)
    x, y, cw, ch = crop_window(sw, sh, edl.aspect, crop_at(edl, segment, start_time), split)
    crops = [CropBox(x=x, y=y, width=cw, height=ch)]
    if split:
        crops.append(crops[0].model_copy(update={"x": x + sw // 2}))
    crop_to = None
    target = getattr(segment, "crop_to", None)
    if segment.crop is not None and target is not None and not split:
        tx, ty, tw, th = crop_window(sw, sh, edl.aspect, target)
        crop_to = CropBox(x=tx, y=ty, width=tw, height=th)
    moves = _crop_moves(edl, segment, sw, sh) if isinstance(segment, VideoSegment) else []

    common = {
        "input": media_key(segment),
        "kind": segment.kind,
        "length": p.end - p.start,
        "crops": crops,
        "crop_to": crop_to,
        "crop_moves": moves if len(moves) > 1 else [],
        "source_width": sw,
        "source_height": sh,
        "color": None if segment.color.neutral else segment.color,
        "transition": segment.transition if p.index > 0 else None,
        "offset": round(p.start, 3),
    }
    if isinstance(segment, VideoSegment):
        return PlannedSegment(
            **common,
            source_start=segment.start,
            source_duration=segment.end - segment.start,
            speed=segment.speed,
            has_audio=source.has_audio and segment.volume > 0,
            volume=segment.volume,
            audio_fade_in=segment.audio_fade_in,
            audio_fade_out=segment.audio_fade_out,
        )
    return PlannedSegment(
        **common,
        source_start=start_time,
        source_duration=segment.duration if isinstance(segment, ImageSegment) else 0.0,
        has_audio=False,
    )


def _crop_moves(edl: Edl, segment: VideoSegment, sw: int, sh: int) -> list[CropMove]:
    """Face tracking: where the crop window jumps, in output seconds from the segment's
    start. Zoom is shared, so only the position changes."""
    if not follows_tracking(edl, segment):
        return []
    starts = [s.start for s in edl.tracking.shots if segment.start < s.start < segment.end]
    moves: list[CropMove] = []
    for t in [segment.start, *starts]:
        x, y, _, _ = crop_window(sw, sh, edl.aspect, crop_at(edl, segment, t))
        if not moves or (moves[-1].x, moves[-1].y) != (x, y):
            moves.append(CropMove(time=round((t - segment.start) / segment.speed, 3), x=x, y=y))
    return moves


def _plan_broll(
    item: BrollItem, source: MediaSource, width: int, height: int, clip_duration: float
) -> PlannedBroll:
    sw, sh = source.width, source.height
    if item.layout is BrollLayout.FULL:
        x, y, cw, ch = crop_window(sw, sh, _aspect_of(width, height), Crop())
        crop = CropBox(x=x, y=y, width=cw, height=ch)
        box = (0, 0, width, height)
    else:
        crop = CropBox(x=0, y=0, width=sw, height=sh)
        w = _even(item.size * width)
        h = _even(w * sh / sw)
        left = min(max(round(item.x * width - w / 2), 0), width - w)
        top = min(max(round(item.y * height - h / 2), 0), max(height - h, 0))
        box = (left, top, w, h)
    return PlannedBroll(
        input=media_key(item),
        kind="image" if item.image else "video",
        start=item.start,
        duration=min(item.duration, clip_duration - item.start),
        media_start=item.media_start,
        crop=crop,
        x=box[0],
        y=box[1],
        width=box[2],
        height=box[3],
        volume=item.volume,
        has_audio=source.has_audio and item.volume > 0 and item.image is None,
        fade=item.fade,
    )


def _aspect_of(width: int, height: int):
    return next(a for a, size in OUTPUT_SIZES.items() if size == (width, height))


def _even(value: float) -> int:
    return max(2, int(round(value / 2)) * 2)
