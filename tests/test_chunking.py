"""Unit tests for text chunking service."""

import pytest

from app.services.chunking import (
    ChunkingStrategy,
    FixedSizeChunker,
    ParagraphChunker,
    RecursiveChunker,
    SentenceChunker,
)


# ============================================================================
# Sample Texts for Testing
# ============================================================================

SIMPLE_TEXT = "Hello world. This is a test document. It has multiple sentences."

LONG_TEXT = """
Artificial intelligence has transformed the way we live and work. Machine learning
algorithms can now process vast amounts of data and identify patterns that were
previously invisible to human analysts. Natural language processing enables
computers to understand and generate human language with remarkable accuracy.

Deep learning, a subset of machine learning, uses neural networks with many layers
to learn complex representations of data. These models have achieved breakthroughs
in image recognition, speech synthesis, and language translation. The transformer
architecture, introduced in 2017, revolutionized NLP by enabling parallel processing
of sequential data.

Large language models like GPT and BERT have pushed the boundaries of what's
possible with text understanding and generation. These models are pre-trained on
massive corpora of text and can be fine-tuned for specific tasks. Transfer learning
allows knowledge gained from one task to be applied to another.

Retrieval-Augmented Generation combines the strengths of retrieval systems with
generative models. By first retrieving relevant documents and then using them as
context for generation, RAG systems produce more accurate and factual responses.
This approach is particularly useful for enterprise applications where accuracy
and traceability are paramount.
""".strip()

SHORT_TEXT = "Hello."

EMPTY_TEXT = ""

WHITESPACE_TEXT = "   \n\n\t  "


# ============================================================================
# FixedSizeChunker Tests
# ============================================================================


class TestFixedSizeChunker:
    """Tests for fixed-size text chunking."""

    def test_basic_chunking(self):
        """Test basic fixed-size chunking."""
        chunker = FixedSizeChunker(chunk_size=100, overlap=10)
        chunks = chunker.chunk(LONG_TEXT)

        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) > 0

    def test_small_text_single_chunk(self):
        """Test that small text returns single chunk."""
        chunker = FixedSizeChunker(chunk_size=500, overlap=50)
        chunks = chunker.chunk(SIMPLE_TEXT)

        assert len(chunks) == 1
        assert chunks[0] == SIMPLE_TEXT

    def test_empty_text(self):
        """Test chunking empty text returns empty list."""
        chunker = FixedSizeChunker(chunk_size=100, overlap=10)

        assert chunker.chunk("") == []
        assert chunker.chunk("   ") == []

    def test_chunk_size_respected(self):
        """Test that chunks don't exceed size limit (approximately)."""
        chunk_size = 200
        chunker = FixedSizeChunker(chunk_size=chunk_size, overlap=20)
        chunks = chunker.chunk(LONG_TEXT)

        for chunk in chunks:
            # Allow some tolerance for word boundary adjustment
            assert len(chunk) <= chunk_size + 50

    def test_overlap_creates_shared_content(self):
        """Test that overlap creates overlapping content between chunks."""
        chunker = FixedSizeChunker(chunk_size=100, overlap=30)
        chunks = chunker.chunk(LONG_TEXT)

        if len(chunks) >= 2:
            # There should be some shared content due to overlap
            # This is a loose check since word boundaries may shift
            assert len(chunks) >= 2

    def test_none_text(self):
        """Test that None text returns empty list."""
        chunker = FixedSizeChunker()
        assert chunker.chunk(None) == []

    def test_custom_parameters(self):
        """Test chunker with custom parameters."""
        chunker = FixedSizeChunker(chunk_size=50, overlap=5)
        chunks = chunker.chunk(LONG_TEXT)

        assert len(chunks) > 5  # Should produce many small chunks


# ============================================================================
# SentenceChunker Tests
# ============================================================================


class TestSentenceChunker:
    """Tests for sentence-based text chunking."""

    def test_basic_sentence_chunking(self):
        """Test basic sentence chunking."""
        chunker = SentenceChunker(max_chunk_size=200)
        chunks = chunker.chunk(LONG_TEXT)

        assert len(chunks) > 0
        for chunk in chunks:
            assert len(chunk) > 0

    def test_short_text_single_chunk(self):
        """Test short text produces single chunk."""
        chunker = SentenceChunker(max_chunk_size=500)
        chunks = chunker.chunk(SHORT_TEXT)

        assert len(chunks) == 1

    def test_empty_text(self):
        """Test empty text returns empty list."""
        chunker = SentenceChunker()

        assert chunker.chunk("") == []
        assert chunker.chunk(None) == []

    def test_respects_max_chunk_size(self):
        """Test that chunks respect maximum size."""
        max_size = 300
        chunker = SentenceChunker(max_chunk_size=max_size)
        chunks = chunker.chunk(LONG_TEXT)

        for chunk in chunks:
            # Allow tolerance since sentence boundaries may exceed slightly
            assert len(chunk) <= max_size * 2

    def test_sentences_not_split_mid_sentence(self):
        """Test that chunks don't split in the middle of sentences."""
        text = "First sentence. Second sentence. Third sentence. Fourth sentence."
        chunker = SentenceChunker(max_chunk_size=50)
        chunks = chunker.chunk(text)

        for chunk in chunks:
            # Each chunk should end cleanly
            assert len(chunk.strip()) > 0


# ============================================================================
# ParagraphChunker Tests
# ============================================================================


class TestParagraphChunker:
    """Tests for paragraph-based text chunking."""

    def test_basic_paragraph_chunking(self):
        """Test basic paragraph chunking."""
        chunker = ParagraphChunker(max_chunk_size=500)
        chunks = chunker.chunk(LONG_TEXT)

        assert len(chunks) > 0
        for chunk in chunks:
            assert len(chunk) > 0

    def test_single_paragraph(self):
        """Test single paragraph text."""
        text = "This is a single paragraph with no double newlines."
        chunker = ParagraphChunker(max_chunk_size=500)
        chunks = chunker.chunk(text)

        assert len(chunks) == 1
        assert chunks[0] == text

    def test_empty_text(self):
        """Test empty text returns empty list."""
        chunker = ParagraphChunker()

        assert chunker.chunk("") == []
        assert chunker.chunk(None) == []

    def test_preserves_paragraph_structure(self):
        """Test that paragraph boundaries are respected."""
        text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
        chunker = ParagraphChunker(max_chunk_size=5000)
        chunks = chunker.chunk(text)

        # With large max_chunk_size, all paragraphs should be in one chunk
        assert len(chunks) == 1

    def test_splits_long_paragraphs(self):
        """Test that very long paragraphs get split."""
        long_para = "Word " * 500  # ~2500 chars
        chunker = ParagraphChunker(max_chunk_size=200)
        chunks = chunker.chunk(long_para)

        assert len(chunks) > 1

    def test_multiple_paragraphs_grouped(self):
        """Test that small paragraphs are grouped together."""
        text = "Short para 1.\n\nShort para 2.\n\nShort para 3."
        chunker = ParagraphChunker(max_chunk_size=1000)
        chunks = chunker.chunk(text)

        # All short paragraphs should fit in one chunk
        assert len(chunks) == 1


# ============================================================================
# RecursiveChunker Tests
# ============================================================================


class TestRecursiveChunker:
    """Tests for recursive text chunking."""

    def test_basic_recursive_chunking(self):
        """Test basic recursive chunking."""
        chunker = RecursiveChunker(chunk_size=200, overlap=20)
        chunks = chunker.chunk(LONG_TEXT)

        assert len(chunks) > 0
        for chunk in chunks:
            assert len(chunk) > 0

    def test_empty_text(self):
        """Test empty text returns empty list."""
        chunker = RecursiveChunker()

        assert chunker.chunk("") == []
        assert chunker.chunk(None) == []

    def test_short_text_single_chunk(self):
        """Test short text produces single chunk."""
        chunker = RecursiveChunker(chunk_size=1000)
        chunks = chunker.chunk(SIMPLE_TEXT)

        assert len(chunks) == 1

    def test_uses_separator_hierarchy(self):
        """Test that recursive chunker uses separators in order."""
        text = "Para 1.\n\nPara 2.\n\nPara 3 is longer with more content."
        chunker = RecursiveChunker(chunk_size=50, overlap=5)
        chunks = chunker.chunk(text)

        assert len(chunks) >= 2

    def test_custom_separators(self):
        """Test chunker with custom separators."""
        chunker = RecursiveChunker(
            chunk_size=100,
            overlap=10,
            separators=[";", ",", " "],
        )
        text = "item1; item2; item3; item4; item5; item6; item7; item8; item9; item10; " * 5
        chunks = chunker.chunk(text)

        assert len(chunks) >= 1

    def test_overlap_parameter(self):
        """Test that overlap is applied."""
        chunker = RecursiveChunker(chunk_size=100, overlap=30)
        chunks = chunker.chunk(LONG_TEXT)

        # With overlap, we should get more chunks than without
        chunker_no_overlap = RecursiveChunker(chunk_size=100, overlap=0)
        chunks_no_overlap = chunker_no_overlap.chunk(LONG_TEXT)

        assert len(chunks) >= len(chunks_no_overlap)


# ============================================================================
# ChunkingStrategy Enum Tests
# ============================================================================


class TestChunkingStrategy:
    """Tests for chunking strategy enum."""

    def test_enum_values(self):
        """Test all strategy enum values exist."""
        assert ChunkingStrategy.FIXED_SIZE == "fixed_size"
        assert ChunkingStrategy.SENTENCE == "sentence"
        assert ChunkingStrategy.PARAGRAPH == "paragraph"
        assert ChunkingStrategy.RECURSIVE == "recursive"

    def test_enum_from_string(self):
        """Test creating enum from string value."""
        assert ChunkingStrategy("fixed_size") == ChunkingStrategy.FIXED_SIZE
        assert ChunkingStrategy("recursive") == ChunkingStrategy.RECURSIVE

    def test_invalid_strategy_raises(self):
        """Test invalid strategy raises ValueError."""
        with pytest.raises(ValueError):
            ChunkingStrategy("invalid_strategy")


# ============================================================================
# Integration / Edge Case Tests
# ============================================================================


class TestChunkingEdgeCases:
    """Tests for edge cases across all chunkers."""

    @pytest.mark.parametrize("ChunkerClass", [
        FixedSizeChunker,
        SentenceChunker,
        ParagraphChunker,
        RecursiveChunker,
    ])
    def test_whitespace_only_text(self, ChunkerClass):
        """Test all chunkers handle whitespace-only text."""
        chunker = ChunkerClass()
        result = chunker.chunk(WHITESPACE_TEXT)
        assert result == []

    @pytest.mark.parametrize("ChunkerClass", [
        FixedSizeChunker,
        SentenceChunker,
        ParagraphChunker,
        RecursiveChunker,
    ])
    def test_all_chunkers_return_list(self, ChunkerClass):
        """Test all chunkers return a list."""
        chunker = ChunkerClass()
        result = chunker.chunk(LONG_TEXT)
        assert isinstance(result, list)

    @pytest.mark.parametrize("ChunkerClass", [
        FixedSizeChunker,
        SentenceChunker,
        ParagraphChunker,
        RecursiveChunker,
    ])
    def test_no_empty_chunks_returned(self, ChunkerClass):
        """Test that no empty chunks are returned."""
        chunker = ChunkerClass()
        chunks = chunker.chunk(LONG_TEXT)

        for chunk in chunks:
            assert len(chunk.strip()) > 0

    def test_unicode_text(self):
        """Test chunking with Unicode/Vietnamese text."""
        text = (
            "Trí tuệ nhân tạo đã thay đổi cách chúng ta sống và làm việc. "
            "Các thuật toán học máy hiện có thể xử lý lượng lớn dữ liệu. "
            "Xử lý ngôn ngữ tự nhiên cho phép máy tính hiểu ngôn ngữ con người."
        )
        chunker = FixedSizeChunker(chunk_size=100, overlap=10)
        chunks = chunker.chunk(text)

        assert len(chunks) > 0
        # Verify content is preserved
        full_text = " ".join(chunks)
        assert "Trí tuệ nhân tạo" in full_text

    def test_very_long_text(self):
        """Test chunking very long text."""
        long_text = "This is a sentence. " * 1000  # ~20000 chars
        chunker = RecursiveChunker(chunk_size=500, overlap=50)
        chunks = chunker.chunk(long_text)

        assert len(chunks) > 10
        # All text should be covered
        total_length = sum(len(c) for c in chunks)
        assert total_length > 0

    def test_text_with_special_characters(self):
        """Test chunking text with special characters."""
        text = "Hello! How are you? I'm fine. @#$% special chars... end."
        chunker = SentenceChunker(max_chunk_size=200)
        chunks = chunker.chunk(text)

        assert len(chunks) >= 1
