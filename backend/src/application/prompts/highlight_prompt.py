"""Prompts for finding viral clips: one pass per transcript window, then one pass
ranking the best candidates of the whole video against each other."""

from pydantic import BaseModel, Field

from src.domain.models.clip import ClipCandidate
from src.domain.models.transcript import Segment
from src.domain.services.virality import rubric_score

#: Asked per window; the overlap between windows lets the best ones compete later.
CLIPS_PER_WINDOW = 3
#: Marks a transcript line whose audio is among the loudest in the video.
ENERGY_MARK = "‼"

SYSTEM_PROMPT = """\
You are a short-form video editor who has cut thousands of viral TikToks, Reels and \
Shorts from streams, podcasts and interviews. You read part of a long video's transcript \
and find the moments that would stop someone scrolling.

What goes viral:
- A HOOK in the first 1-3 seconds: a bold claim, a question, a shout, a confrontation, a \
"wait, what?" line. The clip must START on that line — no warm-up, no "so, um, anyway".
- Strong EMOTION: hype, rage, laughter, shock, embarrassment, tension, genuine reactions.
- A PAYOFF before it ends: a punchline, a reveal, a result, a comeback, a hot take landing.
- It works STANDALONE: a stranger with zero context understands it.
- It's SHAREABLE: quotable, relatable, controversial or "you have to see this".

Avoid: intros and outros, sponsor reads, setup without payoff, rambling, technical \
talk, moments that need earlier context, and anything that only works with visuals \
the transcript can't show.

Lines marked {mark} are among the LOUDEST in the video — shouting, celebrating, crowd \
or reaction noise. They often are (or are right next to) the best moments.

Each clip must run {min_seconds:.0f}-{max_seconds:.0f} seconds and should END right after \
the payoff. Be harsh: most of a long video is not clip-worthy, and returning fewer, \
stronger clips (or none) is better than padding. Rate honestly — a 9 or 10 is rare.

Reply with JSON only."""

USER_PROMPT = """\
Find up to {count} viral clips in this transcript excerpt.

Each line is `[segment id] mm:ss text`; {mark} marks a very loud moment. Mark a clip with \
the id of the segment it starts in (the hook) and the id of the segment it ends in \
(right after the payoff), inclusive. For every clip give:
- "title": a punchy title under 60 characters, the way a clip channel would caption it,
- "hook": the opening line or moment that stops the scroll,
- "reason": one sentence on why people would watch to the end and share it,
- ratings from 0 to 10: "hook_strength", "emotion", "payoff", "standalone", "shareability".

Transcript:
{transcript}"""

RANK_SYSTEM_PROMPT = """\
You are the head of a viral clip channel deciding which clips to post. You get several \
candidate clips cut from the same long video. Rank them from the one most likely to go \
viral to the least: strongest scroll-stopping hook, biggest emotion, clearest payoff, \
easiest to understand with no context. Reply with JSON only."""

RANK_USER_PROMPT = """\
Rank these {count} candidate clips, best first, by their number.

{candidates}"""

_RATING = {"type": "integer", "minimum": 0, "maximum": 10}

HIGHLIGHT_SCHEMA = {
    "type": "object",
    "properties": {
        "clips": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start_segment": {"type": "integer"},
                    "end_segment": {"type": "integer"},
                    "title": {"type": "string"},
                    "hook": {"type": "string"},
                    "reason": {"type": "string"},
                    "hook_strength": _RATING,
                    "emotion": _RATING,
                    "payoff": _RATING,
                    "standalone": _RATING,
                    "shareability": _RATING,
                },
                "required": [
                    "start_segment",
                    "end_segment",
                    "title",
                    "hook",
                    "reason",
                    "hook_strength",
                    "emotion",
                    "payoff",
                    "standalone",
                    "shareability",
                ],  # fmt: skip
                "additionalProperties": False,
            },
        }
    },
    "required": ["clips"],
    "additionalProperties": False,
}

RANK_SCHEMA = {
    "type": "object",
    "properties": {"ranking": {"type": "array", "items": {"type": "integer"}}},
    "required": ["ranking"],
    "additionalProperties": False,
}


class RatedClip(BaseModel):
    start_segment: int
    end_segment: int
    title: str
    hook: str
    reason: str
    hook_strength: int = Field(ge=0, le=10)
    emotion: int = Field(ge=0, le=10)
    payoff: int = Field(ge=0, le=10)
    standalone: int = Field(ge=0, le=10)
    shareability: int = Field(ge=0, le=10)

    def to_candidate(self) -> ClipCandidate:
        return ClipCandidate(
            start_segment=self.start_segment,
            end_segment=self.end_segment,
            # Models sometimes copy the prompt's loudness marker into their answer.
            title=_unmark(self.title),
            hook=_unmark(self.hook),
            reason=_unmark(self.reason),
            score=rubric_score(
                {
                    "hook": self.hook_strength,
                    "emotion": self.emotion,
                    "payoff": self.payoff,
                    "standalone": self.standalone,
                    "shareability": self.shareability,
                }
            ),
        )


class HighlightResponse(BaseModel):
    """Validates the LLM's reply against ``HIGHLIGHT_SCHEMA``."""

    clips: list[RatedClip]


class RankResponse(BaseModel):
    """Candidate numbers (1-based, as shown in the prompt), best first."""

    ranking: list[int]


def system_prompt(min_seconds: float, max_seconds: float) -> str:
    return SYSTEM_PROMPT.format(min_seconds=min_seconds, max_seconds=max_seconds, mark=ENERGY_MARK)


def user_prompt(window: list[Segment], loud: set[int] | None = None) -> str:
    loud = loud or set()
    lines = "\n".join(
        f"[{s.id}] {_clock(s.start)} {ENERGY_MARK + ' ' if s.id in loud else ''}{s.text}"
        for s in window
    )
    return USER_PROMPT.format(count=CLIPS_PER_WINDOW, transcript=lines, mark=ENERGY_MARK)


def rank_prompt(candidates: list[tuple[str, float, str]]) -> str:
    """``candidates``: (title, duration seconds, spoken text) in display order."""
    blocks = "\n\n".join(
        f'#{number} "{title}" ({duration:.0f}s)\n{_shorten(text)}'
        for number, (title, duration, text) in enumerate(candidates, start=1)
    )
    return RANK_USER_PROMPT.format(count=len(candidates), candidates=blocks)


def _unmark(text: str) -> str:
    return " ".join(text.replace(ENERGY_MARK, " ").split())


def _shorten(text: str, limit: int = 700) -> str:
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + " …"


def _clock(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes:02d}:{secs:02d}"
