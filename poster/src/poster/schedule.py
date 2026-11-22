"""When a platform may post next. Pure: everything comes in as arguments (``now`` is
local, naive or aware alike), so it's easy to test.

A platform posts at most ``per_day`` times per local day, only inside the active hours,
spaced evenly across them with random jitter: 10/day over 9-23 is one every ~84 min,
each gap somewhere in 63-105 min."""

import random
from datetime import datetime, timedelta


def spacing(per_day: int, active_hours: tuple[int, int]) -> timedelta:
    start, end = active_hours
    return timedelta(hours=end - start) / per_day


def next_slot(
    last_post: datetime | None,
    now: datetime,
    per_day: int,
    active_hours: tuple[int, int],
    jitter: float,
    rng: random.Random,
) -> datetime:
    """The earliest time after ``last_post`` to post again: one jittered gap later,
    moved into the active hours."""
    if last_post is None:
        return in_active_hours(now, active_hours)
    gap = spacing(per_day, active_hours) * (1 + rng.uniform(-jitter, jitter))
    return in_active_hours(last_post + gap, active_hours)


def in_active_hours(t: datetime, active_hours: tuple[int, int]) -> datetime:
    """``t`` itself inside the window, else the next window opening (plus up to a few
    minutes, so platforms don't all fire at exactly 9:00)."""
    start, end = active_hours
    opening = t.replace(hour=start, minute=0, second=0, microsecond=0)
    if t < opening:
        return opening
    if t.hour < end or (end == 24):
        return t
    return opening + timedelta(days=1)


def daily_cap_reached(posted: list[datetime], now: datetime, per_day: int) -> bool:
    today = now.date()
    return sum(1 for t in posted if t.date() == today) >= per_day


def tomorrow_opening(now: datetime, active_hours: tuple[int, int]) -> datetime:
    return now.replace(hour=active_hours[0], minute=0, second=0, microsecond=0) + timedelta(days=1)


def due_at(
    posted: list[datetime],
    now: datetime,
    per_day: int,
    active_hours: tuple[int, int],
    jitter: float,
    rng: random.Random,
    planned: datetime | None = None,
) -> datetime:
    """When the platform may post next, given its post times (sorted). ``planned`` is a
    slot chosen earlier (kept across restarts so the jitter isn't re-rolled)."""
    if daily_cap_reached(posted, now, per_day):
        return tomorrow_opening(now, active_hours)
    if planned is not None and (not posted or planned > posted[-1]):
        return in_active_hours(planned, active_hours)
    return next_slot(posted[-1] if posted else None, now, per_day, active_hours, jitter, rng)
