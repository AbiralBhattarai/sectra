import pytest

from src.domain.models.edl import Color
from src.domain.services.color_grading import matrix, transfer

IDENTITY = ((1, 0, 0), (0, 1, 0), (0, 0, 1))


def approx(m):
    return [pytest.approx(row, abs=1e-6) for row in m]


def test_a_neutral_grade_changes_nothing():
    assert transfer(Color()) == (1, 0)
    assert list(matrix(Color())) == approx(IDENTITY)


def test_brightness_then_contrast_is_one_linear_transfer():
    # CSS: brightness(1.2) contrast(0.5) → (v·1.2 − 0.5)·0.5 + 0.5
    assert transfer(Color(brightness=1.2, contrast=0.5)) == pytest.approx((0.6, 0.25))


def test_zero_saturation_gives_every_channel_the_same_luma_weights():
    rows = matrix(Color(saturation=0))
    assert rows[0] == rows[1] == rows[2] == pytest.approx((0.213, 0.715, 0.072))


def test_only_a_zero_hue_rotation_is_the_identity():
    assert list(matrix(Color(hue=180))) != approx(IDENTITY)
    assert list(matrix(Color(hue=0))) == approx(IDENTITY)
