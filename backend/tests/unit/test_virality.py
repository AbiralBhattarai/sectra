import pytest

from src.domain.services.virality import (
    RUBRIC_WEIGHTS,
    blend_with_ranking,
    high_energy_segments,
    rubric_score,
)
from tests.unit.transcript_builders import evenly


def ratings(**overrides):
    return {name: 5 for name in RUBRIC_WEIGHTS} | overrides


def test_weights_sum_to_one():
    assert sum(RUBRIC_WEIGHTS.values()) == pytest.approx(1.0)


def test_rubric_score_weights_the_hook_most():
    assert rubric_score(ratings()) == 50
    assert rubric_score({name: 10 for name in RUBRIC_WEIGHTS}) == 100
    assert rubric_score(ratings(hook=10)) > rubric_score(ratings(shareability=10))
    assert rubric_score(ratings(hook=99)) == rubric_score(ratings(hook=10))  # clamped


def test_loudest_fifth_of_segments_is_high_energy():
    segments = evenly(10)  # 10 s each
    peaks = [0.1] * 100
    peaks[20:30] = [0.8] * 10  # segment 2
    peaks[70:80] = [0.6] * 10  # segment 7
    peaks[50:60] = [0.3] * 10  # segment 5 is only third loudest
    assert high_energy_segments(segments, peaks, per_second=1) == {2, 7}
    assert high_energy_segments(segments, [], per_second=1) == set()


def test_blend_with_ranking():
    # Rubric 90/60/40; ranked C (index 2), B, A.
    assert blend_with_ranking([90, 60, 40], [2, 1, 0]) == [45, 55, 70]
    # Candidates the ranking leaves out count as last.
    assert blend_with_ranking([80, 80, 80], [1]) == [40, 90, 40]
    assert blend_with_ranking([77], [0]) == [77]
