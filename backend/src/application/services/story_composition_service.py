import random
from pathlib import Path

from src.application.services.pipeline_dispatcher import ProgressCallback
from src.domain.enums.video_file_enum import VideoFile
from src.domain.exceptions import AppValidationException, NotFoundException
from src.domain.models.job import Job
from src.domain.models.story import StorySpec
from src.ports.output.file_storage_port import FileStoragePort
from src.ports.output.media_port import MediaPort
from src.ports.output.video_repository import VideoRepository


class StoryCompositionService:
    """COMPOSE stage: the narration over a black frame or a stretch of gameplay from the
    background library becomes the story's ``source.mp4``. From here on the story goes
    through the clipping pipeline (PREPARE → VAD → TRANSCRIBE) for timed captions."""

    def __init__(
        self,
        videos: VideoRepository,
        storage: FileStoragePort,
        media: MediaPort,
        rng: random.Random | None = None,
    ) -> None:
        self._videos = videos
        self._storage = storage
        self._media = media
        self._rng = rng or random.Random()

    async def __call__(self, job: Job, report: ProgressCallback) -> None:
        video = await self._videos.get(job.video_id) if job.video_id else None
        if video is None or video.story is None:
            raise NotFoundException(f"Story {job.video_id} not found")
        narration = self._storage.path(video.id, VideoFile.NARRATION)
        if not narration.is_file():
            raise AppValidationException("The story has not been narrated yet")
        # NARRATE stores the narration's length; source.mp4 is cut to exactly that.
        duration = video.duration
        if not duration:
            raise AppValidationException("The narration's length is unknown; narrate again")

        background, offset = None, 0.0
        if video.story.background_mode == "gameplay":
            background = self._pick(video.story)
            length = (await self._media.probe(background)).duration
            if length > duration + 1:
                offset = round(self._rng.uniform(0, length - duration), 3)

        source = self._storage.path(video.id, VideoFile.SOURCE)
        partial = source.with_name(f"{source.stem}.partial{source.suffix}")
        await self._media.compose_story(narration, partial, duration, background, offset, report)
        partial.replace(source)

        stored = await self._media.probe(source)
        video = await self._videos.get(video.id) or video
        video.duration, video.width, video.height = stored.duration, stored.width, stored.height
        await self._videos.save(video)

    def _pick(self, story: StorySpec) -> Path:
        """The chosen clip, else a random one from the category, else from the library."""
        if story.background:
            category, _, file = story.background.partition("/")
            path = self._storage.background_path(category, file)
            if path.is_file():
                return path
            raise AppValidationException(f"Background {story.background} is no longer there")
        clips = self._storage.list_backgrounds()
        if story.category:
            clips = [c for c in clips if c[0] == story.category]
        if not clips:
            where = f"the '{story.category}' category" if story.category else "the library"
            raise AppValidationException(
                f"No gameplay clips in {where}; add some under Backgrounds or pick Black screen"
            )
        category, file = self._rng.choice(clips)
        return self._storage.background_path(category, file)
