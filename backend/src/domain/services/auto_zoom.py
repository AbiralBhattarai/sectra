"""Automatic zoom-ins for a clip, in the short-form style: a slow push on the hook,
punch-ins that alternate on sentence changes to keep the picture moving, a hard punch on
the loudest moments, and one on the payoff. Deterministic, from the transcript and the
waveform peaks only."""

from statistics import median

from src.domain.models.edl import Zoom
from src.domain.models.speech import TimeSpan
from src.domain.models.transcript import Segment, Word

HOOK_SCALE = 1.12
HOOK_RAMP = 2.0
#: The hook push runs to the end of the first sentence, within these bounds (seconds).
HOOK_MIN, HOOK_MAX = 1.5, 3.5
BEAT_SCALE = 1.15
#: Sentence-change punches are at least this far apart; a longer stretch gets one
#: added after ``BEAT_FILL`` seconds (snapped to a word).
BEAT_MIN_GAP, BEAT_MAX_GAP, BEAT_FILL = 3.0, 6.0, 4.0
#: A sentence longer than this is split at its widest pause.
LONG_SEGMENT = 6.0
ENERGY_SCALE = 1.3
ENERGY_LENGTH = 1.3
#: Loudness is averaged over this many seconds; hits are at least ``ENERGY_GAP`` apart,
#: about one per ``ENERGY_EVERY`` seconds of clip at most.
ENERGY_WINDOW, ENERGY_GAP, ENERGY_EVERY = 0.5, 2.5, 12.0
#: A hit must be in the clip's loudest 10% and clearly above its typical level.
ENERGY_PERCENTILE, ENERGY_OVER_MEDIAN = 0.9, 1.35
PAYOFF_SCALE = 1.25
PAYOFF_LENGTH = 3.0
#: The payoff punch only applies when the last sentence starts past this share of the clip.
PAYOFF_AFTER = 0.4
#: Shorter zooms (also what's left after a higher-priority zoom cut one) are dropped.
MIN_ZOOM = 0.8


def auto_zooms(
    span: TimeSpan,
    segments: list[Segment],
    peaks: list[float] | None = None,
    per_second: int = 20,
) -> list[Zoom]:
    """Zooms for the clip covering ``span`` (source time), sorted and non-overlapping.
    Where they compete, energy hits beat the payoff, which beats the hook push, which
    beats the sentence-change punches."""
    inside = [s for s in segments if s.end > span.start and s.start < span.end]
    words = [w for s in inside for w in s.words if span.start <= w.start < span.end]
    hook = _hook(span, inside)
    by_priority = [
        _energy_hits(span, words, peaks or [], per_second),
        _payoff(span, inside),
        [hook],
        _beats(span, inside, words, after=hook.end),
    ]
    placed: list[Zoom] = []
    for group in by_priority:
        for zoom in group:
            placed += _free_pieces(zoom, placed)
    return sorted(placed, key=lambda z: z.start)


def _hook(span: TimeSpan, inside: list[Segment]) -> Zoom:
    first_end = inside[0].end if inside else span.start + HOOK_MAX
    end = min(max(first_end, span.start + HOOK_MIN), span.start + HOOK_MAX, span.end)
    return _zoom(span.start, end, HOOK_SCALE, ramp=min(HOOK_RAMP, end - span.start))


def _beats(span: TimeSpan, inside: list[Segment], words: list[Word], after: float) -> list[Zoom]:
    """Alternate 1x / ``BEAT_SCALE`` at sentence changes after the hook, starting at 1x."""
    candidates = sorted(
        t for t in _sentence_starts(inside, words) if after + 1e-6 < t < span.end - MIN_ZOOM
    )
    cuts: list[float] = []
    last = after
    for t in candidates:
        while t - last > BEAT_MAX_GAP:
            last = _snap(last + BEAT_FILL, words)
            cuts.append(last)
        if t - last >= BEAT_MIN_GAP:
            cuts.append(t)
            last = t
    while span.end - last > BEAT_MAX_GAP:
        last = _snap(last + BEAT_FILL, words)
        cuts.append(last)
    bounds = [after, *cuts, span.end]
    return [
        _zoom(start, end, BEAT_SCALE)
        for index, (start, end) in enumerate(zip(bounds, bounds[1:], strict=False))
        if index % 2 == 1
    ]


def _sentence_starts(inside: list[Segment], words: list[Word]) -> list[float]:
    starts = []
    for segment in inside:
        own = [w for w in words if segment.start <= w.start < segment.end]
        starts.append(own[0].start if own else segment.start)
        if segment.end - segment.start > LONG_SEGMENT and len(own) > 2:
            middle = own[len(own) // 4 : len(own) - len(own) // 4] or own[1:]
            pause = max(middle, key=lambda w: w.start - _previous_end(own, w))
            starts.append(pause.start)
    return starts


def _previous_end(words: list[Word], word: Word) -> float:
    index = words.index(word)
    return words[index - 1].end if index else word.start


def _energy_hits(
    span: TimeSpan, words: list[Word], peaks: list[float], per_second: int
) -> list[Zoom]:
    first = max(0, int(span.start * per_second))
    last = min(len(peaks), int(span.end * per_second))
    window = max(1, round(ENERGY_WINDOW * per_second))
    if last - first < window * 2:
        return []
    levels = [
        (index, sum(peaks[index : index + window]) / window)
        for index in range(first, last - window + 1)
    ]
    values = sorted(level for _, level in levels)
    threshold = max(
        values[min(len(values) - 1, int(ENERGY_PERCENTILE * len(values)))],
        median(values) * ENERGY_OVER_MEDIAN,
    )
    budget = max(1, round(span.duration / ENERGY_EVERY))
    hits: list[float] = []
    for index, level in sorted(levels, key=lambda item: item[1], reverse=True):
        if level < threshold or len(hits) == budget:
            break
        moment = index / per_second  # where the loud stretch begins
        if all(abs(moment - other) >= ENERGY_GAP for other in hits):
            hits.append(moment)
    zooms = []
    for moment in hits:
        # Punch in on the word that carries the loud bit, not halfway through it.
        onsets = [w.start for w in words if moment - 0.6 <= w.start <= moment + 0.1]
        start = max(span.start, onsets[-1] if onsets else moment)
        zooms.append(_zoom(start, min(span.end, start + ENERGY_LENGTH), ENERGY_SCALE))
    return [z for z in zooms if z.end - z.start >= MIN_ZOOM]


def _payoff(span: TimeSpan, inside: list[Segment]) -> list[Zoom]:
    if len(inside) < 2:
        return []
    last = inside[-1]
    start = last.words[0].start if last.words else last.start
    if start - span.start < PAYOFF_AFTER * span.duration or span.end - start < MIN_ZOOM:
        return []
    return [_zoom(start, min(span.end, start + PAYOFF_LENGTH), PAYOFF_SCALE)]


def _snap(t: float, words: list[Word]) -> float:
    """The word start nearest ``t`` (within a second), else ``t``."""
    near = [w.start for w in words if abs(w.start - t) <= 1.0]
    return min(near, key=lambda s: abs(s - t)) if near else t


def _free_pieces(zoom: Zoom, placed: list[Zoom]) -> list[Zoom]:
    """The parts of ``zoom`` not covered by ``placed``, at least ``MIN_ZOOM`` long. A
    push keeps its ramp only on the piece that still starts where it did."""
    pieces = [(zoom.start, zoom.end)]
    for other in placed:
        pieces = [
            part
            for start, end in pieces
            for part in ((start, min(end, other.start)), (max(start, other.end), end))
            if part[1] - part[0] > 1e-6
        ]
    return [
        _zoom(start, end, zoom.scale, ramp=zoom.ramp if start == zoom.start else 0.0)
        for start, end in pieces
        if end - start >= MIN_ZOOM
    ]


def _zoom(start: float, end: float, scale: float, ramp: float = 0.0) -> Zoom:
    return Zoom(start=round(start, 3), end=round(end, 3), scale=scale, ramp=round(ramp, 3))
