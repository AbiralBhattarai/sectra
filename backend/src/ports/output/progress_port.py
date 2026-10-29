"""Output port for broadcasting job progress."""

from collections.abc import AsyncIterator
from typing import Protocol

from src.domain.models.job import JobEvent


class ProgressPort(Protocol):
    async def publish(self, event: JobEvent) -> None:
        """Broadcast ``event`` to every subscriber."""
        ...

    def subscribe(self) -> AsyncIterator[JobEvent]:
        """Yield events published from now on, until the consumer stops iterating."""
        ...
