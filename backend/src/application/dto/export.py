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
