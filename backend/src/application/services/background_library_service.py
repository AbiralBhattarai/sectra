import re
import uuid
from collections.abc import AsyncIterator
from pathlib import Path, PurePath

from src.application.services.job_scheduler import JobScheduler
from src.application.services.pipeline_dispatcher import ProgressCallback
from src.domain.enums.job_status_enum import JobStatus
from src.domain.enums.job_type_enum import JobType
from src.domain.exceptions import (
    AppValidationException,
    MediaProcessingException,
    NotFoundException,
)
from src.domain.models.background import Background, PendingBackground
from src.domain.models.job import Job
from src.ports.output.downloader_port import DownloaderPort
from src.ports.output.file_storage_port import FileStoragePort
from src.ports.output.job_repository import JobRepository
from src.ports.output.media_port import MediaPort

CATEGORY = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
#: Stored as "<8 hex>-<slug>.mp4" so names are unique and safe in paths.
_STORED = re.compile(r"^[0-9a-f]{8}-(?P<slug>[A-Za-z0-9._-]*)\.mp4$")
UPLOAD_EXTENSIONS = {"mp4", "mov", "mkv", "webm", "m4v", "avi"}
#: Shown in the library until it's dismissed by a newer state or re-added.
_PENDING_LIMIT = 50


class BackgroundLibraryService:
    """Gameplay clips for story backgrounds (API side), and the BACKGROUND stage that
    downloads/re-encodes them (worker side). A clip only appears in the library once it
    is fully written, so a story never picks a half-encoded file."""

    def __init__(
        self,
        storage: FileStoragePort,
        jobs: JobRepository,
        scheduler: JobScheduler,
        downloader: DownloaderPort | None = None,
        media: MediaPort | None = None,
    ) -> None:
        self._storage = storage
        self._jobs = jobs
        self._scheduler = scheduler
        self._downloader = downloader
        self._media = media

    async def add_from_url(self, url: str, category: str) -> Job:
        job = Job(
            type=JobType.BACKGROUND,
            payload={"category": _category(category), "url": url, "source": url},
        )
        await self._scheduler.submit(job)
        return job

    async def add_upload(self, filename: str, category: str, chunks: AsyncIterator[bytes]) -> Job:
        name = PurePath(filename)
        extension = name.suffix.lower().lstrip(".")
        if extension not in UPLOAD_EXTENSIONS:
            raise AppValidationException(
                f"Unsupported file type '.{extension}'; expected one of "
                + ", ".join(sorted(UPLOAD_EXTENSIONS))
            )
        job = Job(
            type=JobType.BACKGROUND,
            payload={"category": _category(category), "source": name.name, "name": name.stem},
        )
        try:
            await self._storage.save_background_upload(job.id, extension, chunks)
        except BaseException:
            await self._storage.remove_background_incoming(job.id)
            raise
        await self._scheduler.submit(job)
        return job

    async def list(self) -> tuple[list[Background], list[PendingBackground]]:
        ready = [
            Background(category=category, file=file, name=_name(file))
            for category, file in self._storage.list_backgrounds()
        ]
        pending = [
            PendingBackground(
                job_id=job.id,
                category=job.payload.get("category", ""),
                source=job.payload.get("source", ""),
                status=job.status,
                progress=job.progress,
                error=job.error,
            )
            for job in await self._jobs.list_by_type(JobType.BACKGROUND, _PENDING_LIMIT)
            if job.status is not JobStatus.SUCCEEDED
        ]
        return ready, pending

    async def path(self, category: str, file: str) -> Path:
        _check(category, file)
        path = self._storage.background_path(category, file)
        if not path.is_file():
            raise NotFoundException(f"Background {category}/{file} not found")
        return path

    async def delete(self, category: str, file: str) -> None:
        await self.path(category, file)
        await self._storage.delete_background(category, file)

    async def __call__(self, job: Job, report: ProgressCallback) -> None:
        """BACKGROUND stage."""
        if self._media is None or self._downloader is None:
            raise RuntimeError("BackgroundLibraryService was built without media tools")
        category = _category(job.payload["category"])
        incoming = self._storage.background_incoming_dir(job.id)
        url = job.payload.get("url")
        try:
            raw = next(incoming.glob("raw.*"), None)
            name = job.payload.get("name", "")
            if url:
                if raw is not None:
                    raw.unlink()  # a retried download starts clean

                async def download_progress(fraction: float) -> None:
                    await report(0.5 * fraction)

                result = await self._downloader.download(url, incoming, download_progress)
                raw, name = result.path, result.title or url
            if raw is None or not raw.is_file():
                raise MediaProcessingException("The uploaded clip is gone; add it again")

            info = await self._media.probe(raw)
            file = f"{uuid.uuid4().hex[:8]}-{_slug(name)}.mp4"
            target = self._storage.background_path(category, file)
            partial = target.with_name(f"{target.stem}.partial.mp4")
            done = 0.5 if url else 0.0

            async def encode_progress(fraction: float) -> None:
                await report(done + (1 - done) * fraction)

            try:
                await self._media.make_background(raw, partial, info.duration, encode_progress)
                partial.replace(target)
            finally:
                partial.unlink(missing_ok=True)
        except BaseException:
            # A download is fetched again on retry; an upload is kept so Retry can work.
            if url:
                await self._storage.remove_background_incoming(job.id)
            raise
        await self._storage.remove_background_incoming(job.id)


def _category(value: str) -> str:
    category = value.strip().lower().replace(" ", "-")
    if not CATEGORY.match(category):
        raise AppValidationException(
            "Category must be 1-40 lowercase letters, digits or dashes (e.g. minecraft)"
        )
    return category


def _check(category: str, file: str) -> None:
    if not CATEGORY.match(category) or not _STORED.match(file):
        raise NotFoundException(f"Background {category}/{file} not found")


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-.")[:60] or "clip"


def _name(file: str) -> str:
    match = _STORED.match(file)
    slug = match.group("slug") if match else file
    return slug.replace("-", " ").replace("_", " ")


def parse_ref(ref: str) -> tuple[str, str]:
    """ "<category>/<file>" → (category, file); raises ``AppValidationException``."""
    category, _, file = ref.partition("/")
    if not CATEGORY.match(category) or not _STORED.match(file):
        raise AppValidationException(f"Unknown background {ref!r}")
    return category, file
