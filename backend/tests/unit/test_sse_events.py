import json
from uuid import uuid4

from src.adapters.input.rest.events import _sse
from src.domain.enums.job_status_enum import JobStatus
from src.domain.enums.job_type_enum import JobType
from src.domain.models.job import JobEvent


async def test_sse_frames_each_event():
    event = JobEvent(job_id=uuid4(), type=JobType.PING, status=JobStatus.QUEUED, progress=0)

    async def source():
        yield event

    stream = _sse(source())
    assert await anext(stream) == ": connected\n\n"
    frame = await anext(stream)
    await stream.aclose()

    header, data = frame.strip().split("\n")
    assert header == "event: job"
    assert json.loads(data.removeprefix("data: "))["job_id"] == str(event.job_id)
