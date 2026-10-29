import asyncio
import json
import logging
from uuid import UUID

from pydantic import ValidationError

from src.application.prompts.highlight_prompt import (
    HIGHLIGHT_SCHEMA,
    RANK_SCHEMA,
    RANK_SYSTEM_PROMPT,
    HighlightResponse,
    RankResponse,
    rank_prompt,
    system_prompt,
    user_prompt,
)
from src.application.services.pipeline_dispatcher import ProgressCallback
from src.domain.enums.video_file_enum import VideoFile
from src.domain.exceptions import InvalidLLMOutputException, NotFoundException
from src.domain.models.clip import Clip, ClipCandidate
from src.domain.models.edl import Edl
from src.domain.models.job import Job
from src.domain.models.speech import TimeSpan
from src.domain.models.transcript import Segment, Transcript, Word
from src.domain.services.clip_candidates import select_clips
from src.domain.services.transcript_windowing import window_segments
from src.domain.services.virality import blend_with_ranking, high_energy_segments
from src.ports.output.clip_repository import ClipRepository
from src.ports.output.file_storage_port import FileStoragePort
from src.ports.output.llm_port import LLMPort
from src.ports.output.video_repository import VideoRepository

logger = logging.getLogger(__name__)

#: Asks per prompt before giving up on malformed answers.
_ATTEMPTS = 2
#: Share of progress spent on the per-window pass; the ranking pass takes the rest.
_WINDOW_SHARE = 0.9
#: The ranking pass sees this many times ``max_count`` candidates (at most _MAX_RANKED).
_RANK_POOL = 2
_MAX_RANKED = 20


class HighlightAnalysisService:
    """ANALYZE stage. The LLM proposes and rates clips window by window (concurrently;
    the adapter's semaphore bounds requests), loud moments flagged from the waveform.
    The best candidates of the whole video are then ranked against each other in one
    request, and that ranking decides which clips are kept."""

    def __init__(
        self,
        videos: VideoRepository,
        storage: FileStoragePort,
        clips: ClipRepository,
        llm: LLMPort,
        min_seconds: float,
        max_seconds: float,
        max_count: int,
        window_seconds: float,
    ) -> None:
        self._videos = videos
        self._storage = storage
        self._clips = clips
        self._llm = llm
        self._min_seconds = min_seconds
        self._max_seconds = max_seconds
        self._max_count = max_count
        self._window_seconds = window_seconds

    async def __call__(self, job: Job, report: ProgressCallback) -> None:
        video = await self._videos.get(job.video_id) if job.video_id else None
        if video is None:
            raise NotFoundException(f"Video {job.video_id} not found")
        transcript = Transcript.model_validate_json(
            await self._storage.read_text(video.id, VideoFile.TRANSCRIPT)
        )
        loud = await self._loud_segments(video.id, transcript.segments)
        windows = window_segments(transcript.segments, window=self._window_seconds)
        system = system_prompt(self._min_seconds, self._max_seconds)
        answers: list[list[ClipCandidate] | None] = []

        async def analyze(window: list[Segment]) -> None:
            answers.append(await self._ask(system, window, loud))
            await report(_WINDOW_SHARE * len(answers) / len(windows))

        try:
            async with asyncio.TaskGroup() as group:
                for window in windows:
                    group.create_task(analyze(window))
        except ExceptionGroup as errors:
            raise errors.exceptions[0] from errors

        if answers and all(answer is None for answer in answers):
            raise InvalidLLMOutputException(
                "The LLM never returned usable JSON; try a larger or more capable model"
            )
        candidates = [c for answer in answers if answer for c in answer]
        pool = select_clips(
            candidates,
            transcript.segments,
            self._min_seconds,
            self._max_seconds,
            min(self._max_count * _RANK_POOL, _MAX_RANKED),
        )
        words = [word for segment in transcript.segments for word in segment.words]
        ranked = await self._rank(pool, words)
        await report(1.0)

        await self._clips.replace_for_video(
            video.id,
            [
                Clip(
                    video_id=video.id,
                    title=candidate.title.strip(),
                    hook=candidate.hook.strip(),
                    score=candidate.score,
                    reason=candidate.reason.strip(),
                    start=span.start,
                    end=span.end,
                    edl=Edl.for_span(span, words),
                )
                for candidate, span in ranked[: self._max_count]
            ],
        )

    async def _loud_segments(self, video_id: UUID, segments: list[Segment]) -> set[int]:
        try:
            peaks = json.loads(await self._storage.read_text(video_id, VideoFile.PEAKS))
        except FileNotFoundError:
            return set()
        return high_energy_segments(segments, peaks["peaks"], peaks["per_second"])

    async def _ask(
        self, system: str, window: list[Segment], loud: set[int]
    ) -> list[ClipCandidate] | None:
        """The window's candidates, or None when the LLM kept answering malformed JSON."""
        user = user_prompt(window, loud)
        for attempt in range(1, _ATTEMPTS + 1):
            try:
                answer = await self._llm.complete_json(system, user, HIGHLIGHT_SCHEMA)
                return [
                    clip.to_candidate() for clip in HighlightResponse.model_validate(answer).clips
                ]
            except (InvalidLLMOutputException, ValidationError) as exc:
                logger.warning(
                    "Malformed LLM answer for segments %d-%d (attempt %d): %s",
                    window[0].id,
                    window[-1].id,
                    attempt,
                    exc,
                )
        return None

    async def _rank(
        self, pool: list[tuple[ClipCandidate, TimeSpan]], words: list[Word]
    ) -> list[tuple[ClipCandidate, TimeSpan]]:
        """Best first. Blends each rubric score with the LLM's head-to-head ranking;
        falls back to rubric order if the ranking can't be obtained."""
        by_score = sorted(pool, key=lambda item: item[0].score, reverse=True)
        if len(by_score) < 2:
            return by_score
        shown = [
            (
                candidate.title,
                span.duration,
                " ".join(w.text for w in words if span.start <= w.start and w.end <= span.end),
            )
            for candidate, span in by_score
        ]
        ranking = await self._ask_ranking(rank_prompt(shown))
        if ranking is None:
            return by_score
        # Prompt numbers are 1-based.
        scores = blend_with_ranking([c.score for c, _ in by_score], [n - 1 for n in ranking])
        rescored = [
            (candidate.model_copy(update={"score": score}), span)
            for (candidate, span), score in zip(by_score, scores, strict=True)
        ]
        return sorted(rescored, key=lambda item: item[0].score, reverse=True)

    async def _ask_ranking(self, user: str) -> list[int] | None:
        for attempt in range(1, _ATTEMPTS + 1):
            try:
                answer = await self._llm.complete_json(RANK_SYSTEM_PROMPT, user, RANK_SCHEMA)
                return RankResponse.model_validate(answer).ranking
            except (InvalidLLMOutputException, ValidationError) as exc:
                logger.warning("Malformed ranking answer (attempt %d): %s", attempt, exc)
        return None
