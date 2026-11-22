import asyncio
import json
import logging
from uuid import UUID

from pydantic import ValidationError

from src.application.prompts.highlight_prompt import (
    CLIPS_PER_WINDOW,
    HIGHLIGHT_SCHEMA,
    RANK_SCHEMA,
    HighlightResponse,
    RankResponse,
    rank_prompt,
    rank_system_prompt,
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
from src.domain.services.auto_zoom import auto_zooms
from src.domain.services.clip_candidates import DUPLICATE_IOU, select_clips
from src.domain.services.transcript_windowing import window_segments
from src.domain.services.virality import blend_with_ranking, high_energy_segments
from src.ports.input.clip_export_port import ClipExportPort
from src.ports.input.clip_tracking_port import ClipTrackingPort
from src.ports.output.clip_repository import ClipRepository
from src.ports.output.file_storage_port import FileStoragePort
from src.ports.output.llm_port import LLMPort
from src.ports.output.video_repository import VideoRepository

logger = logging.getLogger(__name__)

#: Asks per prompt before giving up on malformed answers.
_ATTEMPTS = 2
#: Share of progress spent on the per-window pass; the ranking pass takes the rest.
_WINDOW_SHARE = 0.9
#: The ranking pass sees this many times ``max_count`` candidates, at most _MAX_RANKED
#: (so the prompt fits a small context); any further clips follow in rubric order.
_RANK_POOL = 2
_MAX_RANKED = 20


class HighlightAnalysisService:
    """ANALYZE stage. The LLM proposes and rates clips window by window (concurrently;
    the adapter's semaphore bounds requests), loud moments flagged from the waveform.
    The best candidates of the whole video are then ranked against each other in one
    request, and that ranking decides which clips are kept.

    Optionally every clip gets automatic zoom-ins and is then handed on, best first, to
    face tracking (which exports when done) or straight to export, for the outbox."""

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
        clips_per_window: int = CLIPS_PER_WINDOW,
        max_overlap: float = DUPLICATE_IOU,
        auto_zoom: bool = False,
        tracking: ClipTrackingPort | None = None,
        exports: ClipExportPort | None = None,
    ) -> None:
        self._videos = videos
        self._storage = storage
        self._clips = clips
        self._llm = llm
        self._min_seconds = min_seconds
        self._max_seconds = max_seconds
        self._max_count = max_count
        self._window_seconds = window_seconds
        self._clips_per_window = clips_per_window
        self._max_overlap = max_overlap
        self._auto_zoom = auto_zoom
        self._tracking = tracking
        self._exports = exports

    async def __call__(self, job: Job, report: ProgressCallback) -> None:
        video = await self._videos.get(job.video_id) if job.video_id else None
        if video is None:
            raise NotFoundException(f"Video {job.video_id} not found")
        # Parsing, clip selection and EDL building are CPU work on large inputs; they run in
        # a thread so the event loop keeps serving the other consumers' Redis reads.
        transcript = await asyncio.to_thread(
            Transcript.model_validate_json,
            await self._storage.read_text(video.id, VideoFile.TRANSCRIPT),
        )
        peaks = await self._peaks(video.id)
        loud = (
            high_energy_segments(transcript.segments, peaks["peaks"], peaks["per_second"])
            if peaks
            else set()
        )
        windows = window_segments(transcript.segments, window=self._window_seconds)
        guidance = video.clip_prompt
        system = system_prompt(self._min_seconds, self._max_seconds, guidance)
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
        pool = await asyncio.to_thread(
            select_clips,
            candidates,
            transcript.segments,
            self._min_seconds,
            self._max_seconds,
            max(self._max_count, min(self._max_count * _RANK_POOL, _MAX_RANKED)),
            self._max_overlap,
        )
        words = [word for segment in transcript.segments for word in segment.words]
        ranked = await self._rank(pool, words, rank_system_prompt(guidance))
        await report(1.0)

        kept = await asyncio.to_thread(
            self._build_clips, video.id, ranked, words, transcript.segments, peaks
        )
        await self._clips.replace_for_video(video.id, kept)
        await self._hand_on(kept)

    def _build_clips(
        self,
        video_id: UUID,
        ranked: list[tuple[ClipCandidate, TimeSpan]],
        words: list[Word],
        segments: list[Segment],
        peaks: dict | None,
    ) -> list[Clip]:
        return [
            Clip(
                video_id=video_id,
                title=candidate.title.strip(),
                hook=candidate.hook.strip(),
                score=candidate.score,
                reason=candidate.reason.strip(),
                caption=candidate.caption.strip(),
                start=span.start,
                end=span.end,
                edl=self._edl(span, words, segments, peaks),
            )
            for candidate, span in ranked[: self._max_count]
        ]

    def _edl(
        self, span: TimeSpan, words: list[Word], segments: list[Segment], peaks: dict | None
    ) -> Edl:
        edl = Edl.for_span(span, words)
        if self._auto_zoom:
            edl.zooms = auto_zooms(
                span,
                segments,
                peaks["peaks"] if peaks else None,
                peaks["per_second"] if peaks else 20,
            )
        return edl

    async def _hand_on(self, clips: list[Clip]) -> None:
        """Queue the automatic edit of each clip, best first (that order is its rank in
        the outbox)."""
        for rank, clip in enumerate(clips, start=1):
            if self._tracking is not None:
                await self._tracking.request_tracking(clip.id, auto_rank=rank)
            elif self._exports is not None:
                await self._exports.request_export(clip.id, outbox_rank=rank)

    async def _peaks(self, video_id: UUID) -> dict | None:
        try:
            text = await self._storage.read_text(video_id, VideoFile.PEAKS)
        except FileNotFoundError:
            return None
        return await asyncio.to_thread(json.loads, text)

    async def _ask(
        self, system: str, window: list[Segment], loud: set[int]
    ) -> list[ClipCandidate] | None:
        """The window's candidates, or None when the LLM kept answering malformed JSON."""
        user = user_prompt(window, loud, self._clips_per_window)
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
        self, pool: list[tuple[ClipCandidate, TimeSpan]], words: list[Word], system: str
    ) -> list[tuple[ClipCandidate, TimeSpan]]:
        """Best first. The top ``_MAX_RANKED`` by rubric are ranked head to head: each
        rubric score is blended with that ranking (rubric order if no ranking can be
        obtained). The rest follow in rubric order, never scored above a ranked clip."""
        by_score = sorted(pool, key=lambda item: item[0].score, reverse=True)
        top, rest = by_score[:_MAX_RANKED], by_score[_MAX_RANKED:]
        ranked = await self._rank_top(top, words, system)
        if not rest:
            return ranked
        floor = min(candidate.score for candidate, _ in ranked)
        return ranked + [
            (candidate.model_copy(update={"score": min(candidate.score, floor)}), span)
            for candidate, span in rest
        ]

    async def _rank_top(
        self, by_score: list[tuple[ClipCandidate, TimeSpan]], words: list[Word], system: str
    ) -> list[tuple[ClipCandidate, TimeSpan]]:
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
        ranking = await self._ask_ranking(system, rank_prompt(shown))
        if ranking is None:
            return by_score
        # Prompt numbers are 1-based.
        scores = blend_with_ranking([c.score for c, _ in by_score], [n - 1 for n in ranking])
        rescored = [
            (candidate.model_copy(update={"score": score}), span)
            for (candidate, span), score in zip(by_score, scores, strict=True)
        ]
        return sorted(rescored, key=lambda item: item[0].score, reverse=True)

    async def _ask_ranking(self, system: str, user: str) -> list[int] | None:
        for attempt in range(1, _ATTEMPTS + 1):
            try:
                answer = await self._llm.complete_json(system, user, RANK_SCHEMA)
                return RankResponse.model_validate(answer).ranking
            except (InvalidLLMOutputException, ValidationError) as exc:
                logger.warning("Malformed ranking answer (attempt %d): %s", attempt, exc)
        return None
