"""Pure text handling for narrated stories: cleaning pasted text for speech, splitting
it into sentences for TTS and into chunks for the LLM rewrite."""

import re

#: Kokoro speaks a sentence at a time; longer ones are split at commas, then spaces.
MAX_SENTENCE_CHARS = 300
#: Words per LLM rewrite request: small enough that a 7B model doesn't summarise.
CHUNK_WORDS = 500
#: A rewrite must keep roughly this share of the words, or it's thrown away.
REWRITE_MIN_RATIO = 0.7
REWRITE_MAX_RATIO = 1.4
TITLE_MAX_CHARS = 80

_URL = re.compile(r"https?://\S+|www\.\S+")
_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_MARKUP = re.compile(r"[*_#>`~|]+")
_SPACES = re.compile(r"[ \t ]+")
#: Whitespace after an end mark, or after an end mark and a closing quote/bracket.
_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+|(?<=[.!?…][\"')\]”’])\s+")
_PARAGRAPHS = re.compile(r"\n\s*\n")


def clean_for_speech(text: str) -> str:
    """Drop markdown, links and stray markup; keep paragraph breaks as blank lines."""
    text = _MD_LINK.sub(r"\1", text)
    text = _URL.sub("", text)
    text = _MARKUP.sub(" ", text)
    paragraphs = []
    for paragraph in _PARAGRAPHS.split(text.replace("\r\n", "\n")):
        line = _SPACES.sub(" ", paragraph.replace("\n", " ")).strip()
        if line:
            paragraphs.append(line)
    return "\n\n".join(paragraphs)


def split_sentences(text: str, max_chars: int = MAX_SENTENCE_CHARS) -> list[str]:
    """Sentences in order, each at most ``max_chars`` (long ones split at commas, then
    at word boundaries)."""
    sentences: list[str] = []
    for paragraph in _PARAGRAPHS.split(text):
        for sentence in _SENTENCE_END.split(paragraph.replace("\n", " ").strip()):
            sentence = sentence.strip()
            if sentence:
                sentences += _fit(sentence, max_chars)
    return sentences


def _fit(sentence: str, max_chars: int) -> list[str]:
    if len(sentence) <= max_chars:
        return [sentence]
    parts: list[str] = []
    current = ""
    # Prefer commas/semicolons; fall back to words for comma-less run-ons.
    pieces = re.split(r"(?<=[,;:])\s+", sentence)
    if any(len(p) > max_chars for p in pieces):
        pieces = sentence.split()
    for piece in pieces:
        candidate = f"{current} {piece}".strip()
        if current and len(candidate) > max_chars:
            parts.append(current)
            current = piece
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts


def chunk_paragraphs(text: str, max_words: int = CHUNK_WORDS) -> list[str]:
    """Consecutive paragraphs grouped into chunks of about ``max_words`` words; a single
    longer paragraph is split at sentence ends."""
    chunks: list[str] = []
    current: list[str] = []
    count = 0
    for paragraph in _PARAGRAPHS.split(text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        pieces = [paragraph]
        if word_count(paragraph) > max_words:
            pieces = _group(_SENTENCE_END.split(paragraph), max_words)
        for piece in pieces:
            words = word_count(piece)
            if current and count + words > max_words:
                chunks.append("\n\n".join(current))
                current, count = [], 0
            current.append(piece)
            count += words
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def _group(sentences: list[str], max_words: int) -> list[str]:
    groups: list[str] = []
    current: list[str] = []
    count = 0
    for sentence in sentences:
        words = word_count(sentence)
        if current and count + words > max_words:
            groups.append(" ".join(current))
            current, count = [], 0
        current.append(sentence.strip())
        count += words
    if current:
        groups.append(" ".join(current))
    return groups


def word_count(text: str) -> int:
    return len(text.split())


def rewrite_ok(original: str, rewrite: str) -> bool:
    """A rewrite keeps the story when its length stays close to the original's (small
    models tend to summarise, or to ramble on)."""
    before, after = word_count(original), word_count(rewrite)
    if after == 0:
        return False
    return REWRITE_MIN_RATIO * before <= after <= REWRITE_MAX_RATIO * before


def default_title(text: str) -> str:
    """The first sentence, cut at a word boundary to ``TITLE_MAX_CHARS``."""
    sentences = split_sentences(text)
    first = sentences[0] if sentences else "Story"
    if len(first) <= TITLE_MAX_CHARS:
        return first
    cut = first[: TITLE_MAX_CHARS - 1].rsplit(" ", 1)[0]
    return f"{cut}…"


def default_caption(title: str) -> str:
    return f"{title} #storytime #fyp"
