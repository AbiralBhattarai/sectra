"""Prompts for narrated stories, shaped for small local models (7B): the rewrite is plain
text in short chunks, and the structured answers are tiny schema-checked JSON."""

from pydantic import BaseModel, Field

from src.domain.enums.emotion_enum import Emotion
from src.domain.models.transcript import Segment

POLISH_SYSTEM = """You adapt stories so they sound great read aloud in a short vertical video \
(TikTok, YouTube Shorts, Reels). Rewrite the passage you are given:
- Keep every plot point, name, number and the narrator's point of view (usually "I").
- Keep about the same length. Never summarise, never add new events.
- Use short, punchy, spoken sentences.
- Remove Reddit leftovers such as "EDIT:", "UPDATE:", "TL;DR", throwaway notes and \
formatting.
- Spell abbreviations out the way a narrator would say them: AITA -> "am I the a-hole", \
MIL -> "mother-in-law", BF -> "boyfriend", 20F -> "twenty-year-old woman".
- No markdown, no emoji, no hashtags, no headings, no quotation of these rules.
Reply with the rewritten passage only."""

POLISH_FIRST = "This is the start of the story: open with one gripping hook sentence."
POLISH_MIDDLE = "This passage continues a story: do not add an introduction."

META_SYSTEM = """You write the title and the post caption for a narrated story video.
- title: at most 70 characters, a curiosity hook, no hashtags, no emoji.
- caption: one short hook line followed by 3-5 relevant hashtags (always include \
#storytime).
Reply with JSON only."""

META_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "caption": {"type": "string"},
    },
    "required": ["title", "caption"],
}

MOODS_SYSTEM = """You direct a cartoon narrator who reads a story aloud. For each numbered \
line of the narration, choose the narrator's facial expression while saying it: one of \
neutral, happy, sad, angry, shocked, smug. Most lines are neutral; use the others only where \
the feeling is clear (a twist -> shocked, a petty win -> smug, a loss -> sad).
Reply with JSON only: {"moods": [{"line": <number>, "emotion": "<expression>"}, ...]}, \
listing only lines that are not neutral."""

MOODS_SCHEMA = {
    "type": "object",
    "properties": {
        "moods": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "line": {"type": "integer"},
                    "emotion": {"type": "string", "enum": [e.value for e in Emotion]},
                },
                "required": ["line", "emotion"],
            },
        }
    },
    "required": ["moods"],
}

#: Characters of the story shown to the title/caption request (fits a 4k context).
META_INPUT_CHARS = 4_000


class StoryMeta(BaseModel):
    title: str = Field(min_length=1)
    caption: str = ""


class LineMood(BaseModel):
    line: int
    emotion: Emotion


class MoodsResponse(BaseModel):
    moods: list[LineMood]


def polish_prompt(chunk: str, first: bool) -> str:
    return f"{POLISH_FIRST if first else POLISH_MIDDLE}\n\nPassage:\n{chunk}"


def meta_prompt(story: str) -> str:
    return f"Story:\n{story[:META_INPUT_CHARS]}"


def moods_prompt(segments: list[Segment]) -> str:
    return "Narration:\n" + "\n".join(f"[{s.id}] {s.text.strip()}" for s in segments)
