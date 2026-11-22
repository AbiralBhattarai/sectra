from pathlib import Path

from src.application.services.background_library_service import CATEGORY, parse_ref
from src.application.services.job_scheduler import JobScheduler
from src.domain.enums.job_type_enum import JobType
from src.domain.enums.video_kind_enum import VideoKind
from src.domain.exceptions import AppValidationException, NotFoundException
from src.domain.models.character import MOUTH_SHAPES
from src.domain.models.job import Job
from src.domain.models.story import CHARACTERS, VOICES, StorySpec
from src.domain.models.video import Video
from src.domain.services.story_text import clean_for_speech, default_title
from src.ports.output.file_storage_port import FileStoragePort
from src.ports.output.video_repository import VideoRepository

#: Layers a character may have; anything else is refused by ``character_layer``.
_LAYERS = (
    {f"base/{e}.svg" for e in ("neutral", "happy", "sad", "angry", "shocked", "smug")}
    | {f"mouth/{m}.svg" for m in MOUTH_SHAPES}
    | {"blink.svg", "preview.svg"}
)


class StoryService:
    """Narrator: creates stories (a ``Video`` of kind ``story``) and queues NARRATE;
    everything after that is the worker's pipeline."""

    def __init__(
        self, videos: VideoRepository, storage: FileStoragePort, scheduler: JobScheduler
    ) -> None:
        self._videos = videos
        self._storage = storage
        self._scheduler = scheduler

    async def create(self, spec: StorySpec) -> Video:
        _validate(spec)
        if spec.background:
            category, file = parse_ref(spec.background)
            if not self._storage.background_path(category, file).is_file():
                raise AppValidationException(f"Background {spec.background} is not in the library")
        if not clean_for_speech(spec.text):
            raise AppValidationException("The story has no words to narrate")
        title = spec.title.strip() or default_title(clean_for_speech(spec.text))
        video = Video(title=title, kind=VideoKind.STORY, story=spec)
        await self._videos.add(video)
        await self._scheduler.submit(Job(type=JobType.NARRATE, video_id=video.id))
        return video

    def options(self) -> dict:
        return {
            "voices": [{"id": v, "label": label} for v, label in VOICES.items()],
            "characters": [
                {"id": c, "label": label, "voice": voice}
                for c, (label, voice) in CHARACTERS.items()
            ],
        }

    async def character_layer(self, name: str, layer: str) -> Path:
        if name not in CHARACTERS or layer not in _LAYERS:
            raise NotFoundException(f"Character layer {name}/{layer} not found")
        path = self._storage.character_path(name, layer)
        if not path.is_file():
            raise NotFoundException(f"Character layer {name}/{layer} not found")
        return path


def _validate(spec: StorySpec) -> None:
    if spec.voice not in VOICES:
        raise AppValidationException(f"Unknown voice {spec.voice!r}")
    if spec.character is not None and spec.character not in CHARACTERS:
        raise AppValidationException(f"Unknown character {spec.character!r}")
    if spec.category is not None and not CATEGORY.match(spec.category):
        raise AppValidationException(f"Unknown background category {spec.category!r}")
    if spec.background_mode == "black" and (spec.background or spec.category):
        raise AppValidationException("A black-screen story takes no gameplay background")
