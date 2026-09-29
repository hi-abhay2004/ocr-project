"""
ai/rag/chunker.py (L6) — sentence/clause splitting and underline tagging.
"""

from ai.rag.chunker import chunk_text


def test_splits_on_sentence_boundaries():
    text = "BCNF is a normal form. It is stricter than 3NF. It removes redundancy."
    chunks = chunk_text(text)
    assert [c.text for c in chunks] == [
        "BCNF is a normal form.",
        "It is stricter than 3NF.",
        "It removes redundancy.",
    ]


def test_chunk_offsets_round_trip_into_the_source_text():
    text = "BCNF is a normal form. It is stricter than 3NF."
    for chunk in chunk_text(text):
        assert text[chunk.start : chunk.end] == chunk.text


def test_a_long_sentence_is_further_split_on_clauses():
    text = (
        "A relation is in BCNF if, for every non-trivial functional dependency, "
        "the determinant is a superkey, which is stricter than 3NF's own requirement."
    )
    chunks = chunk_text(text)
    assert len(chunks) > 1


def test_a_short_sentence_is_not_split_on_commas():
    text = "First, do this. Then, do that."
    chunks = chunk_text(text)
    assert len(chunks) == 2  # not split further just because each has a comma


def test_empty_text_yields_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_underlined_span_tags_the_overlapping_chunk():
    text = "BCNF is a normal form. It is stricter than 3NF."
    second_sentence_start = text.index("It is stricter")
    chunks = chunk_text(text, underlined_spans=((second_sentence_start, len(text)),))
    tagged = {c.text: c.underlined for c in chunks}
    assert tagged["BCNF is a normal form."] is False
    assert tagged["It is stricter than 3NF."] is True


def test_a_span_only_partially_overlapping_a_chunk_still_tags_it():
    text = "BCNF is a normal form. It is stricter than 3NF."
    # Span starts mid-word inside the second sentence.
    mid_point = text.index("stricter")
    chunks = chunk_text(text, underlined_spans=((mid_point, mid_point + 3),))
    tagged = {c.text: c.underlined for c in chunks}
    assert tagged["It is stricter than 3NF."] is True
    assert tagged["BCNF is a normal form."] is False
