from enum import StrEnum


class TransitionType(StrEnum):
    """Transitions between segments. Values are ffmpeg ``xfade`` transition names; the
    browser preview approximates each one with CSS."""

    FADE = "fade"
    DISSOLVE = "dissolve"
    FADE_BLACK = "fadeblack"
    FADE_WHITE = "fadewhite"
    WIPE_LEFT = "wipeleft"
    WIPE_RIGHT = "wiperight"
    WIPE_UP = "wipeup"
    WIPE_DOWN = "wipedown"
    SLIDE_LEFT = "slideleft"
    SLIDE_RIGHT = "slideright"
    SLIDE_UP = "slideup"
    SLIDE_DOWN = "slidedown"
    CIRCLE_OPEN = "circleopen"
    ZOOM_IN = "zoomin"
    PIXELIZE = "pixelize"
