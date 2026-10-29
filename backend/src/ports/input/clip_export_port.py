"""Input port: render clips and fetch the results."""

from pathlib import Path
from typing import Literal, Protocol
from uuid import UUID

from src.domain.models.job import Job

ExportFile = Literal["video", "subtitles"]


class ClipExportPort(Protocol):
    async def request_export(self, clip_id: UUID) -> Job:
        """Queue a render of the clip's current edit (snapshotted into the job)."""
        ...

    async def list_exports(self, clip_id: UUID) -> list[Job]:
        """The clip's export jobs, newest first."""
        ...

    async def export_file(self, export_id: UUID, file: ExportFile) -> tuple[Path, str]:
        """Path and download name of a finished export's file; raises
        ``NotFoundException`` if the export doesn't exist or hasn't finished."""
        ...
