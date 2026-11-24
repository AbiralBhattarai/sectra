import asyncio
import logging

from pydantic import ValidationError

from src.application.prompts.story_prompt import (
    MOODS_SCHEMA,
    MOODS_SYSTEM,
    LineMood,
    MoodsResponse,
    moods_prompt,
)
from src.application.services.pipeline_dispatcher import ProgressCallback
from src.domain.enums.emotion_enum import Emotion
from src.domain.enums.overlay_style_enum import OverlayStyle
from src.domain.enums.video_file_enum import VideoFile
from src.domain.exceptions import LLMException, NotFoundException
from src.domain.models.character import CharacterTrack, Mood
from src.domain.models.clip import Clip
from src.domain.models.edl import Crop, Edl, Overlay
from src.domain.models.job import Job
from src.domain.models.speech import TimeSpan
from src.domain.models.story import StorySpec
from src.domain.models.transcript import Segment, Transcript, Word
from src.domain.models.video import Video
from src.domain.services.character_timeline import merge_moods
from src.domain.services.story_parts import split_parts
from src.domain.services.story_text import default_caption
from src.ports.input.clip_export_port import ClipExportPort
from src.ports.output.clip_repository import ClipRepository
from src.ports.output.file_storage_port import FileStoragePort
from src.ports.output.llm_port import LLMPort
from src.ports.output.video_repository import VideoRepository

logger = logging.getLogger(__name__)

#: The title (or "Part N") overlay at the start of each part.
TITLE_SECONDS = 3.0
#: Gap between the top of the character and the bottom of the captions (frame height).
CAPTION_GAP = 0.03
#: Lines of narration per mood request (keeps the prompt small for a 7B model).
_MOOD_BATCH = 60


class StoryClipService:
    """ANALYZE for stories: no clip finding — the whole narration is the clip, split into
    parts that fit the platforms' limit. Each part gets the talking character (with
    LLM-picked expressions), captions just above its head and a title card, then goes
    to the outbox like an automatically found clip when automatic export is on."""

    def __init__(
        self,
        videos: VideoRepository,
        storage: FileStoragePort,
        clips: ClipRepository,
        llm: LLMPort,
        part_max_seconds: float,
        exports: ClipExportPort | None = None,
    ) -> None:
        self._videos = videos
        self._storage = storage
        self._clips = clips
        self._llm = llm
        self._part_max_seconds = part_max_seconds
        self._exports = exports

    async def __call__(self, job: Job, report: ProgressCallback) -> None:
        video = await self._videos.get(job.video_id) if job.video_id else None
        if video is None or video.story is None or video.duration is None:
            raise NotFoundException(f"Story {job.video_id} not found")
        transcript = Transcript.model_validate_json(
            await self._storage.read_text(video.id, VideoFile.TRANSCRIPT)
        )
        segments = transcript.segments
        moods = await self._moods(segments) if video.story.character else []
        await report(0.8)

        parts = split_parts(segments, video.duration, self._part_max_seconds)
        words = [w for s in segments for w in s.words]
        clips = [
            self._clip(video, video.story, part, index, len(parts), words, moods)
            for index, part in enumerate(parts, start=1)
        ]
        await self._clips.replace_for_video(video.id, clips)
        if self._exports is not None:
            for rank, clip in enumerate(clips, start=1):
                await self._exports.request_export(clip.id, outbox_rank=rank)

    def _clip(
        self,
        video: Video,
        story: StorySpec,
        span: TimeSpan,
        number: int,
        count: int,
        words: list[Word],
        moods: list[Mood],
    ) -> Clip:
        title = video.title if count == 1 else f"{video.title} · Part {number}"
        caption = story.caption or default_caption(video.title)
        if count > 1:
            caption = f"Part {number}/{count} — {caption}"
        edl = Edl.for_span(span, words)
        edl.overlays = [
            Overlay(
                text=(video.title if number == 1 else f"Part {number}")[:200],
                start=0.0,
                end=min(TITLE_SECONDS, span.duration),
                y=0.12,
                style=OverlayStyle.TITLE,
            )
        ]
        if story.character:
            track = CharacterTrack(
                name=story.character,
                moods=[m for m in moods if m.end > span.start and m.start < span.end],
            )
            edl.character = track
            edl.captions.y = round(track.y - track.scale / 2 - CAPTION_GAP, 3)
        if story.background_mode == "black":
            edl.crop = Crop()  # the frame is already 9:16
        return Clip(
            video_id=video.id,
            title=title,
            hook=story.narration[:200] if number == 1 else f"Part {number} of {count}",
            score=100,
            reason="Narrated story",
            caption=caption,
            start=span.start,
            end=span.end,
            edl=edl,
        )

    async def _moods(self, segments: list[Segment]) -> list[Mood]:
        """Expressions per stretch of narration; neutral throughout if the LLM fails."""
        batches = [segments[i : i + _MOOD_BATCH] for i in range(0, len(segments), _MOOD_BATCH)]
        by_id = {s.id: s for s in segments}
        answers = await asyncio.gather(*(self._ask_moods(batch) for batch in batches))
        spans: list[tuple[float, float, Emotion]] = []
        for answer in answers:
            for item in answer:
                segment = by_id.get(item.line)
                if segment is not None:
                    spans.append((segment.start, segment.end, item.emotion))
        return merge_moods(spans)

    async def _ask_moods(self, batch: list[Segment]) -> list[LineMood]:
        for attempt in (1, 2):
            try:
                answer = await self._llm.complete_json(
                    MOODS_SYSTEM, moods_prompt(batch), MOODS_SCHEMA
                )
                return MoodsResponse.model_validate(answer).moods
            except (LLMException, ValidationError) as exc:
                logger.warning("Mood request failed (attempt %d): %s", attempt, exc)
        return []


class AnalysisRouter:
    """The ANALYZE handler: clip finding for source videos, part splitting for stories."""

    def __init__(self, videos: VideoRepository, clipping, stories: StoryClipService) -> None:
        self._videos = videos
        self._clipping = clipping
        self._stories = stories

    async def __call__(self, job: Job, report: ProgressCallback) -> None:
        video = await self._videos.get(job.video_id) if job.video_id else None
        if video is not None and video.story is not None:
            await self._stories(job, report)
        else:
            await self._clipping(job, report)
