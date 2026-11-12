from datetime import UTC, datetime
from uuid import UUID

from src.application.services.edit_media import check_files, media_durations
from src.domain.enums.video_file_enum import VideoFile
from src.domain.exceptions import AppConflictException, AppValidationException, NotFoundException
from src.domain.models.app_event import ClipEvent
from src.domain.models.clip import Clip, ClipRevision
from src.domain.models.edit_command import EditCommand
from src.domain.models.edl import Edl, Tracking
from src.domain.models.timeline import TimelineView
from src.domain.models.transcript import Transcript, Word
from src.domain.models.video import Video
from src.domain.services.edl_commands import EditContext, apply_all, merge_tracking
from src.domain.services.edl_rules import edl_bounds, validate_edl
from src.ports.output.clip_repository import ClipRepository
from src.ports.output.file_storage_port import FileStoragePort
from src.ports.output.progress_port import ProgressPort
from src.ports.output.video_repository import VideoRepository

#: Attempts at applying a background result (face tracking) while the user is editing.
_BACKGROUND_RETRIES = 5


class ClipEditingService:
    def __init__(
        self,
        clips: ClipRepository,
        videos: VideoRepository,
        storage: FileStoragePort,
        progress: ProgressPort,
    ) -> None:
        self._clips = clips
        self._videos = videos
        self._storage = storage
        self._progress = progress
        #: video id → (transcript mtime, words); transcripts of long videos are large.
        self._transcripts: dict[UUID, tuple[float, list[Word]]] = {}

    async def list_for_video(self, video_id: UUID) -> list[Clip]:
        if await self._videos.get(video_id) is None:
            raise NotFoundException(f"Video {video_id} not found")
        return await self._clips.list_for_video(video_id)

    async def get(self, clip_id: UUID) -> Clip:
        clip = await self._clips.get(clip_id)
        if clip is None:
            raise NotFoundException(f"Clip {clip_id} not found")
        return clip

    async def apply_edits(
        self,
        clip_id: UUID,
        commands: list[EditCommand],
        base_revision: int | None = None,
        dry_run: bool = False,
        actor: str = "editor",
    ) -> Clip:
        if not commands:
            raise AppValidationException("No commands to apply")
        clip = await self.get(clip_id)
        base = _check_base(clip, base_revision)
        video = await self._video(clip)
        ctx = EditContext(
            clip_video=video.id,
            source_duration=video.duration,
            transcript=await self._words(video.id),
            media_durations=await self._durations(clip.edl, commands),
        )
        edl = apply_all(clip.edl, commands, ctx)
        check_files(edl, self._storage)
        clip.edl = edl
        if dry_run:
            return clip
        return await self._commit(clip, base, _label(commands), actor)

    async def update_edl(
        self, clip_id: UUID, edl: Edl, base_revision: int | None = None, actor: str = "editor"
    ) -> Clip:
        clip = await self.get(clip_id)
        base = _check_base(clip, base_revision)
        video = await self._video(clip)
        validate_edl(
            edl, video.duration, await media_durations(edl, {video.id}, self._videos, self._storage)
        )
        check_files(edl, self._storage)
        clip.edl = edl
        return await self._commit(clip, base, "Replace the edit", actor)

    async def undo(self, clip_id: UUID, actor: str = "editor") -> Clip:
        return await self._step(clip_id, -1, actor)

    async def redo(self, clip_id: UUID, actor: str = "editor") -> Clip:
        return await self._step(clip_id, +1, actor)

    async def describe(self, clip_id: UUID) -> TimelineView:
        clip = await self.get(clip_id)
        revisions = {r.revision for r in await self._clips.history(clip_id)}
        return TimelineView.build(
            clip, can_undo=clip.revision - 1 in revisions, can_redo=clip.revision + 1 in revisions
        )

    async def history(self, clip_id: UUID) -> list[ClipRevision]:
        await self.get(clip_id)
        return await self._clips.history(clip_id)

    async def apply_tracking(self, clip_id: UUID, tracking: Tracking) -> Clip:
        for _ in range(_BACKGROUND_RETRIES):
            clip = await self.get(clip_id)
            base = clip.revision
            clip.edl = merge_tracking(clip.edl, tracking)
            try:
                return await self._commit(clip, base, "Face tracking", "tracking")
            except AppConflictException:
                continue  # the user edited meanwhile: merge into their latest version
        raise AppConflictException("The clip kept changing; face tracking wasn't applied")

    async def _step(self, clip_id: UUID, direction: int, actor: str) -> Clip:
        clip = await self.get(clip_id)
        current = clip.revision
        edl = await self._clips.revision_edl(clip_id, current + direction)
        if edl is None:
            raise AppValidationException("Nothing to undo" if direction < 0 else "Nothing to redo")
        clip.edl, clip.revision = edl, current + direction
        _set_bounds(clip)
        if not await self._clips.move_to_revision(clip, current):
            raise AppConflictException("The clip was changed meanwhile; reload it")
        await self._publish(clip, actor)
        return clip

    async def _commit(self, clip: Clip, base: int, label: str, actor: str) -> Clip:
        _set_bounds(clip)
        if not await self._clips.commit_edit(clip, base, label, actor):
            raise AppConflictException("The clip was changed meanwhile; reload it")
        await self._publish(clip, actor)
        return clip

    async def _publish(self, clip: Clip, actor: str) -> None:
        await self._progress.publish(
            ClipEvent(clip_id=clip.id, video_id=clip.video_id, revision=clip.revision, actor=actor)
        )

    async def _video(self, clip: Clip) -> Video:
        video = await self._videos.get(clip.video_id)
        if video is None or video.duration is None:
            raise NotFoundException(f"Video {clip.video_id} not found")
        return video

    async def _durations(self, edl: Edl, commands: list[EditCommand]) -> dict[UUID, float]:
        """Durations of the videos the EDL uses plus any a command brings in."""
        extra = {m for c in commands if (m := getattr(c, "media", None)) is not None}
        return await media_durations(edl, extra, self._videos, self._storage)

    async def _words(self, video_id: UUID) -> list[Word]:
        path = self._storage.path(video_id, VideoFile.TRANSCRIPT)
        try:
            mtime = path.stat().st_mtime
        except FileNotFoundError:
            return []  # not transcribed yet: captions just stay empty
        cached = self._transcripts.get(video_id)
        if cached and cached[0] == mtime:
            return cached[1]
        transcript = Transcript.model_validate_json(
            await self._storage.read_text(video_id, VideoFile.TRANSCRIPT)
        )
        words = sorted((w for s in transcript.segments for w in s.words), key=lambda w: w.start)
        self._transcripts[video_id] = (mtime, words)
        return words


def _check_base(clip: Clip, base_revision: int | None) -> int:
    if base_revision is not None and base_revision != clip.revision:
        raise AppConflictException(
            f"The clip is at revision {clip.revision}, not {base_revision}; reload it"
        )
    return clip.revision


def _set_bounds(clip: Clip) -> None:
    bounds = edl_bounds(clip.edl)
    if bounds is not None:
        clip.start, clip.end = bounds.start, bounds.end
    clip.updated_at = datetime.now(UTC)


def _label(commands: list[EditCommand]) -> str:
    """History label, e.g. "split, set_transition"."""
    ops = list(dict.fromkeys(c.op for c in commands))
    return ", ".join(ops[:4]) + ("…" if len(ops) > 4 else "")
