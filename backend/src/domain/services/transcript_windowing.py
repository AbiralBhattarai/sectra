from src.domain.models.transcript import Segment

#: Fits a ~4k-token context (Ollama's usual default) with room for the answer.
WINDOW_SECONDS = 300.0
#: A highlight straddling two windows still fits wholly inside one of them.
OVERLAP_SECONDS = 60.0


def window_segments(
    segments: list[Segment],
    window: float = WINDOW_SECONDS,
    overlap: float = OVERLAP_SECONDS,
) -> list[list[Segment]]:
    """Split the transcript into overlapping windows of whole segments, each
    covering at most ``window`` seconds (a single longer segment gets its own)."""
    if not segments:
        return []
    windows: list[list[Segment]] = []
    first = 0
    while True:
        start = segments[first].start
        last = first
        while last + 1 < len(segments) and segments[last + 1].end - start <= window:
            last += 1
        windows.append(segments[first : last + 1])
        if last == len(segments) - 1:
            return windows
        # Next window starts `overlap` seconds before this one ends, always advancing.
        resume = segments[last].end - overlap
        next_first = next(i for i in range(first + 1, last + 2) if segments[i].start >= resume)
        first = next_first
