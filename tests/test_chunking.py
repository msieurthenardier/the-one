"""Tests for the deterministic chunker (M24 F02 L03, DD-7, AC-7).

No ``hypothesis`` in the dev extra — the corpus-wide invariant sweep uses a
``random.Random(seed)``-generated corpus instead, mixing paragraph lengths,
long unbroken lines, CRLF, and unicode, per the leg spec's stated approach.
"""

from __future__ import annotations

import random

import pytest

from the_one.db._kb_types import ChunkRecord
from the_one.knowledge.chunking import chunk_text

SEED = 20260914
CORPUS_SIZE = 200


def _generate_corpus(seed: int, n: int) -> list[str]:
    rng = random.Random(seed)
    words = [
        "alpha",
        "bravo",
        "charlie",
        "delta",
        "echo",
        "foxtrot",
        "golf",
        "hotel",
        "café",
        "naïve",
        "日本語",
        "emoji😀test",
        "zürich",
    ]
    texts: list[str] = []
    for _ in range(n):
        kind = rng.choice(["paragraphs", "long_line", "mixed", "crlf"])
        if kind == "paragraphs":
            paragraphs = []
            for _ in range(rng.randint(1, 8)):
                sentence_count = rng.randint(1, 6)
                sentences = []
                for _ in range(sentence_count):
                    word_count = rng.randint(3, 20)
                    sentence = " ".join(rng.choice(words) for _ in range(word_count))
                    terminator = rng.choice([".", "!", "?"])
                    sentences.append(sentence + terminator)
                paragraphs.append(" ".join(sentences))
            text = "\n\n".join(paragraphs)
        elif kind == "long_line":
            # A long unbroken run with no spaces at all — forces hard splits.
            length = rng.randint(1500, 6000)
            text = "".join(rng.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(length))
        elif kind == "crlf":
            lines = []
            for _ in range(rng.randint(2, 30)):
                word_count = rng.randint(1, 12)
                lines.append(" ".join(rng.choice(words) for _ in range(word_count)))
            text = "\r\n".join(lines)
            if rng.random() < 0.5:
                text += "\r\n\r\n" + "\r\n".join(lines[:3])
        else:  # mixed
            parts = []
            for _ in range(rng.randint(2, 5)):
                sub_kind = rng.choice(["paragraph", "long_line"])
                if sub_kind == "paragraph":
                    word_count = rng.randint(10, 200)
                    parts.append(" ".join(rng.choice(words) for _ in range(word_count)) + ".")
                else:
                    length = rng.randint(200, 1200)
                    parts.append("".join(rng.choice("xyzXYZ") for _ in range(length)))
            text = "\n\n".join(parts)
        # Occasionally add leading/trailing whitespace to exercise stripping.
        if rng.random() < 0.3:
            text = "  \n" + text + "\n\t  "
        texts.append(text)
    return texts


CORPUS = _generate_corpus(SEED, CORPUS_SIZE)


class TestChunkTextInvariants:
    @pytest.mark.parametrize("text", CORPUS, ids=range(len(CORPUS)))
    def test_invariants_hold(self, text: str) -> None:
        size_chars, overlap_chars = 1000, 150
        chunks = chunk_text(text, size_chars=size_chars, overlap_chars=overlap_chars)

        # Offsets are exact.
        for chunk in chunks:
            assert text[chunk.char_start : chunk.char_end] == chunk.text

        # Length cap: every chunk is <= size_chars.
        for chunk in chunks:
            assert len(chunk.text) <= size_chars

        # seq is 0..n-1 contiguous.
        assert [c.seq for c in chunks] == list(range(len(chunks)))

        # No chunk is whitespace-only (would have been skipped).
        for chunk in chunks:
            assert chunk.text.strip() != ""

        # Overlap window between consecutive chunks.
        for prev, nxt in zip(chunks, chunks[1:]):
            overlap = prev.char_end - nxt.char_start
            assert overlap <= overlap_chars
            if len(prev.text) == size_chars:
                assert overlap >= 1

    def test_determinism(self) -> None:
        for text in CORPUS[:20]:
            first = chunk_text(text)
            second = chunk_text(text)
            assert first == second


class TestChunkTextEdgeCases:
    def test_empty_text_yields_no_chunks(self) -> None:
        assert chunk_text("") == []

    def test_whitespace_only_text_yields_no_chunks(self) -> None:
        assert chunk_text("   \n\t\n  ") == []

    def test_defaults_are_1000_and_150(self) -> None:
        text = "word " * 5000
        chunks = chunk_text(text)
        for chunk in chunks:
            assert len(chunk.text) <= 1000
        for prev, nxt in zip(chunks, chunks[1:]):
            assert prev.char_end - nxt.char_start <= 150

    def test_single_unbreakable_run_hard_splits_at_size_chars(self) -> None:
        text = "x" * 5000
        chunks = chunk_text(text, size_chars=1000, overlap_chars=150)
        assert len(chunks) > 1
        for chunk in chunks[:-1]:
            assert len(chunk.text) == 1000

    def test_hard_split_overlap_is_exact_character_fallback(self) -> None:
        text = "x" * 5000
        chunks = chunk_text(text, size_chars=1000, overlap_chars=150)
        for prev, nxt in zip(chunks, chunks[1:]):
            assert prev.char_end - nxt.char_start == 150

    def test_short_text_yields_single_chunk(self) -> None:
        text = "A short sentence that fits in one chunk."
        chunks = chunk_text(text)
        assert len(chunks) == 1
        assert chunks[0].text == text
        assert chunks[0].seq == 0
        assert chunks[0].char_start == 0
        assert chunks[0].char_end == len(text)

    def test_leading_and_trailing_whitespace_is_stripped_with_offsets_adjusted(self) -> None:
        inner = "Some real content here."
        text = "   \n\t" + inner + "\n\n  "
        chunks = chunk_text(text)
        assert len(chunks) == 1
        assert chunks[0].text == inner
        assert text[chunks[0].char_start : chunks[0].char_end] == inner

    def test_paragraph_boundary_preferred_over_hard_split(self) -> None:
        first_paragraph = "word " * 190  # ~950 chars, fits under size_chars=1000
        second_paragraph = "more words here to fill the next chunk nicely, plenty more content."
        text = first_paragraph.strip() + "\n\n" + second_paragraph * 5
        chunks = chunk_text(text, size_chars=1000, overlap_chars=150)
        # The first chunk should end at (or before) the paragraph boundary,
        # not spill a hard-split fragment of the second paragraph in.
        assert chunks[0].text == first_paragraph.strip()

    def test_crlf_text_offsets_are_exact(self) -> None:
        text = "line one\r\nline two\r\n\r\nline three\r\nline four"
        chunks = chunk_text(text, size_chars=1000, overlap_chars=150)
        for chunk in chunks:
            assert text[chunk.char_start : chunk.char_end] == chunk.text

    def test_returns_chunk_record_instances(self) -> None:
        chunks = chunk_text("hello world")
        assert len(chunks) == 1
        assert isinstance(chunks[0], ChunkRecord)

    def test_unicode_offsets_are_exact(self) -> None:
        text = "日本語のテキストです。" * 100 + "\n\n" + "café naïve zürich 😀 " * 50
        chunks = chunk_text(text, size_chars=500, overlap_chars=100)
        for chunk in chunks:
            assert text[chunk.char_start : chunk.char_end] == chunk.text
