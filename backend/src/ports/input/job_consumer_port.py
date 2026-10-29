"""Input port: a driving adapter that pulls job messages off a queue."""

from collections.abc import Awaitable, Callable
from typing import Protocol

MessageHandler = Callable[[dict[str, str]], Awaitable[None]]
"""Async callback invoked once per consumed message with its fields."""


class JobConsumerPort(Protocol):
    """The handler is wired in the composition root, so the transport stays unaware
    of what the message means."""

    async def consume(self, stream: str, handler: MessageHandler) -> None:
        """Consume ``stream``, invoking ``handler`` per message. Runs until ``stop`` is called.

        A message is acknowledged only after its handler returns, so a crash mid-job
        redelivers it when the consumer restarts.
        """
        ...

    async def stop(self) -> None:
        """Stop fetching new messages and wait for in-flight handlers to finish."""
        ...
