from src.domain.services.story_text import (
    chunk_paragraphs,
    clean_for_speech,
    default_caption,
    default_title,
    rewrite_ok,
    split_sentences,
)


def test_clean_drops_markdown_links_and_keeps_paragraphs():
    text = "**AITA** for [this](https://x.com)?\r\n\r\n# Edit\nSee https://reddit.com/r/x  now."
    assert clean_for_speech(text) == "AITA for this?\n\nEdit See now."


def test_sentences_split_on_end_marks_and_paragraphs():
    text = 'I said "no." She left! Why?\n\nThe end'
    assert split_sentences(text) == ['I said "no."', "She left!", "Why?", "The end"]


def test_long_sentences_split_at_commas_then_words():
    sentence = ", ".join([" ".join(["word"] * 10)] * 4)
    parts = split_sentences(sentence, max_chars=120)
    assert all(len(p) <= 120 for p in parts)
    assert " ".join(parts) == sentence

    run_on = "a" * 50 + " " + "b" * 50 + " " + "c" * 50
    assert split_sentences(run_on, max_chars=110) == ["a" * 50 + " " + "b" * 50, "c" * 50]


def test_chunks_group_paragraphs_up_to_the_word_budget():
    paragraphs = [" ".join(["w"] * 200) for _ in range(5)]
    chunks = chunk_paragraphs("\n\n".join(paragraphs), max_words=500)
    assert [len(c.split()) for c in chunks] == [400, 400, 200]


def test_one_huge_paragraph_is_split_at_sentence_ends():
    paragraph = " ".join(["Short sentence here."] * 300)  # 900 words
    chunks = chunk_paragraphs(paragraph, max_words=500)
    assert len(chunks) == 2
    assert all(c.endswith(".") for c in chunks)
    assert sum(len(c.split()) for c in chunks) == 900


def test_rewrite_must_keep_roughly_the_same_length():
    original = " ".join(["word"] * 100)
    assert rewrite_ok(original, " ".join(["word"] * 80))
    assert not rewrite_ok(original, " ".join(["word"] * 50))  # summarised
    assert not rewrite_ok(original, " ".join(["word"] * 200))  # rambled
    assert not rewrite_ok(original, "")


def test_default_title_is_the_first_sentence_cut_at_a_word():
    assert default_title("My sister stole my wedding. Then...") == "My sister stole my wedding."
    long = "word " * 40
    title = default_title(long)
    assert len(title) <= 80 and title.endswith("…") and " wor…" not in title
    assert default_caption("Hi") == "Hi #storytime #fyp"
