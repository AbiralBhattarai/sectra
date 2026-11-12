"""Output frame size and crop window. Mirrors frontend/src/editor/crop.ts."""

from src.domain.enums.aspect_ratio_enum import AspectRatio
from src.domain.models.edl import Crop, Edl, ImageSegment, Segment, VideoSegment
from src.domain.services.sequence import is_clip_video

OUTPUT_SIZES: dict[AspectRatio, tuple[int, int]] = {
    AspectRatio.VERTICAL: (1080, 1920),
    AspectRatio.SQUARE: (1080, 1080),
    AspectRatio.LANDSCAPE: (1920, 1080),
}


def crop_window(
    source_width: int, source_height: int, aspect: AspectRatio, crop: Crop, split: bool = False
) -> tuple[int, int, int, int]:
    """(x, y, width, height) of the source region that becomes the output frame: the
    largest window of the output aspect that fits, shrunk by ``crop.scale`` and centred
    on ``crop.x/y`` but kept inside the source. Sizes are even (yuv420p needs it).

    With ``split`` the window is for the left half of the source filling the top half
    of the frame; the right half's window is the same, shifted by ``source_width // 2``."""
    out_width, out_height = OUTPUT_SIZES[aspect]
    if split:
        source_width //= 2
        out_height //= 2
    ratio = out_width / out_height
    width, height = float(source_width), source_width / ratio
    if height > source_height:
        height = float(source_height)
        width = source_height * ratio
    width = _even(width / crop.scale, source_width)
    height = _even(height / crop.scale, source_height)
    x = _clamp(round(crop.x * source_width - width / 2), 0, source_width - width)
    y = _clamp(round(crop.y * source_height - height / 2), 0, source_height - height)
    return x, y, width, height


def tracking_on(edl: Edl) -> bool:
    return edl.tracking is not None and edl.tracking.enabled


def follows_tracking(edl: Edl, segment: Segment) -> bool:
    """Face tracking frames clip-video segments that have no crop of their own."""
    return tracking_on(edl) and is_clip_video(segment) and segment.crop is None


def split_applies(edl: Edl, segment: Segment) -> bool:
    """Split screen applies to clip-video segments; face tracking wins over it."""
    return edl.split_screen and not tracking_on(edl) and is_clip_video(segment)


def crop_at(edl: Edl, segment: Segment, t: float) -> Crop:
    """The crop in effect at media time ``t`` of ``segment`` (source seconds, or seconds
    into an image): its own crop, animated towards ``crop_to`` over the segment (Ken
    Burns); else with face tracking, the shot starting at or before ``t`` (else the first)
    at the shared zoom; else ``edl.crop``. Mirrors ``cropAt`` in crop.ts."""
    if segment.crop is not None:
        target = getattr(segment, "crop_to", None)
        if target is None:
            return segment.crop
        p = progress(segment, t)
        a = segment.crop
        return Crop(
            x=a.x + (target.x - a.x) * p,
            y=a.y + (target.y - a.y) * p,
            scale=a.scale + (target.scale - a.scale) * p,
        )
    if follows_tracking(edl, segment):
        shots = edl.tracking.shots
        shot = next((s for s in reversed(shots) if s.start <= t), shots[0])
        return Crop(x=shot.x, y=shot.y, scale=edl.crop.scale)
    return edl.crop


def progress(segment: Segment, t: float) -> float:
    """How far (0..1) media time ``t`` is through the segment."""
    if isinstance(segment, VideoSegment):
        fraction = (t - segment.start) / (segment.end - segment.start)
    elif isinstance(segment, ImageSegment):
        fraction = t / segment.duration
    else:
        return 0.0
    return min(max(fraction, 0.0), 1.0)


def _even(value: float, limit: int) -> int:
    return min(max(2, int(round(value / 2)) * 2), limit - limit % 2)


def _clamp(value: int, low: int, high: int) -> int:
    return min(max(value, low), high)
