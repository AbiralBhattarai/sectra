import asyncio
import logging

from redis.asyncio import Redis
from redis.exceptions import ResponseError

from src.ports.input.job_consumer_port import MessageHandler

logger = logging.getLogger(__name__)

GROUP = "workers"


class RedisStreamConsumer:
    """Consumes one Redis stream through a consumer group, running up to ``concurrency``
    handlers at once. Messages are acked only after their handler returns."""

    def __init__(
        self,
        redis: Redis,
        consumer_name: str,
        concurrency: int,
        drain_timeout: float = 30.0,
        block_ms: int = 2000,
    ) -> None:
        self._redis = redis
        self._consumer = consumer_name
        self._slots = asyncio.Semaphore(concurrency)
        self._drain_timeout = drain_timeout
        self._block_ms = block_ms
        self._tasks: set[asyncio.Task] = set()
        self._stopping = asyncio.Event()

    async def consume(self, stream: str, handler: MessageHandler) -> None:
        await self._ensure_group(stream)
        await self._replay_pending(stream, handler)
        while not self._stopping.is_set():
            await self._slots.acquire()
            if self._stopping.is_set():
                self._slots.release()
                break
            try:
                response = await self._redis.xreadgroup(
                    GROUP, self._consumer, {stream: ">"}, count=1, block=self._block_ms
                )
            except BaseException:
                self._slots.release()
                raise
            messages = response[0][1] if response else []
            if not messages or self._stopping.is_set():
                # A message read while stopping stays pending and is replayed on restart.
                self._slots.release()
                continue
            msg_id, fields = messages[0]
            self._spawn(stream, msg_id, fields, handler)

    async def stop(self) -> None:
        self._stopping.set()
        if not self._tasks:
            return
        _, pending = await asyncio.wait(self._tasks, timeout=self._drain_timeout)
        for task in pending:
            # Not acked, so the job is redelivered when the worker comes back.
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

    async def _ensure_group(self, stream: str) -> None:
        try:
            await self._redis.xgroup_create(stream, GROUP, id="0", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def _replay_pending(self, stream: str, handler: MessageHandler) -> None:
        """Re-run messages this consumer read but never acked (the worker died mid-job)."""
        last_id = "0"
        while not self._stopping.is_set():
            response = await self._redis.xreadgroup(
                GROUP, self._consumer, {stream: last_id}, count=100
            )
            messages = response[0][1] if response else []
            if not messages:
                return
            for msg_id, fields in messages:
                await self._slots.acquire()
                self._spawn(stream, msg_id, fields, handler)
                last_id = msg_id

    def _spawn(
        self, stream: str, msg_id: str, fields: dict[str, str] | None, handler: MessageHandler
    ) -> None:
        task = asyncio.create_task(self._handle(stream, msg_id, fields, handler))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _handle(
        self, stream: str, msg_id: str, fields: dict[str, str] | None, handler: MessageHandler
    ) -> None:
        try:
            # Fields are empty when the entry was trimmed from the stream while pending.
            if fields:
                await handler(fields)
            await self._redis.xack(stream, GROUP, msg_id)
        except Exception:
            logger.exception("Handler failed for %s %s; leaving it pending", stream, msg_id)
        finally:
            self._slots.release()
