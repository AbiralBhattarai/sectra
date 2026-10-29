from redis.asyncio import Redis

from src.domain.models.job import Job

#: Acked entries are never read again; cap the stream so it doesn't grow forever.
_STREAM_MAXLEN = 10_000


class RedisStreamQueueAdapter:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def enqueue(self, job: Job) -> None:
        await self._redis.xadd(
            job.type.stream, {"job_id": str(job.id)}, maxlen=_STREAM_MAXLEN, approximate=True
        )
