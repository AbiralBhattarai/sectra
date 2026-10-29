import pytest

from src.domain.models.media import MediaInfo
from src.domain.services.media_rules import fit_short_side, plan_normalization


@pytest.mark.parametrize(
    ("size", "limit", "expected"),
    [
        ((3840, 2160), 1080, (1920, 1080)),  # 4K landscape
        ((2160, 3840), 1080, (1080, 1920)),  # 4K portrait: the width is the short side
        ((1920, 1080), 1080, None),  # already at the limit
        ((1280, 720), 1080, None),
        ((2560, 1080), 720, (1706, 720)),  # odd result rounded to even
        ((1920, 1440), 1080, (1440, 1080)),
    ],
)
def test_fit_short_side(size, limit, expected):
    assert fit_short_side(*size, limit) == expected


def info(**overrides) -> MediaInfo:
    defaults = dict(
        duration=10.0,
        width=1280,
        height=720,
        video_codec="h264",
        pixel_format="yuv420p",
        audio_codec="aac",
    )
    return MediaInfo(**defaults | overrides)


def test_compliant_file_is_stream_copied():
    plan = plan_normalization(info())
    assert (plan.scale_to, plan.reencode_video, plan.reencode_audio) == (None, False, False)


def test_oversized_file_is_scaled_and_reencoded():
    plan = plan_normalization(info(width=3840, height=2160))
    assert plan.scale_to == (1920, 1080)
    assert plan.reencode_video


@pytest.mark.parametrize(
    "overrides", [{"video_codec": "vp9"}, {"pixel_format": "yuv444p"}, {"width": 1281}]
)
def test_incompatible_video_is_reencoded_without_scaling(overrides):
    plan = plan_normalization(info(**overrides))
    assert plan.reencode_video
    assert plan.scale_to is None


def test_non_aac_audio_is_reencoded_alone():
    plan = plan_normalization(info(audio_codec="opus"))
    assert (plan.reencode_video, plan.reencode_audio) == (False, True)
