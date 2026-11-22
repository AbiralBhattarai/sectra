import asyncio
import logging

from pydantic import ValidationError

from src.application.prompts.story_prompt import (
    META_SCHEMA,
    META_SYSTEM,
    POLISH_SYSTEM,
    StoryMeta,
    meta_prompt,
    polish_prompt,
)
from src.application.services.pipeline_dispatcher import ProgressCallback
from src.domain.enums.video_file_enum import VideoFile
from src.domain.exceptions import AppValidationException, LLMException, NotFoundException
from src.domain.models.character import LipSync
from src.domain.models.job import Job
from src.domain.models.video import Video
from src.domain.services.story_text import (
    TITLE_MAX_CHARS,
    chunk_paragraphs,
    clean_for_speech,
    default_caption,
    default_title,
    rewrite_ok,
    split_sentences,
)
from src.ports.output.file_storage_port import FileStoragePort
from src.ports.output.lipsync_port import LipSyncPort
from src.ports.output.llm_port import LLMPort
from src.ports.output.tts_port import TTSPort
from src.ports.output.video_repository import VideoRepository

logger = logging.getLogger(__name__)

#: Share of the stage's progress: rewrite, then speech, then lip sync.
_POLISH_SHARE, _TTS_SHARE = 0.2, 0.7


class StoryNarrationService:
    """NARRATE stage: (optionally) rewrite the story for narration with the LLM, speak it
    with TTS into ``narration.wav``, and work out the narrator's mouth shapes. The LLM is
    best effort: anything unusable falls back to the user's own text."""

    def __init__(
        self,
        videos: VideoRepository,
        storage: FileStoragePort,
        tts: TTSPort,
        lipsync: LipSyncPort,
        llm: LLMPort,
        pause_seconds: float = 0.25,
    ) -> None:
        self._videos = videos
        self._storage = storage
        self._tts = tts
        self._lipsync = lipsync
        self._llm = llm
        self._pause_seconds = pause_seconds

    async def __call__(self, job: Job, report: ProgressCallback) -> None:
        video = await self._videos.get(job.video_id) if job.video_id else None
        if video is None:
            raise NotFoundException(f"Video {job.video_id} not found")
        story = video.story
        if story is None:
            raise AppValidationException("This video is not a story")

        text = clean_for_speech(story.text)
        if not text:
            raise AppValidationException("The story has no words to narrate")
        title, caption = story.title.strip(), ""
        if story.polish:
            text = await self._polish(text)
            title, caption = await self._meta(text, title)
        await report(_POLISH_SHARE)
        title = (title or default_title(text))[: TITLE_MAX_CHARS + 20]
        caption = caption or default_caption(title)

        narration = self._storage.path(video.id, VideoFile.NARRATION)
        self._storage.video_dir(video.id)

        async def tts_progress(fraction: float) -> None:
            await report(_POLISH_SHARE + _TTS_SHARE * fraction)

        seconds = await self._tts.narrate(
            split_sentences(text), story.voice, story.speed, self._pause_seconds,
            narration, tts_progress,
        )  # fmt: skip
        if story.character:
            cues = await self._lipsync.mouth_cues(narration, text)
            await self._storage.write_text(
                video.id, VideoFile.LIPSYNC, LipSync(cues=cues).model_dump_json()
            )
        await self._save(video, text, title, caption, seconds)

    async def _polish(self, text: str) -> str:
        chunks = chunk_paragraphs(text)

        async def rewrite(index: int, chunk: str) -> str:
            try:
                answer = await self._llm.complete_text(
                    POLISH_SYSTEM, polish_prompt(chunk, first=index == 0)
                )
            except LLMException as exc:
                logger.warning("Story rewrite failed for chunk %d: %s", index, exc)
                return chunk
            cleaned = clean_for_speech(answer)
            if rewrite_ok(chunk, cleaned):
                return cleaned
            logger.warning("Rewrite of chunk %d changed its length too much; kept original", index)
            return chunk

        return "\n\n".join(
            await asyncio.gather(*(rewrite(i, chunk) for i, chunk in enumerate(chunks)))
        )

    async def _meta(self, text: str, title: str) -> tuple[str, str]:
        """(title, caption) from the LLM; the user's title, if any, wins."""
        for attempt in (1, 2):
            try:
                answer = await self._llm.complete_json(META_SYSTEM, meta_prompt(text), META_SCHEMA)
                meta = StoryMeta.model_validate(answer)
                return title or meta.title.strip().strip('"'), meta.caption.strip()
            except (LLMException, ValidationError) as exc:
                logger.warning("Story title/caption request failed (attempt %d): %s", attempt, exc)
        return title, ""

    async def _save(
        self, video: Video, text: str, title: str, caption: str, seconds: float
    ) -> None:
        # Re-read: the user may have renamed or deleted the video meanwhile.
        current = await self._videos.get(video.id)
        if current is None or current.story is None:
            return
        current.title = title
        current.duration = round(seconds, 3)
        current.story = current.story.model_copy(update={"narration": text, "caption": caption})
        await self._videos.save(current)
