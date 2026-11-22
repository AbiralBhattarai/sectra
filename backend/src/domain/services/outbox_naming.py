"""File names for the outbox: the clip's rank and social caption, made safe for every
filesystem the folder may be opened on (Windows is the strictest)."""

import re

#: Characters Windows forbids in file names, plus control characters.
_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
#: Leaves room for the rank, a collision suffix and the extension under 255.
MAX_STEM = 120


def outbox_stem(rank: int, caption: str, fallback: str = "clip") -> str:
    """``"07 The caption text"``: the rank zero-padded so the folder sorts best first."""
    text = " ".join(_FORBIDDEN.sub(" ", caption).split()) or " ".join(fallback.split()) or "clip"
    stem = f"{rank:02d} {text}"
    if len(stem) > MAX_STEM:
        stem = stem[:MAX_STEM].rsplit(" ", 1)[0]
    # Windows drops trailing dots and spaces, so a name ending in them can't be reopened.
    return stem.rstrip(". ") or f"{rank:02d}"


def post_description(title: str, extra: str = "") -> str:
    """What the Post button posts: the clip's title, then the user's own text (hashtags,
    a credit…) after a space. ``"Betrayal and Confrontation" + "#lacy"`` →
    ``"Betrayal and Confrontation #lacy"``."""
    return " ".join(part for part in (title.strip(), extra.strip()) if part)


def unique_stem(stem: str, taken: set[str]) -> str:
    """``stem``, or ``stem (2)``, ``stem (3)``… — the first not in ``taken``."""
    if stem not in taken:
        return stem
    number = 2
    while f"{stem} ({number})" in taken:
        number += 1
    return f"{stem} ({number})"


def folder_name(title: str) -> str:
    """The video's folder in the outbox."""
    return " ".join(_FORBIDDEN.sub(" ", title).split())[:80].rstrip(". ") or "video"
