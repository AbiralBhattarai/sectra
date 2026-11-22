"""Output frame size and crop window. Mirrors frontend/src/editor/crop.ts."""

from src.domain.enums.aspect_ratio_enum import AspectRatio
from src.domain.models.edl import Crop, Edl, Facecam

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
    return _window(source_width, source_height, out_width / out_height, crop)


#: Streamer-mode box: 4:3, this share of the frame's shorter side wide, inset by MARGIN.
PIP_WIDTH = 0.4
PIP_RATIO = 4 / 3
PIP_MARGIN = 0.04


def pip_box(aspect: AspectRatio) -> tuple[int, int, int, int]:
    """(x, y, width, height) of the facecam box in the output frame: bottom right.
    Mirrors ``pipBox`` in crop.ts."""
    out_width, out_height = OUTPUT_SIZES[aspect]
    short = min(out_width, out_height)
    width = int(round(short * PIP_WIDTH / 2)) * 2
    height = int(round(width / PIP_RATIO / 2)) * 2
    margin = int(round(short * PIP_MARGIN))
    return out_width - margin - width, out_height - margin - height, width, height


def facecam_window(
    source_width: int, source_height: int, aspect: AspectRatio, facecam: Facecam
) -> tuple[int, int, int, int]:
    """(x, y, width, height) of the source region shown in the facecam box: the largest
    window of the box's aspect, shrunk by ``facecam.scale``, centred on ``facecam.x/y``."""
    _, _, width, height = pip_box(aspect)
    crop = Crop(x=facecam.x, y=facecam.y, scale=facecam.scale)
    return _window(source_width, source_height, width / height, crop)


def streamer_mode(edl: Edl) -> bool:
    return edl.facecam is not None


def _window(
    source_width: int, source_height: int, ratio: float, crop: Crop
) -> tuple[int, int, int, int]:
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
    """Face tracking drives the crop (never in streamer mode)."""
    return edl.tracking is not None and edl.tracking.enabled and edl.facecam is None


def crop_at(edl: Edl, t: float) -> Crop:
    """The crop in effect at source time ``t``: ``edl.crop``, or with face tracking on,
    its zoom centred where the last shot starting at or before ``t`` (else the first)
    points. Mirrors ``cropAt`` in crop.ts."""
    if not tracking_on(edl):
        return edl.crop
    shots = edl.tracking.shots
    shot = next((s for s in reversed(shots) if s.start <= t), shots[0])
    return Crop(x=shot.x, y=shot.y, scale=edl.crop.scale)


def zoom_at(edl: Edl, t: float) -> float:
    """Magnification at source time ``t`` from ``edl.zooms`` (1 outside them, and always
    with a split screen): a punch-in holds its scale; a push eases in linearly over
    ``ramp`` seconds. Mirrors ``zoomAt`` in crop.ts."""
    if edl.split_screen and edl.facecam is None:
        return 1.0
    for zoom in edl.zooms:
        if zoom.start <= t < zoom.end:
            if zoom.ramp <= 0:
                return zoom.scale
            return 1 + (zoom.scale - 1) * min(max((t - zoom.start) / zoom.ramp, 0.0), 1.0)
    return 1.0


def _even(value: float, limit: int) -> int:
    return min(max(2, int(round(value / 2)) * 2), limit - limit % 2)


def _clamp(value: int, low: int, high: int) -> int:
    return min(max(value, low), high)
