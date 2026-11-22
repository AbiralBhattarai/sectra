from typing import Any

from pydantic import BaseModel

from src.application.dto.job import JobDTO
from src.domain.enums.job_status_enum import JobStatus
from src.domain.models.job import Job


class ExportDTO(JobDTO):
    #: Download links, present once the render succeeded.
    video_url: str | None
    subtitles_url: str | None

    @classmethod
    def from_job(cls, job: Job) -> "ExportDTO":
        done = job.status is JobStatus.SUCCEEDED
        base = f"/api/exports/{job.id}"
        return cls(
            **JobDTO.from_domain(job).model_dump(),
            video_url=f"{base}/video" if done else None,
            subtitles_url=f"{base}/subtitles" if done else None,
        )


class PostStatusDTO(BaseModel):
    """The latest Post of a clip: its render, then what the host poster recorded per
    platform (``posted``: at/url; ``failures``: count/error/gave_up; ``blocked``: reason)."""

    export: ExportDTO
    platforms: list[str]
    #: The render reached the outbox (so `poster serve` can pick it up).
    in_outbox: bool
    posted: dict[str, dict[str, Any]]
    failures: dict[str, dict[str, Any]]
    blocked: dict[str, dict[str, Any]]

    @classmethod
    def from_post(cls, job: Job, sidecar: dict[str, Any] | None) -> "PostStatusDTO":
        sidecar = sidecar or {}
        return cls(
            export=ExportDTO.from_job(job),
            platforms=list(job.payload.get("platforms", [])),
            in_outbox=bool(sidecar),
            posted=sidecar.get("posted", {}),
            failures=sidecar.get("failures", {}),
            blocked=sidecar.get("blocked", {}),
        )
