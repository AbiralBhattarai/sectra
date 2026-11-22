import asyncio

from src.adapters.input.worker.redis_stream_consumer import GROUP, RedisStreamConsumer
from tests.unit.helpers import wait_until

STREAM = "jobs:test"


def consumer(redis, concurrency=2, drain_timeout=5.0):
    return RedisStreamConsumer(
        redis, "w1", concurrency=concurrency, drain_timeout=drain_timeout, block_ms=50
    )


async def pending_count(redis) -> int:
    return (await redis.xpending(STREAM, GROUP))["pending"]


async def test_handles_and_acks_messages(redis):
    seen = []

    async def handler(fields):
        seen.append(fields["job_id"])

    c = consumer(redis)
    task = asyncio.create_task(c.consume(STREAM, handler))
    await redis.xadd(STREAM, {"job_id": "a"})
    await redis.xadd(STREAM, {"job_id": "b"})
    await wait_until(lambda: len(seen) == 2)
    await c.stop()
    await task

    assert sorted(seen) == ["a", "b"]
    assert await pending_count(redis) == 0


async def test_failed_handler_leaves_message_pending(redis):
    called = asyncio.Event()

    async def handler(fields):
        called.set()
        raise RuntimeError("db down")

    c = consumer(redis)
    task = asyncio.create_task(c.consume(STREAM, handler))
    await redis.xadd(STREAM, {"job_id": "a"})
    await asyncio.wait_for(called.wait(), 5)
    await c.stop()  # drains the in-flight handler
    await task

    assert await pending_count(redis) == 1


async def test_unfinished_message_is_replayed_by_restarted_consumer(redis):
    started = asyncio.Event()

    async def hangs(fields):
        started.set()
        await asyncio.Event().wait()

    first = consumer(redis, drain_timeout=0.1)
    task = asyncio.create_task(first.consume(STREAM, hangs))
    await redis.xadd(STREAM, {"job_id": "a"})
    await asyncio.wait_for(started.wait(), 5)
    await first.stop()  # times out draining and cancels the handler
    await task
    assert await pending_count(redis) == 1

    replayed = []

    async def handler(fields):
        replayed.append(fields["job_id"])

    second = consumer(redis)
    task = asyncio.create_task(second.consume(STREAM, handler))
    await wait_until(lambda: replayed == ["a"])
    await second.stop()
    await task
    assert await pending_count(redis) == 0


async def test_runs_at_most_concurrency_handlers_at_once(redis):
    in_flight = 0
    peak = 0
    done = []

    async def handler(fields):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.05)
        in_flight -= 1
        done.append(fields["job_id"])

    for i in range(6):
        await redis.xadd(STREAM, {"job_id": str(i)})
    c = consumer(redis, concurrency=2)
    task = asyncio.create_task(c.consume(STREAM, handler))
    await wait_until(lambda: len(done) == 6)
    await c.stop()
    await task

    assert peak == 2


async def test_survives_a_read_timeout(redis, monkeypatch):
    """A timed-out XREADGROUP (Redis blip, busy loop) is retried, not fatal."""
    from redis.exceptions import TimeoutError as RedisTimeoutError

    from src.adapters.input.worker import redis_stream_consumer

    monkeypatch.setattr(redis_stream_consumer, "_BACKOFF_START", 0.01)
    real = redis.xreadgroup
    failures = 0

    async def flaky(*args, **kwargs):
        nonlocal failures
        if ">" in args[2].values() and failures < 2:
            failures += 1
            raise RedisTimeoutError("Timeout reading from redis")
        return await real(*args, **kwargs)

    monkeypatch.setattr(redis, "xreadgroup", flaky)
    seen = []

    async def handler(fields):
        seen.append(fields["job_id"])

    c = consumer(redis)
    task = asyncio.create_task(c.consume(STREAM, handler))
    await redis.xadd(STREAM, {"job_id": "a"})
    await wait_until(lambda: seen == ["a"])
    await c.stop()
    await task

    assert failures == 2
