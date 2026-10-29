from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from redis.asyncio import Redis

from src.adapters.output.events.redis_pubsub_progress_adapter import RedisPubSubProgressAdapter
from src.adapters.output.persistence.db import create_engine, create_sessionmaker
from src.adapters.output.persistence.postgres_clip_repository import PostgresClipRepository
from src.adapters.output.persistence.postgres_job_repository import PostgresJobRepository
from src.adapters.output.persistence.postgres_video_repository import PostgresVideoRepository
from src.adapters.output.queue.redis_stream_queue_adapter import RedisStreamQueueAdapter
from src.adapters.output.storage.local_fs_storage_adapter import LocalFsStorageAdapter
from src.adapters.output.storage.music_manifest import load_default_tracks
from src.application.services.clip_editing_service import ClipEditingService
from src.application.services.clip_export_service import ClipExportService
from src.application.services.job_scheduler import JobScheduler
from src.application.services.job_service import JobService
from src.application.services.music_library_service import MusicLibraryService
from src.application.services.video_library_service import VideoLibraryService
from src.config.settings import Settings


@dataclass(frozen=True)
class Container:
    """Object graph shared by the API and the worker."""

    settings: Settings
    redis: Redis
    executor: ThreadPoolExecutor
    jobs: PostgresJobRepository
    videos: PostgresVideoRepository
    clips: PostgresClipRepository
    storage: LocalFsStorageAdapter
    progress: RedisPubSubProgressAdapter
    scheduler: JobScheduler
    job_service: JobService
    video_library: VideoLibraryService
    clip_editing: ClipEditingService
    music_library: MusicLibraryService
    clip_export: ClipExportService
    #: Drains driven adapters on shutdown — closes Redis, the Postgres pool and the threads.
    aclose: Callable[[], Awaitable[None]]


def build_container(settings: Settings) -> Container:
    engine = create_engine(settings.database_url)
    sessionmaker = create_sessionmaker(engine)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    executor = ThreadPoolExecutor(settings.blocking_threads, thread_name_prefix="blocking")

    jobs = PostgresJobRepository(sessionmaker)
    videos = PostgresVideoRepository(sessionmaker)
    clips = PostgresClipRepository(sessionmaker)
    storage = LocalFsStorageAdapter(settings.data_dir, executor, settings.default_music_dir)
    progress = RedisPubSubProgressAdapter(redis)
    scheduler = JobScheduler(jobs=jobs, queue=RedisStreamQueueAdapter(redis), progress=progress)

    async def aclose() -> None:
        await redis.aclose()
        await engine.dispose()
        executor.shutdown(wait=False, cancel_futures=True)

    return Container(
        settings=settings,
        redis=redis,
        executor=executor,
        jobs=jobs,
        videos=videos,
        clips=clips,
        storage=storage,
        progress=progress,
        scheduler=scheduler,
        job_service=JobService(jobs=jobs, videos=videos, scheduler=scheduler, progress=progress),
        video_library=VideoLibraryService(
            videos=videos, jobs=jobs, storage=storage, scheduler=scheduler
        ),
        clip_editing=ClipEditingService(clips=clips, videos=videos, storage=storage),
        music_library=MusicLibraryService(
            storage=storage, defaults=load_default_tracks(settings.default_music_dir)
        ),
        clip_export=ClipExportService(
            clips=clips, videos=videos, jobs=jobs, storage=storage, scheduler=scheduler
        ),
        aclose=aclose,
    )
