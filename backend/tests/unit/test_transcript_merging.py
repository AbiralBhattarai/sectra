from src.domain.models.speech import TimeSpan
from src.domain.models.transcript import Segment, Transcript, Word
from src.domain.services.transcript_merging import merge_chunk_transcripts


def transcript(language, *segments):
    return Transcript(language=language, segments=list(segments))


def segment(start, end, text, words):
    return Segment(id=0, start=start, end=end, text=text, words=words)


def test_offsets_renumbers_and_orders_chunks():
    late = transcript("en", segment(0.5, 2.0, " world", [Word(text=" world", start=0.5, end=2.0)]))
    early = transcript("en", segment(0.0, 1.0, " Hello", [Word(text=" Hello", start=0.1, end=0.9)]))

    merged = merge_chunk_transcripts(
        [(TimeSpan(start=30, end=40), late), (TimeSpan(start=5, end=10), early)], speech=[]
    )

    assert [(s.id, s.start, s.end, s.text) for s in merged.segments] == [
        (0, 5.0, 6.0, "Hello"),
        (1, 30.5, 32.0, "world"),
    ]
    assert [(w.text, w.start, w.end) for w in merged.segments[1].words] == [("world", 30.5, 32.0)]
    assert merged.language == "en"


def test_timestamps_past_the_chunk_are_clamped():
    part = transcript("en", segment(0, 12, "x", [Word(text="x", start=9.5, end=12)]))
    merged = merge_chunk_transcripts([(TimeSpan(start=100, end=110), part)], speech=[])
    assert merged.segments[0].end == 110
    assert merged.segments[0].words[0].end == 110


def test_language_is_the_majority_and_blank_words_are_dropped():
    a = transcript(
        "en", segment(0, 1, "a", [Word(text=" ", start=0, end=0.1)]), segment(1, 2, "b", [])
    )
    b = transcript("de", segment(0, 1, "c", []))
    merged = merge_chunk_transcripts(
        [(TimeSpan(start=0, end=5), a), (TimeSpan(start=5, end=10), b)], speech=[]
    )
    assert merged.language == "en"
    assert merged.segments[0].words == []


def test_nothing_to_merge():
    assert merge_chunk_transcripts([], speech=[]) == Transcript(language=None, segments=[])


def test_first_word_of_a_chunk_starts_at_the_speech_onset():
    words = [Word(text="The", start=0.0, end=0.68), Word(text="quick", start=0.68, end=0.92)]
    part = transcript("en", segment(0.0, 0.92, "The quick", words))

    merged = merge_chunk_transcripts(
        [(TimeSpan(start=9.8, end=12.2), part)], speech=[TimeSpan(start=10.0, end=12.0)]
    )

    assert [(w.start, w.end) for w in merged.segments[0].words] == [(10.0, 10.48), (10.48, 10.72)]


def test_onset_outside_the_first_word_is_left_alone():
    words = [Word(text="Hi", start=0.3, end=0.6)]
    part = transcript("en", segment(0.3, 0.6, "Hi", words))
    merged = merge_chunk_transcripts(
        [(TimeSpan(start=9.8, end=12.2), part)], speech=[TimeSpan(start=10.0, end=12.0)]
    )
    assert merged.segments[0].words[0].start == 10.1
