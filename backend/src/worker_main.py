import asyncio
import logging
import signal
from uuid import UUID

from src.config.logging_config import configure_logging
from src.config.settings import get_settings
from src.config.worker_container import build_worker_container

logger = logging.getLogger(__name__)


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    container = build_worker_container(settings)

    async def handle(fields: dict[str, str]) -> None:
        await container.dispatcher.run_job(UUID(fields["job_id"]))

    stop_requested = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_requested.set)

    consumers = [
        asyncio.create_task(consumer.consume(stream, handle), name=f"consume:{stream}")
        for stream, consumer in container.consumers.items()
    ]
    stopper = asyncio.create_task(stop_requested.wait())
    logger.info("Worker %s consuming %s", settings.worker_name, sorted(container.consumers))
    try:
        # Returns on a shutdown signal, or when a consumer dies (e.g. Redis went away).
        await asyncio.wait([*consumers, stopper], return_when=asyncio.FIRST_COMPLETED)
    finally:
        await asyncio.gather(*(c.stop() for c in container.consumers.values()))
        stopper.cancel()
        results = await asyncio.gather(*consumers, return_exceptions=True)
        await container.aclose()
    for result in results:
        if isinstance(result, BaseException) and not isinstance(result, asyncio.CancelledError):
            raise result


if __name__ == "__main__":
    asyncio.run(main())
