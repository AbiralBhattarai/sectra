"""Input port: face tracking (active-speaker shots) for a clip."""

from typing import Protocol
from uuid import UUID

from src.domain.models.edl import Tracking
from src.domain.models.job import Job


class ClipTrackingPort(Protocol):
    async def request_tracking(self, clip_id: UUID) -> Job:
        """A TRACK job covering the clip's current ranges: an existing queued, running or
        finished one when it covers them, else a newly queued one."""
        ...

    async def tracking_result(self, job_id: UUID) -> Tracking:
        """Shots of a finished TRACK job; raises ``NotFoundException`` if it doesn't
        exist or hasn't succeeded."""
        ...
