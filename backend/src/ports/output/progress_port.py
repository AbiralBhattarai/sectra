"""Output port for broadcasting job progress."""

from collections.abc import AsyncIterator
from typing import Protocol

from src.domain.models.app_event import AppEvent


class ProgressPort(Protocol):
    async def publish(self, event: AppEvent) -> None:
        """Broadcast ``event`` to every subscriber."""
        ...

    def subscribe(self) -> AsyncIterator[AppEvent]:
        """Yield events published from now on, until the consumer stops iterating."""
        ...
