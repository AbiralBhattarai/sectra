from src.domain.models.media import MediaInfo, NormalizePlan

MAX_SOURCE_SHORT_SIDE = 1080


def fit_short_side(width: int, height: int, max_short_side: int) -> tuple[int, int] | None:
    """Size that brings the shorter side down to ``max_short_side`` keeping the aspect
    ratio, with both sides even (H.264 needs that). None when already small enough."""
    short = min(width, height)
    if short <= max_short_side:
        return None
    scale = max_short_side / short
    return _even(width * scale), _even(height * scale)


def plan_normalization(info: MediaInfo) -> NormalizePlan:
    scale_to = fit_short_side(info.width, info.height, MAX_SOURCE_SHORT_SIDE)
    reencode_video = (
        scale_to is not None
        or info.video_codec != "h264"
        or info.pixel_format != "yuv420p"
        or info.width % 2 != 0
        or info.height % 2 != 0
    )
    return NormalizePlan(
        scale_to=scale_to,
        reencode_video=reencode_video,
        reencode_audio=info.audio_codec != "aac",
    )


def _even(value: float) -> int:
    return max(2, round(value / 2) * 2)
