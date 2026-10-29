from pydantic import BaseModel, model_validator


class TimeSpan(BaseModel):
    """A stretch of the source timeline, in seconds."""

    start: float
    end: float

    @model_validator(mode="after")
    def _ordered(self) -> "TimeSpan":
        if self.end < self.start:
            raise ValueError(f"span ends ({self.end}) before it starts ({self.start})")
        return self

    @property
    def duration(self) -> float:
        return self.end - self.start


class SpeechMap(BaseModel):
    """Where the VAD heard speech in a video."""

    duration: float
    segments: list[TimeSpan]
