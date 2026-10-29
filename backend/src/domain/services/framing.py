"""Output frame size and crop window. Mirrors frontend/src/editor/crop.ts."""

from src.domain.enums.aspect_ratio_enum import AspectRatio
from src.domain.models.edl import Crop

OUTPUT_SIZES: dict[AspectRatio, tuple[int, int]] = {
    AspectRatio.VERTICAL: (1080, 1920),
    AspectRatio.SQUARE: (1080, 1080),
    AspectRatio.LANDSCAPE: (1920, 1080),
}


def crop_window(
    source_width: int, source_height: int, aspect: AspectRatio, crop: Crop
) -> tuple[int, int, int, int]:
    """(x, y, width, height) of the source region that becomes the output frame: the
    largest window of the output aspect that fits, shrunk by ``crop.scale`` and centred
    on ``crop.x/y`` but kept inside the source. Sizes are even (yuv420p needs it)."""
    out_width, out_height = OUTPUT_SIZES[aspect]
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


def _even(value: float, limit: int) -> int:
    return min(max(2, int(round(value / 2)) * 2), limit - limit % 2)


def _clamp(value: int, low: int, high: int) -> int:
    return min(max(value, low), high)
