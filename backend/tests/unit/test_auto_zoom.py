from src.domain.models.speech import TimeSpan
from src.domain.models.transcript import Segment, Word
from src.domain.services.auto_zoom import (
    BEAT_SCALE,
    ENERGY_SCALE,
    HOOK_SCALE,
    MIN_ZOOM,
    PAYOFF_SCALE,
    auto_zooms,
)
from tests.unit.transcript_builders import evenly


def spoken(id: int, start: float, end: float, step: float = 0.5) -> Segment:
    """A segment with a word every ``step`` seconds."""
    words = []
    t = start
    while t < end - 1e-6:
        words.append(Word(text="w", start=round(t, 3), end=round(min(end, t + step * 0.8), 3)))
        t += step
    return Segment(id=id, start=start, end=end, text="w " * len(words), words=words)


def assert_well_formed(zooms, span):
    assert zooms == sorted(zooms, key=lambda z: z.start)
    for a, b in zip(zooms, zooms[1:], strict=False):
        assert a.end <= b.start + 1e-9, (a, b)
    for z in zooms:
        assert span.start <= z.start < z.end <= span.end
        assert z.end - z.start >= MIN_ZOOM - 1e-9


def test_hook_push_beats_and_payoff_without_peaks():
    segments = [spoken(i, i * 4.0, (i + 1) * 4.0) for i in range(8)]  # 0-32 s, 4 s sentences
    span = TimeSpan(start=0, end=32)

    zooms = auto_zooms(span, segments)

    assert_well_formed(zooms, span)
    hook = zooms[0]
    # Pushes in over the first sentence (4 s, capped at 3.5 s).
    assert (hook.start, hook.end, hook.scale, hook.ramp) == (0, 3.5, HOOK_SCALE, 2.0)
    payoff = zooms[-1]
    assert (payoff.start, payoff.end, payoff.scale) == (28, 31, PAYOFF_SCALE)
    beats = [z for z in zooms if z.scale == BEAT_SCALE]
    # Sentence starts at 4, 8, 12, … alternate 1x / zoomed, starting at 1x after the hook.
    assert [(z.start, z.end) for z in beats] == [(8, 12), (16, 20), (24, 28)]
    assert all(z.ramp == 0 for z in beats)


def test_energy_hit_wins_over_a_beat_and_snaps_to_a_word():
    segments = [spoken(i, i * 4.0, (i + 1) * 4.0) for i in range(8)]
    span = TimeSpan(start=0, end=32)
    peaks = [0.1] * (40 * 20)
    peaks[int(17.2 * 20) : int(18.0 * 20)] = [0.9] * 16  # a shout at ~17.2-18 s

    zooms = auto_zooms(span, segments, peaks, per_second=20)

    assert_well_formed(zooms, span)
    [hit] = [z for z in zooms if z.scale == ENERGY_SCALE]
    assert hit.start == 17.0  # the word starting just before the loud stretch
    assert hit.end == 18.3
    # The beat it landed in survives around it.
    around = [(z.start, z.end) for z in zooms if z.scale == BEAT_SCALE and 16 <= z.start < 20]
    assert around == [(16, 17), (18.3, 20)]


def test_monotone_loudness_gives_no_energy_hits():
    segments = [spoken(i, i * 4.0, (i + 1) * 4.0) for i in range(8)]
    zooms = auto_zooms(TimeSpan(start=0, end=32), segments, [0.5] * 800, per_second=20)
    assert not [z for z in zooms if z.scale == ENERGY_SCALE]


def test_long_sentences_are_split_and_long_silences_filled():
    # One 20 s sentence with a clear pause at 10 s, inside a 24 s clip.
    words = [Word(text="w", start=t / 2, end=t / 2 + 0.4) for t in range(0, 19)]
    words += [Word(text="w", start=10.8 + t / 2, end=10.8 + t / 2 + 0.4) for t in range(0, 19)]
    long = Segment(id=0, start=0, end=20, text="", words=words)
    segments = [long, spoken(1, 20, 24)]
    span = TimeSpan(start=0, end=24)

    zooms = auto_zooms(span, segments)

    assert_well_formed(zooms, span)
    starts = {z.start for z in zooms} | {z.end for z in zooms}
    assert 10.8 in starts  # the widest pause became a cut
    # No stretch of more than BEAT_MAX_GAP without a change after the hook.
    edges = sorted({0.0, 24.0} | starts)
    assert max(b - a for a, b in zip(edges, edges[1:], strict=False)) <= 6.0 + 1e-6


def test_clip_starting_mid_transcript_only_uses_its_own_sentences():
    span = TimeSpan(start=100, end=130)
    zooms = auto_zooms(span, evenly(30))  # 10 s single-word segments
    assert_well_formed(zooms, span)
    assert zooms[0].start == 100 and zooms[0].scale == HOOK_SCALE


def test_short_clip_without_speech_is_one_hook_push():
    zooms = auto_zooms(TimeSpan(start=5, end=7), [])
    assert [(z.start, z.end, z.scale, z.ramp) for z in zooms] == [(5, 7, HOOK_SCALE, 2)]
