"""Small EDL builders with predictable ids (s1, s2, …)."""

from src.domain.models.edl import Captions, Edl, VideoSegment
from src.domain.models.render import MediaSource
from src.domain.models.transcript import Word


def words(*specs) -> list[Word]:
    return [Word(text=t, start=s, end=e) for t, s, e in specs]


def seg(start: float, end: float, id: str | None = None, **fields) -> VideoSegment:
    return VideoSegment(id=id or f"x{start:g}-{end:g}", start=start, end=end, **fields)


def edl(*spans, captions: list[Word] | None = None, **fields) -> Edl:
    """``spans`` are (start, end) tuples or ready segments; tuples get ids s1, s2, …"""
    segments = [
        s if not isinstance(s, tuple) else VideoSegment(id=f"s{i}", start=s[0], end=s[1])
        for i, s in enumerate(spans, start=1)
    ]
    return Edl(segments=segments, captions=Captions(words=captions or []), **fields)


def sources(width=1920, height=1080, has_audio=True, **others) -> dict[str, MediaSource]:
    return {"main": MediaSource(width=width, height=height, has_audio=has_audio), **others}


class Ids:
    """Deterministic ``new_id`` for EditContext: n1, n2, …"""

    def __init__(self) -> None:
        self.count = 0

    def __call__(self) -> str:
        self.count += 1
        return f"n{self.count}"
