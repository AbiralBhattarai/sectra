from collections.abc import AsyncIterator

from redis.asyncio import Redis

from src.domain.models.app_event import AppEvent, parse_event

CHANNEL = "job-events"


class RedisPubSubProgressAdapter:
    def __init__(self, redis: Redis, channel: str = CHANNEL) -> None:
        self._redis = redis
        # Pub/sub channels are global to the server (not per database).
        self._channel = channel

    async def publish(self, event: AppEvent) -> None:
        await self._redis.publish(self._channel, event.model_dump_json())

    async def subscribe(self) -> AsyncIterator[AppEvent]:
        pubsub = self._redis.pubsub(ignore_subscribe_messages=True)
        await pubsub.subscribe(self._channel)
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    yield parse_event(message["data"])
        finally:
            await pubsub.unsubscribe(self._channel)
            await pubsub.aclose()
