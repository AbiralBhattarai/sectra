from uuid import UUID

from pydantic import BaseModel

from src.domain.enums.job_status_enum import JobStatus


class Background(BaseModel):
    """A gameplay clip in the background library (video only, H.264)."""

    category: str
    #: Stored file name, "<8 hex>-<slug>.mp4".
    file: str
    #: Shown to the user.
    name: str

    @property
    def ref(self) -> str:
        """How a story refers to it: "<category>/<file>"."""
        return f"{self.category}/{self.file}"


class PendingBackground(BaseModel):
    """A BACKGROUND job that hasn't produced its file yet (or failed)."""

    job_id: UUID
    category: str
    #: The URL, or the uploaded file's name.
    source: str
    status: JobStatus
    progress: float
    error: str | None
