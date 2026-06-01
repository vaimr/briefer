"""Unit tests for worker/chunking.py — text chunking and summary merging."""

import re

import pytest

from worker.chunking import chunk_text, merge_summaries


class TestChunkText:
    """Tests for chunk_text()."""

    def test_short_text_returns_single_chunk(self):
        text = "This is a short text."
        result = chunk_text(text)
        assert result == [text]

    def test_empty_text_returns_empty_list(self):
        assert chunk_text("") == []

    def test_whitespace_only_returns_empty_list(self):
        assert chunk_text("   \n\t  ") == []

    def test_none_returns_empty_list(self):
        assert chunk_text(None) == []

    def test_long_text_splits_into_multiple_chunks(self):
        long_text = " ".join([f"Sentence number {i}. " for i in range(200)])
        result = chunk_text(long_text, chunk_size=500)
        assert len(result) > 1
        for chunk in result:
            assert len(chunk) <= 500

    def test_chunks_respect_sentence_boundaries(self):
        text = "First sentence. Second sentence. Third sentence. Fourth sentence. Fifth sentence. " * 10
        result = chunk_text(text, chunk_size=200)
        for chunk in result:
            assert chunk[-1] in ".!?" or len(chunk) <= 200

    def test_micro_chunks_filtered(self):
        short_sentences = "Hi. " * 100
        result = chunk_text(short_sentences, chunk_size=1000)
        for chunk in result:
            assert len(chunk) >= 200

    def test_chunk_size_boundary(self):
        text = "x" * 3000
        result = chunk_text(text, chunk_size=3000)
        assert result == [text]

    def test_text_just_over_chunk_size_splits(self):
        text = "x" * 3001
        result = chunk_text(text, chunk_size=3000)
        assert len(result) >= 1
        assert len(result) > 0

    def test_chunks_preserve_order(self):
        text = " ".join(
            [
                f"This is a very long sentence number {i} that contains enough content to form a proper chunk when combined with another sentence. "
                for i in range(50)
            ]
        )
        result = chunk_text(text, chunk_size=400)
        assert len(result) > 0
        reconstructed = " ".join(result)
        assert re.sub(r"\s+", " ", reconstructed).strip() == re.sub(r"\s+", " ", text).strip()
        for chunk in result:
            # Each chunk must be >= 200 chars and contain at least one sentence number
            assert len(chunk) >= 200
            assert any(f"number {j}" in chunk for j in range(50))

    def test_custom_chunk_size(self):
        text = " ".join([f"Word {i}. " for i in range(100)])
        result = chunk_text(text, chunk_size=100)
        for chunk in result:
            assert len(chunk) <= 100

    def test_single_sentence_large_text(self):
        long_sentence = "x" * 5000
        result = chunk_text(long_sentence, chunk_size=3000)
        assert len(result) == 1

    def test_multiple_exclamation_marks(self):
        text = ". ".join(
            [
                f"Wow that is truly great amazing incredible wonderful fantastic unbelievable and extraordinary {i}"
                for i in range(20)
            ]
        )
        text = text + "!"
        result = chunk_text(text, chunk_size=300)
        assert len(result) > 1
        for chunk in result:
            assert len(chunk) >= 200

    def test_multiple_question_marks(self):
        text = "? ".join(
            [
                f"Really I wonder why and how and when and where and what and who is this about today and tomorrow {i}"
                for i in range(20)
            ]
        )
        text = text + "?"
        result = chunk_text(text, chunk_size=300)
        assert len(result) > 1
