import asyncio
import contextlib
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from src.adapters.input.rest.dependencies import get_job_service
from src.domain.models.app_event import AppEvent
from src.ports.input.job_management_port import JobManagementPort

router = APIRouter(prefix="/api", tags=["events"])

#: Comment line sent when idle so proxies don't close the connection.
_HEARTBEAT_SECONDS = 15.0


@router.get("/events")
async def events(
    jobs: Annotated[JobManagementPort, Depends(get_job_service)],
) -> StreamingResponse:
    return StreamingResponse(
        _sse(jobs.events()),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _sse(source: AsyncIterator[AppEvent]) -> AsyncIterator[str]:
    # Pump through a queue: timing out on queue.get() is safe, while cancelling the
    # subscription's __anext__ would close the subscription.
    queue: asyncio.Queue[AppEvent] = asyncio.Queue()

    async def pump() -> None:
        async for event in source:
            await queue.put(event)

    pump_task = asyncio.create_task(pump())
    try:
        yield ": connected\n\n"
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), _HEARTBEAT_SECONDS)
            except TimeoutError:
                if pump_task.done():
                    pump_task.result()  # surface a dead subscription instead of idling forever
                yield ": heartbeat\n\n"
                continue
            yield f"event: {event.kind}\ndata: {event.model_dump_json()}\n\n"
    finally:
        pump_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await pump_task
