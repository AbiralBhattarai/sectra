from enum import StrEnum


class VideoKind(StrEnum):
    """What a video is for: clipping a long source (Clipper) or a narrated story
    (Narrator), whose ``source.mp4`` is built from TTS narration."""

    SOURCE = "source"
    STORY = "story"
