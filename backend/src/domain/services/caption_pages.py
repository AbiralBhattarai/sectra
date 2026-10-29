"""Groups caption words into on-screen pages. Mirrors frontend/src/editor/captions.ts —
change both together, or the export won't match the preview."""

import re
from dataclasses import dataclass

from src.domain.enums.caption_style_enum import CaptionStyle
from src.domain.models.transcript import Word

#: Captions linger this long after their last word unless the next page starts.
HOLD_SECONDS = 0.3


@dataclass(frozen=True)
class _Rule:
    max_words: int
    max_gap: float
    break_after: re.Pattern[str]


_RULES = {
    CaptionStyle.BOLD_HIGHLIGHT: _Rule(3, 0.5, re.compile(r"[.?!,;:]$")),
    CaptionStyle.CLEAN: _Rule(7, 0.7, re.compile(r"[.?!]$")),
    CaptionStyle.BOXED: _Rule(7, 0.7, re.compile(r"[.?!]$")),
}


def paginate(words: list[Word], style: CaptionStyle) -> list[list[Word]]:
    if style is CaptionStyle.NONE:
        return []
    rule = _RULES[style]
    pages: list[list[Word]] = []
    current: list[Word] = []
    for word in words:
        if current and (
            len(current) >= rule.max_words or word.start - current[-1].end > rule.max_gap
        ):
            pages.append(current)
            current = []
        current.append(word)
        if rule.break_after.search(word.text):
            pages.append(current)
            current = []
    if current:
        pages.append(current)
    return pages


def hide_time(pages: list[list[Word]], index: int) -> float:
    """When page ``index`` leaves the screen (source time), as in the preview's ``pageAt``."""
    hold = pages[index][-1].end + HOLD_SECONDS
    return min(hold, pages[index + 1][0].start) if index + 1 < len(pages) else hold
