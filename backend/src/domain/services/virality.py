"""How clip candidates are scored and ranked. Kept deterministic on purpose: LLMs
asked for a single 0-100 score cluster everything at 85-95, so the model rates
concrete qualities and the score is computed from them."""

from src.domain.models.transcript import Segment

#: Weight of each 0-10 rating in the final 0-100 score.
RUBRIC_WEIGHTS = {
    "hook": 0.30,  # do the first seconds stop the scroll?
    "emotion": 0.25,  # hype, anger, laughter, shock, tension
    "payoff": 0.20,  # punchline, reveal, insight, result
    "standalone": 0.15,  # makes sense with no context
    "shareability": 0.10,  # quotable / would people send it to a friend
}

#: Share of a video's segments marked as high-energy in the prompt.
HIGH_ENERGY_SHARE = 0.2


def rubric_score(ratings: dict[str, int]) -> int:
    """0-100 from the 0-10 ratings, weighted by ``RUBRIC_WEIGHTS``."""
    total = sum(weight * min(max(ratings[name], 0), 10) for name, weight in RUBRIC_WEIGHTS.items())
    return round(total * 10)


def high_energy_segments(segments: list[Segment], peaks: list[float], per_second: int) -> set[int]:
    """Ids of the loudest ``HIGH_ENERGY_SHARE`` of segments, by mean waveform level.
    Loudness is a strong signal for reactions, shouting and crowd noise, which the
    transcript text alone doesn't show."""
    if not segments or not peaks:
        return set()
    levels: dict[int, float] = {}
    for segment in segments:
        window = peaks[
            int(segment.start * per_second) : max(
                int(segment.end * per_second), int(segment.start * per_second) + 1
            )
        ]
        if window:
            levels[segment.id] = sum(window) / len(window)
    if not levels:
        return set()
    count = max(1, round(len(levels) * HIGH_ENERGY_SHARE))
    return {
        segment_id
        for segment_id, _ in sorted(levels.items(), key=lambda item: item[1], reverse=True)[:count]
    }


def blend_with_ranking(scores: list[int], ranking: list[int]) -> list[int]:
    """Final scores after the LLM ranked the candidates against each other:
    half the rubric score, half the rank (first = 100, last = 0). ``ranking`` lists
    candidate indexes best first; unranked candidates count as last."""
    count = len(scores)
    if count <= 1:
        return scores
    position = {index: rank for rank, index in enumerate(ranking) if 0 <= index < count}
    worst = count - 1
    return [
        round(0.5 * score + 0.5 * 100 * (1 - position.get(index, worst) / worst))
        for index, score in enumerate(scores)
    ]
