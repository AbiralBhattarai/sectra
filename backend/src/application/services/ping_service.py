import asyncio

from src.application.services.pipeline_dispatcher import ProgressCallback
from src.domain.models.job import Job


class PingService:
    """No-op stage that only reports progress; proves the queue → worker → SSE path."""

    def __init__(self, step_delay: float = 1.0) -> None:
        self._step_delay = step_delay

    async def __call__(self, job: Job, report: ProgressCallback) -> None:
        steps = int(job.payload.get("steps", 5))
        for step in range(1, steps + 1):
            await asyncio.sleep(self._step_delay)
            await report(step / steps)
