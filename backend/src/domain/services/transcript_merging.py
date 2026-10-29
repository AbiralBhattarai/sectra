from collections import Counter

from src.domain.models.speech import TimeSpan
from src.domain.models.transcript import Segment, Transcript, Word


def merge_chunk_transcripts(
    parts: list[tuple[TimeSpan, Transcript]], speech: list[TimeSpan]
) -> Transcript:
    """Combine per-chunk transcripts (timestamps relative to their chunk) into one
    transcript on the source timeline, with segment ids renumbered in time order.

    Whisper stamps a chunk's first word from the very start of the audio it was
    given, swallowing the leading silence; that word is moved to where the VAD
    heard speech begin, so captions don't appear early."""
    segments: list[Segment] = []
    languages: Counter[str] = Counter()

    for chunk, transcript in sorted(parts, key=lambda part: part[0].start):
        if transcript.language and transcript.segments:
            languages[transcript.language] += len(transcript.segments)
        onset = next((s.start for s in speech if chunk.start <= s.start < chunk.end), None)
        first_word = True
        for segment in transcript.segments:
            words = [_shift_word(word, chunk) for word in segment.words if word.text.strip()]
            if words and first_word:
                first_word = False
                if onset is not None and words[0].start < onset < words[0].end:
                    words[0] = words[0].model_copy(update={"start": onset})
            segments.append(
                Segment(
                    id=len(segments),
                    start=_clamp(segment.start + chunk.start, chunk),
                    end=_clamp(segment.end + chunk.start, chunk),
                    text=segment.text.strip(),
                    words=words,
                )
            )

    language = languages.most_common(1)[0][0] if languages else None
    return Transcript(language=language, segments=segments)


def _shift_word(word: Word, chunk: TimeSpan) -> Word:
    return Word(
        text=word.text.strip(),
        start=_clamp(word.start + chunk.start, chunk),
        end=_clamp(word.end + chunk.start, chunk),
        probability=word.probability,
    )


def _clamp(seconds: float, chunk: TimeSpan) -> float:
    """Engines sometimes stamp a word a hair past the audio they were given."""
    return round(min(max(seconds, chunk.start), chunk.end), 3)
