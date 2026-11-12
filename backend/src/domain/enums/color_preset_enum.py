from enum import StrEnum


class ColorPreset(StrEnum):
    """Named looks; each is a fixed ``Color`` (domain/services/color_grading.py)."""

    NONE = "none"
    BW = "bw"
    WARM = "warm"
    COOL = "cool"
    VIVID = "vivid"
    VINTAGE = "vintage"
    DRAMATIC = "dramatic"
