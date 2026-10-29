from enum import StrEnum


class OverlayStyle(StrEnum):
    """Text overlay presets; preview and renderer implement each one."""

    TITLE = "title"  # big bold text on a dark box, for a hook line
    LABEL = "label"  # smaller plain text with a shadow
