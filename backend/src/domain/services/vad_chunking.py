"""Packs speech segments into the spans sent to speech-to-text."""

import math

from src.domain.models.speech import TimeSpan

#: Whisper's native window; also keeps cloud uploads small and parallel.
MAX_CHUNK_SECONDS = 30.0
#: Silence longer than this is skipped instead of transcribed.
SPLIT_GAP_SECONDS = 2.0
#: Context kept around each segment so word edges aren't clipped.
PAD_SECONDS = 0.2


def build_chunks(
    segments: list[TimeSpan],
    duration: float,
    max_chunk: float = MAX_CHUNK_SECONDS,
    split_gap: float = SPLIT_GAP_SECONDS,
    pad: float = PAD_SECONDS,
) -> list[TimeSpan]:
    """Greedily merge padded segments into chunks of at most ``max_chunk`` seconds.
    Chunks break only in pauses between segments (never mid-speech) unless a single
    segment is longer than ``max_chunk``. Chunks never overlap, so no word is
    transcribed twice."""
    chunks: list[TimeSpan] = []
    current: TimeSpan | None = None

    for segment in segments:
        padded = TimeSpan(start=max(0.0, segment.start - pad), end=min(duration, segment.end + pad))
        for piece in _split(padded, max_chunk):
            if current is not None and (
                piece.start - current.end <= split_gap and piece.end - current.start <= max_chunk
            ):
                current = TimeSpan(start=current.start, end=max(current.end, piece.end))
                continue
            if current is not None:
                chunks.append(current)
                piece = TimeSpan(start=max(piece.start, current.end), end=piece.end)
            current = piece

    if current is not None:
        chunks.append(current)
    return [chunk for chunk in chunks if chunk.duration > 0]


def _split(span: TimeSpan, max_length: float) -> list[TimeSpan]:
    count = max(1, math.ceil(span.duration / max_length))
    step = span.duration / count
    return [
        TimeSpan(
            start=span.start + i * step,
            end=span.start + (i + 1) * step if i < count - 1 else span.end,
        )
        for i in range(count)
    ]
