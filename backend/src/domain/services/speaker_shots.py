"""Turn per-frame active-speaker scores into hard-cut shots of whoever is talking."""

import statistics

from src.domain.models.edl import Shot
from src.domain.models.face_track import FaceTrack
from src.domain.models.speech import TimeSpan

#: Frames either side averaged before picking a speaker (as Light-ASD's demo does).
_SMOOTHING = 2
#: Track pieces whose median centres are closer than this (fraction of the frame) and
#: that never overlap in time are one person who was briefly lost by the detector.
_SAME_PERSON = 0.1
#: Score given to the frames between a person's pieces: not speaking.
_UNSEEN = -5.0


def build_shots(
    tracks: list[FaceTrack], span: TimeSpan, fps: float, min_shot_seconds: float
) -> list[Shot]:
    """One shot per run of the same speaker, ``span.start`` onwards.

    Each frame goes to the face with the highest positive score; frames where nobody
    speaks keep the previous speaker, and the lead-in goes to whoever speaks most.
    Runs shorter than ``min_shot_seconds`` merge into the longer neighbour, and each
    shot is centred on the median position of its face. Faces are numbered 0, 1, …
    (see ``_join_pieces``). No faces → no shots."""
    if not tracks:
        return []
    tracks = _join_pieces(tracks)
    frame_count = max(t.first_frame + len(t.scores) for t in tracks)
    speakers = _speakers(tracks, frame_count)
    runs = _merge_short(_runs(speakers), max(1, round(min_shot_seconds * fps)))
    by_id = {t.id: t for t in tracks}
    shots = []
    for face, start, end in runs:
        x, y = _median_centre(by_id[face], start, end)
        shots.append(Shot(start=round(span.start + start / fps, 3), face=face, x=x, y=y))
    return shots


def _join_pieces(tracks: list[FaceTrack]) -> list[FaceTrack]:
    """One track per person: longest pieces first, each later piece joins the first
    person it doesn't overlap in time and sits close to. Gaps between pieces hold the
    nearest position and score as not speaking."""
    people: list[list[FaceTrack]] = []
    for piece in sorted(tracks, key=lambda t: -len(t.scores)):
        centre = _median(piece.centres)
        person = next(
            (
                group
                for group in people
                if all(_disjoint(piece, other) for other in group)
                and _distance(centre, _median(group[0].centres)) < _SAME_PERSON
            ),
            None,
        )
        if person is None:
            people.append([piece])
        else:
            person.append(piece)

    # Numbered by first appearance, left to right among faces that appear together.
    people.sort(key=lambda g: (min(t.first_frame for t in g), _median(g[0].centres)[0]))
    joined = []
    for index, group in enumerate(people):
        group.sort(key=lambda t: t.first_frame)
        centres, scores = list(group[0].centres), list(group[0].scores)
        for piece in group[1:]:
            gap = piece.first_frame - (group[0].first_frame + len(scores))
            centres += [centres[-1]] * gap + piece.centres
            scores += [_UNSEEN] * gap + piece.scores
        joined.append(
            FaceTrack(id=index, first_frame=group[0].first_frame, centres=centres, scores=scores)
        )
    return joined


def _disjoint(a: FaceTrack, b: FaceTrack) -> bool:
    return (
        a.first_frame + len(a.scores) <= b.first_frame
        or b.first_frame + len(b.scores) <= a.first_frame
    )


def _median(centres: list[tuple[float, float]]) -> tuple[float, float]:
    return statistics.median(c[0] for c in centres), statistics.median(c[1] for c in centres)


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def _speakers(tracks: list[FaceTrack], frame_count: int) -> list[int]:
    best: list[tuple[float, int] | None] = [None] * frame_count
    for track in tracks:
        for offset, score in enumerate(_smoothed(track.scores)):
            frame = track.first_frame + offset
            if score > 0 and (best[frame] is None or score > best[frame][0]):
                best[frame] = (score, track.id)
    picked = [b[1] if b else None for b in best]
    talking = [p for p in picked if p is not None]
    # Whoever speaks most leads; if nobody ever speaks, the face seen longest.
    lead = statistics.mode(talking) if talking else max(tracks, key=lambda t: len(t.scores)).id
    current, speakers = lead, []  # the lead-in (before anyone speaks) holds `lead`
    for p in picked:
        current = p if p is not None else current
        speakers.append(current)
    return speakers


def _smoothed(scores: list[float]) -> list[float]:
    return [
        statistics.fmean(scores[max(0, i - _SMOOTHING) : i + _SMOOTHING + 1])
        for i in range(len(scores))
    ]


def _runs(speakers: list[int]) -> list[tuple[int, int, int]]:
    """(face, first frame, end frame exclusive) for each stretch of one speaker."""
    runs: list[tuple[int, int, int]] = []
    for frame, face in enumerate(speakers):
        if runs and runs[-1][0] == face:
            runs[-1] = (face, runs[-1][1], frame + 1)
        else:
            runs.append((face, frame, frame + 1))
    return runs


def _merge_short(runs: list[tuple[int, int, int]], min_frames: int) -> list[tuple[int, int, int]]:
    """Fold the shortest too-short run into its longer neighbour until none is left."""
    runs = list(runs)
    while len(runs) > 1:
        index = min(range(len(runs)), key=lambda i: runs[i][2] - runs[i][1])
        face, start, end = runs[index]
        if end - start >= min_frames:
            break
        before = runs[index - 1] if index > 0 else None
        after = runs[index + 1] if index + 1 < len(runs) else None
        longer = max((r for r in (before, after) if r), key=lambda r: r[2] - r[1])
        runs[index] = (longer[0], start, end)
        merged: list[tuple[int, int, int]] = []
        for run in runs:
            if merged and merged[-1][0] == run[0]:
                merged[-1] = (run[0], merged[-1][1], run[2])
            else:
                merged.append(run)
        runs = merged
    return runs


def _median_centre(track: FaceTrack, start: int, end: int) -> tuple[float, float]:
    """Median face centre over the shot's frames, or the whole track when the face
    isn't visible during the shot (the speaker is held through a gap)."""
    first = max(start - track.first_frame, 0)
    inside = track.centres[first : max(end - track.first_frame, 0)] or track.centres
    x, y = _median(inside)
    return round(x, 4), round(y, 4)
