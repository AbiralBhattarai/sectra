"""Input port: render clips and fetch the results."""

from pathlib import Path
from typing import Any, Literal, Protocol
from uuid import UUID

from src.domain.models.job import Job

ExportFile = Literal["video", "subtitles"]


class ClipExportPort(Protocol):
    async def request_export(self, clip_id: UUID, outbox_rank: int | None = None) -> Job:
        """Queue a render of the clip's current edit (snapshotted into the job). With
        ``outbox_rank`` the finished video is also copied to the outbox, named after
        the rank and the clip's caption."""
        ...

    async def request_post(self, clip_id: UUID, post_caption: str | None = None) -> Job:
        """Render the clip's current edit into the outbox marked for posting now, to every
        configured platform (the host poster does the posting). The description is the
        title followed by the clip's ``post_caption``; a given ``post_caption`` is saved
        on the clip first (None keeps the saved one)."""
        ...

    async def post_status(self, clip_id: UUID) -> tuple[Job, dict[str, Any] | None] | None:
        """The latest Post of the clip: its render job and the outbox sidecar (holding
        what the poster has recorded per platform), or None if it was never posted."""
        ...

    async def list_exports(self, clip_id: UUID) -> list[Job]:
        """The clip's export jobs, newest first."""
        ...

    async def export_file(self, export_id: UUID, file: ExportFile) -> tuple[Path, str]:
        """Path and download name of a finished export's file; raises
        ``NotFoundException`` if the export doesn't exist or hasn't finished."""
        ...
