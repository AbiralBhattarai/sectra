"""Applies edit commands (domain/models/edit_command.py) to an EDL. Pure: everything a
command needs beyond the EDL comes in an ``EditContext``. Every result is validated, so a
command that produces an unrenderable edit fails with a message naming it."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from uuid import UUID

from src.domain.exceptions import AppValidationException
from src.domain.models.edit_command import (
    AddBroll,
    AddMarker,
    AddOverlay,
    Delete,
    DeleteWords,
    Duplicate,
    EditCommand,
    EditWords,
    FreezeFrame,
    Insert,
    InsertImage,
    Move,
    ReframeShot,
    RemoveBroll,
    RemoveMarker,
    RemoveMusic,
    RemoveOverlay,
    RemoveTransition,
    RestoreWords,
    SetMusic,
    SetTransition,
    Split,
    Trim,
    UpdateBroll,
    UpdateClip,
    UpdateOverlay,
    UpdateSegment,
)
from src.domain.models.edl import (
    BrollItem,
    Edl,
    FreezeSegment,
    ImageSegment,
    Marker,
    Music,
    Overlay,
    Segment,
    Shot,
    Tracking,
    Transition,
    VideoSegment,
    new_id,
)
from src.domain.models.speech import TimeSpan
from src.domain.models.transcript import Word
from src.domain.services.color_grading import PRESETS
from src.domain.services.edl_rules import MIN_SEGMENT_SECONDS, validate_edl
from src.domain.services.framing import crop_at
from src.domain.services.sequence import EPSILON, layout, media_time, placed_at, words_inside


@dataclass(frozen=True)
class EditContext:
    #: The clip's own video; segments that name it are stored with ``media=None``.
    clip_video: UUID
    source_duration: float
    #: Every word of the clip video's transcript, sorted.
    transcript: list[Word]
    #: Length of every other video an edit may use.
    media_durations: Mapping[UUID, float] = field(default_factory=dict)
    new_id: Callable[[], str] = new_id


def apply_all(edl: Edl, commands: list[EditCommand], ctx: EditContext) -> Edl:
    for number, command in enumerate(commands, start=1):
        try:
            edl = apply(edl, command, ctx)
            validate_edl(
                edl,
                ctx.source_duration,
                {**ctx.media_durations, ctx.clip_video: ctx.source_duration},
            )
        except AppValidationException as e:
            raise AppValidationException(f"Command {number} ({command.op}): {e}") from e
    return edl


def apply(edl: Edl, command: EditCommand, ctx: EditContext) -> Edl:  # noqa: C901
    match command:
        case Split(at=at):
            return _split(edl, at, ctx)
        case Trim():
            return _trim(edl, command, ctx)
        case Delete(segment_ids=ids):
            for segment_id in ids:
                _find(edl, segment_id)
            return _with_segments(edl, [s for s in edl.segments if s.id not in ids], ctx)
        case Move(segment_id=segment_id, to_index=to_index):
            segments = list(edl.segments)
            segment = segments.pop(_find(edl, segment_id))
            segments.insert(min(to_index, len(segments)), segment)
            return _with_segments(edl, segments, ctx)
        case Duplicate(segment_id=segment_id, to_index=to_index):
            index = _find(edl, segment_id)
            copy = edl.segments[index].model_copy(update={"id": ctx.new_id(), "transition": None})
            at = index + 1 if to_index is None else to_index
            return _with_segments(edl, _inserted(edl.segments, at, copy), ctx)
        case Insert(start=start, end=end, media=media, at_index=at_index):
            if end <= start:
                raise AppValidationException("The out point must come after the in point")
            segment = VideoSegment(id=ctx.new_id(), media=_media(media, ctx), start=start, end=end)
            return _with_segments(edl, _inserted(edl.segments, at_index, segment), ctx)
        case InsertImage(image=image, duration=duration, at_index=at_index):
            segment = ImageSegment(id=ctx.new_id(), image=image, duration=duration)
            return _with_segments(edl, _inserted(edl.segments, at_index, segment), ctx)
        case FreezeFrame(at=at, duration=duration):
            return _freeze(edl, at, duration, ctx)
        case UpdateSegment():
            return _update_segments(edl, command, ctx)
        case SetTransition(segment_id=segment_id, type=kind, duration=duration):
            index = _find(edl, segment_id)
            if index == 0:
                raise AppValidationException("The first segment has nothing to transition from")
            transition = Transition(type=kind, duration=duration)
            return _replace(
                edl, index, edl.segments[index].model_copy(update={"transition": transition})
            )
        case RemoveTransition(segment_id=segment_id):
            index = _find(edl, segment_id)
            return _replace(edl, index, edl.segments[index].model_copy(update={"transition": None}))
        case UpdateClip():
            return _update_clip(edl, command)
        case SetMusic(file=file, volume=volume, duck=duck):
            return edl.model_copy(update={"music": Music(file=file, volume=volume, duck=duck)})
        case RemoveMusic():
            return edl.model_copy(update={"music": None})
        case EditWords(words=edits):
            words = list(edl.captions.words)
            for edit in edits:
                _check_word(words, edit.index)
                words[edit.index] = words[edit.index].model_copy(update={"text": edit.text.strip()})
            return _with_words(edl, words)
        case DeleteWords(indices=indices):
            for index in indices:
                _check_word(edl.captions.words, index)
            drop = set(indices)
            return _with_words(edl, [w for i, w in enumerate(edl.captions.words) if i not in drop])
        case RestoreWords(start=start, end=end):
            low, high = (
                start if start is not None else 0.0,
                end if end is not None else float("inf"),
            )
            outside = [w for w in edl.captions.words if not (w.start >= low and w.end <= high)]
            fresh = [
                w
                for w in ctx.transcript
                if w.start >= low and w.end <= high and _covered(w, edl.segments)
            ]
            return _with_words(edl, sorted([*outside, *fresh], key=lambda w: w.start))
        case AddOverlay():
            fields = command.model_dump(exclude={"op"})
            overlays = [*edl.overlays, Overlay(id=ctx.new_id(), **fields)]
            return edl.model_copy(update={"overlays": overlays})
        case UpdateOverlay(id=item_id):
            return edl.model_copy(
                update={"overlays": _patched(edl.overlays, item_id, command, "overlay")}
            )
        case RemoveOverlay(id=item_id):
            return edl.model_copy(update={"overlays": _removed(edl.overlays, item_id, "overlay")})
        case AddBroll():
            item = BrollItem(id=ctx.new_id(), **command.model_dump(exclude={"op"}))
            return edl.model_copy(update={"broll": [*edl.broll, item]})
        case UpdateBroll(id=item_id):
            return edl.model_copy(update={"broll": _patched(edl.broll, item_id, command, "B-roll")})
        case RemoveBroll(id=item_id):
            return edl.model_copy(update={"broll": _removed(edl.broll, item_id, "B-roll")})
        case AddMarker(time=time, label=label):
            markers = sorted(
                [*edl.markers, Marker(id=ctx.new_id(), time=time, label=label)],
                key=lambda m: m.time,
            )
            return edl.model_copy(update={"markers": markers})
        case RemoveMarker(id=item_id):
            return edl.model_copy(update={"markers": _removed(edl.markers, item_id, "marker")})
        case ReframeShot(index=index, x=x, y=y):
            if edl.tracking is None or index >= len(edl.tracking.shots):
                raise AppValidationException(f"No face-tracking shot {index}")
            shots = list(edl.tracking.shots)
            shots[index] = shots[index].model_copy(update={"x": x, "y": y})
            tracking = edl.tracking.model_copy(update={"shots": shots})
            return edl.model_copy(update={"tracking": tracking})
    raise AppValidationException(f"Unknown command {command.op}")  # pragma: no cover


# --- Main track ------------------------------------------------------------------------


def _split(edl: Edl, at: float, ctx: EditContext) -> Edl:
    p = placed_at(layout(edl.segments), at)
    if p is None:
        raise AppValidationException(f"{at:.2f}s is past the end of the clip")
    segment = p.segment
    if isinstance(segment, VideoSegment):
        t = media_time(p, at)
        if t - segment.start < MIN_SEGMENT_SECONDS or segment.end - t < MIN_SEGMENT_SECONDS:
            raise AppValidationException(
                f"{at:.2f}s is too close to an edge of segment {segment.id}"
            )
        middle = crop_at(edl, segment, t) if segment.crop_to else None
        first = segment.model_copy(
            update={"end": t, "audio_fade_out": 0.0, **({"crop_to": middle} if middle else {})}
        )
        second = segment.model_copy(
            update={"id": ctx.new_id(), "start": t, "transition": None, "audio_fade_in": 0.0,
                    **({"crop": middle} if middle else {})}
        )  # fmt: skip
    else:
        local = at - p.start
        if local < MIN_SEGMENT_SECONDS or segment.duration - local < MIN_SEGMENT_SECONDS:
            raise AppValidationException(
                f"{at:.2f}s is too close to an edge of segment {segment.id}"
            )
        first = segment.model_copy(update={"duration": local})
        second = segment.model_copy(
            update={"id": ctx.new_id(), "duration": segment.duration - local, "transition": None}
        )
    segments = [*edl.segments[: p.index], first, second, *edl.segments[p.index + 1 :]]
    return _with_segments(edl, segments, ctx)


def _trim(edl: Edl, command: Trim, ctx: EditContext) -> Edl:
    index = _find(edl, command.segment_id)
    segment = edl.segments[index]
    if isinstance(segment, VideoSegment):
        if command.duration is not None:
            raise AppValidationException("Trim a video segment with start/end, not duration")
        start = segment.start if command.start is None else command.start
        end = segment.end if command.end is None else command.end
        if end - start < MIN_SEGMENT_SECONDS:
            raise AppValidationException(
                f"Segment {segment.id} would be shorter than {MIN_SEGMENT_SECONDS}s"
            )
        changed = segment.model_copy(update={"start": start, "end": end})
    else:
        if command.duration is None or command.start is not None or command.end is not None:
            raise AppValidationException(f"Trim a {segment.kind} segment with duration")
        changed = segment.model_copy(update={"duration": command.duration})
    return _replace(edl, index, changed, ctx)


def _freeze(edl: Edl, at: float, duration: float, ctx: EditContext) -> Edl:
    p = placed_at(layout(edl.segments), at)
    if p is None:
        raise AppValidationException(f"{at:.2f}s is past the end of the clip")
    segment = p.segment
    if isinstance(segment, ImageSegment):
        raise AppValidationException("An image is already still; trim it instead")
    t = media_time(p, at)
    frame = FreezeSegment(
        id=ctx.new_id(), media=segment.media, at=t, duration=duration,
        color=segment.color, crop=crop_at(edl, segment, t) if segment.crop else None,
    )  # fmt: skip
    if isinstance(segment, FreezeSegment):
        return _with_segments(edl, _inserted(edl.segments, p.index + 1, frame), ctx)
    if t - segment.start < MIN_SEGMENT_SECONDS:
        return _with_segments(edl, _inserted(edl.segments, p.index, frame), ctx)
    if segment.end - t < MIN_SEGMENT_SECONDS:
        return _with_segments(edl, _inserted(edl.segments, p.index + 1, frame), ctx)
    split = _split(edl, at, ctx)
    return _with_segments(split, _inserted(split.segments, p.index + 1, frame), ctx)


def _update_segments(edl: Edl, command: UpdateSegment, ctx: EditContext) -> Edl:
    if command.color is not None and command.color_preset is not None:
        raise AppValidationException("Give color or color_preset, not both")
    if command.clear_crop and (command.crop or command.crop_to):
        raise AppValidationException("clear_crop can't be combined with crop/crop_to")
    audio = {
        k: v
        for k, v in command.model_dump(
            include={"speed", "volume", "audio_fade_in", "audio_fade_out"}
        ).items()
        if v is not None
    }
    look: dict = {}
    if command.color is not None:
        look["color"] = command.color
    if command.color_preset is not None:
        look["color"] = PRESETS[command.color_preset]
    if command.crop is not None:
        look["crop"] = command.crop
    if command.clear_crop:
        look["crop"] = None
    segments = list(edl.segments)
    for segment_id in command.segment_ids:
        index = _find(edl, segment_id)
        segment = segments[index]
        update = dict(look)
        if audio:
            if not isinstance(segment, VideoSegment):
                raise AppValidationException(
                    f"Segment {segment_id} is a {segment.kind}; speed, volume and audio fades "
                    "apply to video segments"
                )
            update |= audio
        if command.crop_to is not None:
            if isinstance(segment, FreezeSegment):
                raise AppValidationException(
                    f"Segment {segment_id} is a freeze frame; it can't move"
                )
            if update.get("crop", segment.crop) is None:
                raise AppValidationException("crop_to needs a crop to start from")
            update["crop_to"] = command.crop_to
        if command.clear_crop and not isinstance(segment, FreezeSegment):
            update["crop_to"] = None
        segments[index] = segment.model_copy(update=update)
    return _with_segments(edl, segments, ctx)


def _update_clip(edl: Edl, command: UpdateClip) -> Edl:
    update = command.model_dump(
        include={"aspect", "crop", "split_screen", "fade_in", "fade_out"}, exclude_none=True
    )
    if command.crop is not None:
        update["crop"] = command.crop
    tracking = edl.tracking
    if command.tracking_enabled is not None:
        if tracking is None:
            if command.tracking_enabled:
                raise AppValidationException(
                    "Face tracking hasn't run for this clip; request it first"
                )
        else:
            tracking = tracking.model_copy(update={"enabled": command.tracking_enabled})
            if command.tracking_enabled:
                update["split_screen"] = False
    if command.split_screen and tracking is not None:
        tracking = tracking.model_copy(update={"enabled": False})
    update["tracking"] = tracking
    if command.caption_style is not None:
        update["captions"] = edl.captions.model_copy(update={"style": command.caption_style})
    return edl.model_copy(update=update)


def merge_tracking(edl: Edl, fresh: Tracking) -> Edl:
    """Apply a face-tracking result over the clip's previous one (after trimming past
    it): shots inside the old span stay as they are, since the user may have reframed
    them, and fresh shots fill in before and after. Turns split screen off."""
    old = edl.tracking
    if old is None:
        tracking = fresh.model_copy(update={"enabled": True})
    else:
        start, end = old.span.start, old.span.end
        before = [s for s in fresh.shots if s.start < start]
        after = [s for s in fresh.shots if s.start >= end]
        # Whoever the fresh result frames at the old span's end carries on from there.
        at_end = next((s for s in reversed(fresh.shots) if s.start < end), None)
        resume: list[Shot] = []
        if fresh.span.end > end and at_end and (not after or after[0].start != end):
            resume = [at_end.model_copy(update={"start": end})]
        tracking = Tracking(
            enabled=True,
            span=TimeSpan(start=min(start, fresh.span.start), end=max(end, fresh.span.end)),
            shots=[*before, *old.shots, *resume, *after],
        )
    return edl.model_copy(update={"tracking": tracking, "split_screen": False})


# --- Helpers ---------------------------------------------------------------------------


def _find(edl: Edl, segment_id: str) -> int:
    for index, segment in enumerate(edl.segments):
        if segment.id == segment_id:
            return index
    ids = ", ".join(s.id for s in edl.segments)
    raise AppValidationException(f"No segment {segment_id!r} (segments: {ids})")


def _inserted(segments: list[Segment], index: int | None, segment: Segment) -> list[Segment]:
    at = len(segments) if index is None else min(index, len(segments))
    return [*segments[:at], segment, *segments[at:]]


def _replace(edl: Edl, index: int, segment: Segment, ctx: EditContext | None = None) -> Edl:
    segments = [segment if i == index else s for i, s in enumerate(edl.segments)]
    if ctx is None:
        return edl.model_copy(update={"segments": segments})
    return _with_segments(edl, segments, ctx)


def _media(media: UUID | None, ctx: EditContext) -> UUID | None:
    return None if media == ctx.clip_video else media


def _coverage(segments: list[Segment]) -> list[tuple[float, float]]:
    return [(s.start, s.end) for s in segments if isinstance(s, VideoSegment) and s.media is None]


def _covered(word: Word, segments: list[Segment]) -> bool:
    return any(
        word.start >= a - EPSILON and word.end <= b + EPSILON for a, b in _coverage(segments)
    )


def _with_segments(edl: Edl, segments: list[Segment], ctx: EditContext) -> Edl:
    """New main track, with captions following it: edited words still inside a
    clip-video segment stay as they are; stretches that just became covered are filled
    from the transcript. The first segment never keeps a transition."""
    if segments and segments[0].transition is not None:
        segments = [segments[0].model_copy(update={"transition": None}), *segments[1:]]
    old = _coverage(edl.segments)
    kept = [w for w in edl.captions.words if _covered(w, segments)]
    added = [
        w
        for a, b in _merged(_coverage(segments))
        for w in words_inside(ctx.transcript, a, b)
        if not any(x <= (w.start + w.end) / 2 <= y for x, y in old)
    ]
    words = sorted([*kept, *added], key=lambda w: w.start)
    return edl.model_copy(
        update={"segments": segments, "captions": edl.captions.model_copy(update={"words": words})}
    )


def _merged(spans: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Union of spans (duplicated segments must not add their words twice)."""
    merged: list[tuple[float, float]] = []
    for a, b in sorted(spans):
        if merged and a <= merged[-1][1] + EPSILON:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged


def _with_words(edl: Edl, words: list[Word]) -> Edl:
    return edl.model_copy(update={"captions": edl.captions.model_copy(update={"words": words})})


def _check_word(words: list[Word], index: int) -> None:
    if index >= len(words):
        raise AppValidationException(f"No caption word {index} (there are {len(words)})")


def _patched[T: (Overlay, BrollItem)](items: list[T], item_id: str, command, kind: str) -> list[T]:
    changes = command.model_dump(exclude={"op", "id"}, exclude_none=True)
    found = False
    patched = []
    for item in items:
        if item.id == item_id:
            found = True
            item = type(item).model_validate({**item.model_dump(), **changes})
        patched.append(item)
    if not found:
        raise AppValidationException(f"No {kind} {item_id!r}")
    return patched


def _removed[T: (Overlay, BrollItem, Marker)](items: list[T], item_id: str, kind: str) -> list[T]:
    kept = [item for item in items if item.id != item_id]
    if len(kept) == len(items):
        raise AppValidationException(f"No {kind} {item_id!r}")
    return kept
