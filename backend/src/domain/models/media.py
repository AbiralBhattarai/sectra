from pydantic import BaseModel


class MediaInfo(BaseModel):
    """What ffprobe reports about a media file. ``width``/``height`` are display
    dimensions, i.e. after applying rotation metadata."""

    duration: float
    width: int
    height: int
    video_codec: str
    pixel_format: str | None
    audio_codec: str | None  # None when the file has no audio stream


class NormalizePlan(BaseModel):
    """How to turn a downloaded/uploaded file into the stored source video."""

    #: Output size when the video must be scaled down, otherwise None.
    scale_to: tuple[int, int] | None
    reencode_video: bool
    reencode_audio: bool
