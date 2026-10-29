from enum import StrEnum


class CaptionStyle(StrEnum):
    """Caption presets; the browser preview and the ASS renderer implement each one."""

    BOLD_HIGHLIGHT = "bold-highlight"  # few big words at a time, current word highlighted
    CLEAN = "clean"  # sentence-case lines near the bottom
    BOXED = "boxed"  # lines on a dark box
    NONE = "none"
