from pydantic import BaseModel


class Word(BaseModel):
    text: str
    start: float
    end: float
    probability: float | None = None


class Segment(BaseModel):
    """Roughly a sentence, as the speech-to-text engine split it."""

    id: int
    start: float
    end: float
    text: str
    words: list[Word]


class Transcript(BaseModel):
    language: str | None
    segments: list[Segment]
