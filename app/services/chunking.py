"""Text chunking strategies for document processing."""

import logging
import re
from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class ChunkingStrategy(str, Enum):
    """Available chunking strategies."""

    FIXED_SIZE = "fixed_size"
    SENTENCE = "sentence"
    PARAGRAPH = "paragraph"
    RECURSIVE = "recursive"


class BaseChunker(ABC):
    """Base class for text chunkers."""

    @abstractmethod
    def chunk(self, text: str) -> list[str]:
        """Split text into chunks."""
        pass


class FixedSizeChunker(BaseChunker):
    """Chunk text by fixed character count with overlap."""

    def __init__(
        self,
        chunk_size: int = 500,
        overlap: int = 50,
    ):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, text: str) -> list[str]:
        """Split text into fixed-size chunks with overlap.

        Args:
            text: Text to chunk

        Returns:
            List of text chunks
        """
        if not text or not text.strip():
            return []

        text = text.strip()
        chunks = []
        start = 0

        while start < len(text):
            end = start + self.chunk_size

            # Try to break at word boundary
            if end < len(text):
                # Look for space within last 50 chars
                last_space = text.rfind(" ", start + self.chunk_size - 50, end)
                if last_space > start:
                    end = last_space

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)

            # Move start position with overlap
            start = end - self.overlap
            if start >= len(text) - self.overlap:
                break

        return chunks


class SentenceChunker(BaseChunker):
    """Chunk text by sentences, grouping to target size."""

    def __init__(
        self,
        max_chunk_size: int = 500,
        min_chunk_size: int = 100,
    ):
        self.max_chunk_size = max_chunk_size
        self.min_chunk_size = min_chunk_size
        # Pattern for sentence boundaries
        self.sentence_pattern = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")

    def chunk(self, text: str) -> list[str]:
        """Split text into sentence-based chunks.

        Args:
            text: Text to chunk

        Returns:
            List of text chunks
        """
        if not text or not text.strip():
            return []

        # Split into sentences
        sentences = self.sentence_pattern.split(text.strip())
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            return [text.strip()] if text.strip() else []

        chunks = []
        current_chunk = []
        current_length = 0

        for sentence in sentences:
            sentence_length = len(sentence)

            # If single sentence exceeds max, split it
            if sentence_length > self.max_chunk_size:
                # Save current chunk if exists
                if current_chunk:
                    chunks.append(" ".join(current_chunk))
                    current_chunk = []
                    current_length = 0

                # Use fixed-size chunking for long sentence
                fixed_chunker = FixedSizeChunker(
                    chunk_size=self.max_chunk_size,
                    overlap=50,
                )
                chunks.extend(fixed_chunker.chunk(sentence))
                continue

            # Check if adding this sentence exceeds limit
            if current_length + sentence_length > self.max_chunk_size:
                # Save current chunk
                if current_chunk:
                    chunks.append(" ".join(current_chunk))
                current_chunk = [sentence]
                current_length = sentence_length
            else:
                current_chunk.append(sentence)
                current_length += sentence_length + 1  # +1 for space

        # Don't forget last chunk
        if current_chunk:
            chunk_text = " ".join(current_chunk)
            # Merge with previous if too small
            if len(chunk_text) < self.min_chunk_size and chunks:
                chunks[-1] = chunks[-1] + " " + chunk_text
            else:
                chunks.append(chunk_text)

        return chunks


class ParagraphChunker(BaseChunker):
    """Chunk text by paragraphs."""

    def __init__(
        self,
        max_chunk_size: int = 1000,
        min_chunk_size: int = 100,
    ):
        self.max_chunk_size = max_chunk_size
        self.min_chunk_size = min_chunk_size

    def chunk(self, text: str) -> list[str]:
        """Split text by paragraphs.

        Args:
            text: Text to chunk

        Returns:
            List of text chunks
        """
        if not text or not text.strip():
            return []

        # Split by double newlines (paragraphs)
        paragraphs = re.split(r"\n\s*\n", text.strip())
        paragraphs = [p.strip() for p in paragraphs if p.strip()]

        if not paragraphs:
            return [text.strip()] if text.strip() else []

        chunks = []
        current_chunk = []
        current_length = 0

        for paragraph in paragraphs:
            para_length = len(paragraph)

            # If single paragraph exceeds max, split it
            if para_length > self.max_chunk_size:
                if current_chunk:
                    chunks.append("\n\n".join(current_chunk))
                    current_chunk = []
                    current_length = 0

                # Use sentence chunking for long paragraphs
                sentence_chunker = SentenceChunker(
                    max_chunk_size=self.max_chunk_size,
                )
                chunks.extend(sentence_chunker.chunk(paragraph))
                continue

            if current_length + para_length > self.max_chunk_size:
                if current_chunk:
                    chunks.append("\n\n".join(current_chunk))
                current_chunk = [paragraph]
                current_length = para_length
            else:
                current_chunk.append(paragraph)
                current_length += para_length + 2  # +2 for \n\n

        if current_chunk:
            chunk_text = "\n\n".join(current_chunk)
            if len(chunk_text) < self.min_chunk_size and chunks:
                chunks[-1] = chunks[-1] + "\n\n" + chunk_text
            else:
                chunks.append(chunk_text)

        return chunks


class RecursiveChunker(BaseChunker):
    """Recursively chunk text using multiple separators."""

    def __init__(
        self,
        chunk_size: int = 500,
        overlap: int = 50,
        separators: Optional[list[str]] = None,
    ):
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.separators = separators or ["\n\n", "\n", ". ", " ", ""]

    def chunk(self, text: str) -> list[str]:
        """Recursively split text using hierarchical separators.

        Args:
            text: Text to chunk

        Returns:
            List of text chunks
        """
        if not text or not text.strip():
            return []

        return self._recursive_split(text.strip(), self.separators)

    def _recursive_split(
        self,
        text: str,
        separators: list[str],
    ) -> list[str]:
        """Recursively split text."""
        if len(text) <= self.chunk_size:
            return [text] if text.strip() else []

        if not separators:
            # No more separators, force split
            return FixedSizeChunker(
                chunk_size=self.chunk_size,
                overlap=self.overlap,
            ).chunk(text)

        separator = separators[0]
        remaining_separators = separators[1:]

        if separator:
            splits = text.split(separator)
        else:
            splits = list(text)

        chunks = []
        current_chunk = []
        current_length = 0

        for split in splits:
            split_length = len(split)

            if split_length > self.chunk_size:
                # Save current chunk
                if current_chunk:
                    chunks.append(separator.join(current_chunk))
                    current_chunk = []
                    current_length = 0
                # Recursively split
                chunks.extend(
                    self._recursive_split(split, remaining_separators)
                )
            elif current_length + split_length + len(separator) > self.chunk_size:
                if current_chunk:
                    chunks.append(separator.join(current_chunk))
                current_chunk = [split]
                current_length = split_length
            else:
                current_chunk.append(split)
                current_length += split_length + len(separator)

        if current_chunk:
            chunks.append(separator.join(current_chunk))

        return [c for c in chunks if c.strip()]


class TextChunker:
    """Main text chunker class with configurable strategy."""

    def __init__(
        self,
        strategy: ChunkingStrategy = ChunkingStrategy.RECURSIVE,
        chunk_size: int = 500,
        overlap: int = 50,
    ):
        self.strategy = strategy
        self.chunk_size = chunk_size
        self.overlap = overlap
        self._chunker = self._create_chunker()

    def _create_chunker(self) -> BaseChunker:
        """Create chunker based on strategy."""
        if self.strategy == ChunkingStrategy.FIXED_SIZE:
            return FixedSizeChunker(
                chunk_size=self.chunk_size,
                overlap=self.overlap,
            )
        elif self.strategy == ChunkingStrategy.SENTENCE:
            return SentenceChunker(
                max_chunk_size=self.chunk_size,
            )
        elif self.strategy == ChunkingStrategy.PARAGRAPH:
            return ParagraphChunker(
                max_chunk_size=self.chunk_size,
            )
        else:  # RECURSIVE
            return RecursiveChunker(
                chunk_size=self.chunk_size,
                overlap=self.overlap,
            )

    def chunk(self, text: str) -> list[str]:
        """Split text into chunks using configured strategy.

        Args:
            text: Text to chunk

        Returns:
            List of text chunks
        """
        if not text:
            return []

        chunks = self._chunker.chunk(text)

        logger.debug(
            f"Chunked text into {len(chunks)} chunks using {self.strategy.value}"
        )

        return chunks

    def chunk_with_metadata(
        self,
        text: str,
        base_metadata: Optional[dict] = None,
    ) -> list[dict]:
        """Chunk text and include metadata for each chunk.

        Args:
            text: Text to chunk
            base_metadata: Metadata to include in all chunks

        Returns:
            List of dicts with 'content', 'chunk_index', and metadata
        """
        chunks = self.chunk(text)
        result = []

        for i, chunk in enumerate(chunks):
            chunk_data = {
                "content": chunk,
                "chunk_index": i,
                "char_count": len(chunk),
            }
            if base_metadata:
                chunk_data.update(base_metadata)
            result.append(chunk_data)

        return result
