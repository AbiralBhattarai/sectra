import random
from datetime import datetime, timedelta

from poster.schedule import (
    daily_cap_reached,
    due_at,
    in_active_hours,
    next_slot,
    spacing,
)

HOURS = (9, 23)


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute)


def test_ten_a_day_over_fourteen_hours_is_every_84_minutes():
    assert spacing(10, HOURS) == timedelta(minutes=84)


def test_gaps_are_jittered_around_the_spacing_and_stay_in_bounds():
    rng = random.Random(7)
    gaps = [
        next_slot(at(20, 10), at(20, 10), 10, HOURS, 0.25, rng) - at(20, 10) for _ in range(200)
    ]
    assert min(gaps) >= timedelta(minutes=63) and max(gaps) <= timedelta(minutes=105)
    assert len(set(gaps)) > 150  # not clockwork


def test_outside_active_hours_waits_for_the_window():
    assert in_active_hours(at(20, 6), HOURS) == at(20, 9)
    assert in_active_hours(at(20, 12, 30), HOURS) == at(20, 12, 30)
    assert in_active_hours(at(20, 23, 10), HOURS) == at(21, 9)


def test_first_post_is_due_now_inside_the_window():
    assert due_at([], at(20, 14), 10, HOURS, 0.25, random.Random(1)) == at(20, 14)


def test_daily_cap_pushes_to_tomorrow():
    posted = [at(20, 9) + timedelta(minutes=84 * i) for i in range(10)]
    assert daily_cap_reached(posted, at(20, 22), 10)
    assert due_at(posted, at(20, 22), 10, HOURS, 0.25, random.Random(1)) == at(21, 9)
    # Yesterday's posts don't count against today.
    assert not daily_cap_reached(posted, at(21, 9), 10)


def test_planned_slot_is_kept_until_a_newer_post_supersedes_it():
    posted = [at(20, 10)]
    planned = at(20, 11, 30)
    assert due_at(posted, at(20, 10, 5), 10, HOURS, 0.25, random.Random(1), planned) == planned
    # Planned before the last post (it was used): a fresh slot after that post.
    stale = due_at(
        [*posted, at(20, 11, 31)], at(20, 11, 32), 10, HOURS, 0.0, random.Random(1), planned
    )
    assert stale == at(20, 11, 31) + timedelta(minutes=84)
