from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from src.adapters.input.rest.dependencies import get_job_service
from src.application.dto.job import JobDTO, PingRequest
from src.ports.input.job_management_port import JobManagementPort

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

JobService = Annotated[JobManagementPort, Depends(get_job_service)]


@router.post("/ping", status_code=status.HTTP_202_ACCEPTED)
async def submit_ping(body: PingRequest, jobs: JobService) -> JobDTO:
    return JobDTO.from_domain(await jobs.submit_ping(body.steps))


@router.get("/{job_id}")
async def get_job(job_id: UUID, jobs: JobService) -> JobDTO:
    return JobDTO.from_domain(await jobs.get(job_id))


@router.post("/{job_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_job(job_id: UUID, jobs: JobService) -> JobDTO:
    return JobDTO.from_domain(await jobs.retry(job_id))
