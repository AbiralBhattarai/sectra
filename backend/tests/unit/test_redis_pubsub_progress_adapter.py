import asyncio
from uuid import uuid4

from src.adapters.output.events.redis_pubsub_progress_adapter import RedisPubSubProgressAdapter
from src.domain.enums.job_status_enum import JobStatus
from src.domain.enums.job_type_enum import JobType
from src.domain.models.job import JobEvent


async def test_subscriber_receives_published_events(redis):
    # Pub/sub ignores the db number, so use a channel the running app doesn't share.
    channel = f"test-job-events-{uuid4()}"
    adapter = RedisPubSubProgressAdapter(redis, channel)
    events = adapter.subscribe()
    first = asyncio.create_task(anext(events))

    subscribers = 0

    async def poll():
        nonlocal subscribers
        subscribers = dict(await redis.pubsub_numsub(channel))[channel]

    async with asyncio.timeout(5):
        while subscribers == 0:
            await poll()

    sent = JobEvent(job_id=uuid4(), type=JobType.PING, status=JobStatus.RUNNING, progress=0.5)
    await adapter.publish(sent)

    assert await asyncio.wait_for(first, 5) == sent
    await events.aclose()
