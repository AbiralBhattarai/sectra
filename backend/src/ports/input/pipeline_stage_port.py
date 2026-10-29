"""Input port: execute one queued job."""

from typing import Protocol
from uuid import UUID


class PipelineStagePort(Protocol):
    async def run_job(self, job_id: UUID) -> None:
        """Run the job to a terminal status. Never raises for a failure inside the job:
        the failure is recorded on the job instead, so the caller can always ack."""
        ...
