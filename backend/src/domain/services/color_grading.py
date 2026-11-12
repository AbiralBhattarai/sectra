"""Colour grades. The preview applies a ``Color`` as a CSS ``filter``; the renderer
reproduces it with the same maths: brightness and contrast are one linear transfer per
channel (CSS ``feComponentTransfer``), then saturate, sepia and hue-rotate are the 3×3
matrices from the Filter Effects spec, multiplied in CSS order."""

import math

from src.domain.enums.color_preset_enum import ColorPreset
from src.domain.models.edl import Color

PRESETS: dict[ColorPreset, Color] = {
    ColorPreset.NONE: Color(),
    ColorPreset.BW: Color(saturation=0, contrast=1.1),
    ColorPreset.WARM: Color(sepia=0.25, saturation=1.1, brightness=1.03),
    ColorPreset.COOL: Color(hue=-12, saturation=0.9, brightness=1.02),
    ColorPreset.VIVID: Color(saturation=1.45, contrast=1.1),
    ColorPreset.VINTAGE: Color(sepia=0.45, contrast=0.9, brightness=1.05, saturation=0.85),
    ColorPreset.DRAMATIC: Color(contrast=1.35, saturation=0.75, brightness=0.95),
}

Matrix = tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]


def transfer(color: Color) -> tuple[float, float]:
    """(slope, intercept) on 0..1 channel values: brightness, then contrast."""
    c = color.contrast
    return color.brightness * c, 0.5 * (1 - c)


def matrix(color: Color) -> Matrix:
    """saturate → sepia → hue-rotate as one RGB matrix (applied after ``transfer``)."""
    return _multiply(_hue(color.hue), _multiply(_sepia(color.sepia), _saturate(color.saturation)))


def _saturate(s: float) -> Matrix:
    return (
        (0.213 + 0.787 * s, 0.715 - 0.715 * s, 0.072 - 0.072 * s),
        (0.213 - 0.213 * s, 0.715 + 0.285 * s, 0.072 - 0.072 * s),
        (0.213 - 0.213 * s, 0.715 - 0.715 * s, 0.072 + 0.928 * s),
    )


def _sepia(a: float) -> Matrix:
    k = 1 - a
    return (
        (0.393 + 0.607 * k, 0.769 - 0.769 * k, 0.189 - 0.189 * k),
        (0.349 - 0.349 * k, 0.686 + 0.314 * k, 0.168 - 0.168 * k),
        (0.272 - 0.272 * k, 0.534 - 0.534 * k, 0.131 + 0.869 * k),
    )


def _hue(degrees: float) -> Matrix:
    cos, sin = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    return (
        (0.213 + cos * 0.787 - sin * 0.213, 0.715 - cos * 0.715 - sin * 0.715,
         0.072 - cos * 0.072 + sin * 0.928),
        (0.213 - cos * 0.213 + sin * 0.143, 0.715 + cos * 0.285 + sin * 0.140,
         0.072 - cos * 0.072 - sin * 0.283),
        (0.213 - cos * 0.213 - sin * 0.787, 0.715 - cos * 0.715 + sin * 0.715,
         0.072 + cos * 0.928 + sin * 0.072),
    )  # fmt: skip


def _multiply(a: Matrix, b: Matrix) -> Matrix:
    """a · b (b is applied first)."""
    return tuple(
        tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)) for i in range(3)
    )  # type: ignore[return-value]
