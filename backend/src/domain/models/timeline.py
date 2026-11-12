"""A clip's timeline as an LLM (or any client) can read it without doing the maths:
every segment with its output times and what is said in it."""

from uuid import UUID

from pydantic import BaseModel

from src.domain.enums.aspect_ratio_enum import AspectRatio
from src.domain.enums.caption_style_enum import CaptionStyle
from src.domain.models.clip import Clip
from src.domain.models.edl import (
    BrollItem,
    Color,
    Crop,
    Marker,
    Music,
    Overlay,
    Transition,
    VideoSegment,
)
from src.domain.services.sequence import layout, output_duration, words_inside


class SegmentView(BaseModel):
    id: str
    index: int
    kind: str
    #: Where it plays in the clip (transition overlaps included).
    output_start: float
    output_end: float
    #: Video it comes from; None = the clip's own video.
    media: UUID | None = None
    image: str | None = None
    #: Video segments: the stretch of the video it plays.
    source_start: float | None = None
    source_end: float | None = None
    #: Freeze frames: the frame held.
    at: float | None = None
    speed: float | None = None
    volume: float | None = None
    transition_in: Transition | None = None
    color: Color | None = None
    crop: Crop | None = None
    crop_to: Crop | None = None
    #: The captions spoken in it (clip-video segments only).
    text: str = ""


class TimelineView(BaseModel):
    clip_id: UUID
    video_id: UUID
    title: str
    revision: int
    can_undo: bool
    can_redo: bool
    #: Output seconds.
    duration: float
    aspect: AspectRatio
    crop: Crop
    split_screen: bool
    tracking_enabled: bool
    caption_style: CaptionStyle
    fade_in: float
    fade_out: float
    segments: list[SegmentView]
    overlays: list[Overlay]
    broll: list[BrollItem]
    markers: list[Marker]
    music: Music | None

    @classmethod
    def build(cls, clip: Clip, can_undo: bool, can_redo: bool) -> "TimelineView":
        edl = clip.edl
        segments = []
        for p in layout(edl.segments):
            s = p.segment
            view = SegmentView(
                id=s.id,
                index=p.index,
                kind=s.kind,
                output_start=round(p.start, 3),
                output_end=round(p.end, 3),
                transition_in=s.transition if p.index > 0 else None,
                color=None if s.color.neutral else s.color,
                crop=s.crop,
            )
            if isinstance(s, VideoSegment):
                view.media, view.source_start, view.source_end = s.media, s.start, s.end
                view.speed, view.volume, view.crop_to = s.speed, s.volume, s.crop_to
                if s.media is None:
                    view.text = " ".join(
                        w.text for w in words_inside(edl.captions.words, s.start, s.end)
                    )
            elif s.kind == "freeze":
                view.media, view.at = s.media, s.at
            else:
                view.image, view.crop_to = s.image, s.crop_to
            segments.append(view)
        return cls(
            clip_id=clip.id,
            video_id=clip.video_id,
            title=clip.title,
            revision=clip.revision,
            can_undo=can_undo,
            can_redo=can_redo,
            duration=round(output_duration(edl.segments), 3),
            aspect=edl.aspect,
            crop=edl.crop,
            split_screen=edl.split_screen,
            tracking_enabled=bool(edl.tracking and edl.tracking.enabled),
            caption_style=edl.captions.style,
            fade_in=edl.fade_in,
            fade_out=edl.fade_out,
            segments=segments,
            overlays=edl.overlays,
            broll=edl.broll,
            markers=edl.markers,
            music=edl.music,
        )
