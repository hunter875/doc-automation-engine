"""Unit tests for embedding and RAG service."""

from unittest.mock import MagicMock, patch

import pytest


# ============================================================================
# Embedding Service Tests
# ============================================================================


class TestEmbeddingService:
    """Tests for OpenAI embedding service."""

    def test_embed_single_text(self, mock_openai):
        """Test generating embedding for a single text."""
        from app.engines.rag.embedding_service import EmbeddingService

        service = EmbeddingService()
        embedding = service.embed_single("Hello world")

        assert embedding is not None
        assert isinstance(embedding, list)
        assert len(embedding) == 1536
        mock_openai.embeddings.create.assert_called_once()

    def test_embed_single_empty_text_raises(self, mock_openai):
        """Test that empty text raises ValueError."""
        from app.engines.rag.embedding_service import EmbeddingService

        service = EmbeddingService()

        with pytest.raises(ValueError, match="Text cannot be empty"):
            service.embed_single("")

        with pytest.raises(ValueError, match="Text cannot be empty"):
            service.embed_single("   ")

    def test_embed_batch(self, mock_openai):
        """Test generating embeddings for a batch of texts."""
        from app.engines.rag.embedding_service import EmbeddingService

        # Setup mock for batch
        mock_data = []
        for i in range(3):
            item = MagicMock()
            item.embedding = [0.1] * 1536
            item.index = i
            mock_data.append(item)

        mock_response = MagicMock()
        mock_response.data = mock_data
        mock_openai.embeddings.create.return_value = mock_response

        service = EmbeddingService(batch_size=10)
        texts = ["Text one", "Text two", "Text three"]
        embeddings = service.embed_batch(texts)

        assert len(embeddings) == 3
        assert all(len(e) == 1536 for e in embeddings)

    def test_embed_batch_empty_list(self, mock_openai):
        """Test batch embedding with empty list."""
        from app.engines.rag.embedding_service import EmbeddingService

        service = EmbeddingService()
        result = service.embed_batch([])

        assert result == []
        mock_openai.embeddings.create.assert_not_called()

    def test_embed_batch_filters_empty_texts(self, mock_openai):
        """Test that empty texts are filtered out in batch."""
        from app.engines.rag.embedding_service import EmbeddingService

        service = EmbeddingService()
        result = service.embed_batch(["", "  ", None])

        # All texts are empty/None, should return empty
        assert result == []

    def test_embed_with_token_count(self, mock_openai):
        """Test embedding with token count tracking."""
        from app.engines.rag.embedding_service import EmbeddingService

        service = EmbeddingService()
        texts = ["Hello world"]

        embeddings, token_count = service.embed_with_token_count(texts)

        assert len(embeddings) >= 0
        assert isinstance(token_count, int)
        assert token_count >= 0

    def test_embed_batch_respects_batch_size(self, mock_openai):
        """Test that batch size is respected."""
        from app.engines.rag.embedding_service import EmbeddingService

        # Create many mock responses
        def create_response(*args, **kwargs):
            texts = kwargs.get("input", args[0] if args else [])
            if isinstance(texts, str):
                texts = [texts]
            mock_response = MagicMock()
            mock_items = []
            for i in range(len(texts)):
                item = MagicMock()
                item.embedding = [0.1] * 1536
                item.index = i
                mock_items.append(item)
            mock_response.data = mock_items
            return mock_response

        mock_openai.embeddings.create.side_effect = create_response

        service = EmbeddingService(batch_size=2)
        texts = ["Text 1", "Text 2", "Text 3", "Text 4", "Text 5"]
        embeddings = service.embed_batch(texts)

        assert len(embeddings) == 5
        # With batch_size=2, we need 3 API calls (2+2+1)
        assert mock_openai.embeddings.create.call_count == 3


# ============================================================================
# Chat Service Tests
# ============================================================================


class TestChatService:
    """Tests for OpenAI chat completion service."""

    def test_generate_response(self, mock_openai):
        """Test generating a chat response."""
        from app.engines.rag.embedding_service import ChatService

        service = ChatService()
        answer, usage = service.generate("What is AI?")

        assert answer == "This is a test answer."
        assert usage["total_tokens"] == 150
        assert usage["prompt_tokens"] == 100
        assert usage["completion_tokens"] == 50

    def test_generate_with_system_prompt(self, mock_openai):
        """Test generation with system prompt."""
        from app.engines.rag.embedding_service import ChatService

        service = ChatService()
        answer, usage = service.generate(
            prompt="What is AI?",
            system_prompt="You are a helpful assistant.",
        )

        assert answer is not None
        # Verify system message was included
        call_args = mock_openai.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    def test_generate_with_custom_params(self, mock_openai):
        """Test generation with custom temperature and max_tokens."""
        from app.engines.rag.embedding_service import ChatService

        service = ChatService(temperature=0.5, max_tokens=500)
        answer, usage = service.generate(
            prompt="Test",
            temperature=0.2,
            max_tokens=100,
        )

        call_args = mock_openai.chat.completions.create.call_args
        assert call_args.kwargs["temperature"] == 0.2
        assert call_args.kwargs["max_tokens"] == 100

    def test_generate_stream(self, mock_openai):
        """Test streaming chat completion."""
        from app.engines.rag.embedding_service import ChatService

        # Setup streaming mock
        chunk1 = MagicMock()
        chunk1.choices = [MagicMock()]
        chunk1.choices[0].delta.content = "Hello"

        chunk2 = MagicMock()
        chunk2.choices = [MagicMock()]
        chunk2.choices[0].delta.content = " world"

        chunk3 = MagicMock()
        chunk3.choices = [MagicMock()]
        chunk3.choices[0].delta.content = None

        mock_openai.chat.completions.create.return_value = [chunk1, chunk2, chunk3]

        service = ChatService()
        chunks = list(service.generate_stream("Tell me something"))

        assert chunks == ["Hello", " world"]


# ============================================================================
# RAG Prompt Building Tests
# ============================================================================


class TestRAGPrompt:
    """Tests for RAG prompt building utilities."""

    def test_build_rag_prompt(self):
        """Test building RAG prompt with context."""
        from app.engines.rag.embedding_service import build_rag_prompt

        question = "What is machine learning?"
        context_chunks = [
            "Machine learning is a branch of AI.",
            "It allows computers to learn from data.",
        ]

        prompt = build_rag_prompt(question, context_chunks)

        assert "What is machine learning?" in prompt
        assert "Machine learning is a branch of AI." in prompt
        assert "It allows computers to learn from data." in prompt
        assert "Context:" in prompt

    def test_build_rag_prompt_empty_context(self):
        """Test building RAG prompt with empty context."""
        from app.engines.rag.embedding_service import build_rag_prompt

        prompt = build_rag_prompt("Question?", [])

        assert "Question?" in prompt

    def test_build_rag_prompt_single_context(self):
        """Test building RAG prompt with single context chunk."""
        from app.engines.rag.embedding_service import build_rag_prompt

        prompt = build_rag_prompt("What?", ["Only one context."])

        assert "Only one context." in prompt

    def test_rag_system_prompt_exists(self):
        """Test that RAG system prompt is defined."""
        from app.engines.rag.embedding_service import RAG_SYSTEM_PROMPT

        assert RAG_SYSTEM_PROMPT is not None
        assert len(RAG_SYSTEM_PROMPT) > 0
        assert "context" in RAG_SYSTEM_PROMPT.lower()


# ============================================================================
# Token Counting Tests
# ============================================================================


class TestTokenCounting:
    """Tests for token counting functionality."""

    def test_count_tokens(self):
        """Test counting tokens in text."""
        from app.engines.rag.embedding_service import EmbeddingService

        service = EmbeddingService()
        count = service.count_tokens("Hello world")

        assert count > 0
        assert isinstance(count, int)

    def test_count_tokens_empty_string(self):
        """Test counting tokens for empty string."""
        from app.engines.rag.embedding_service import EmbeddingService

        service = EmbeddingService()
        count = service.count_tokens("")

        assert count == 0

    def test_longer_text_more_tokens(self):
        """Test that longer text has more tokens."""
        from app.engines.rag.embedding_service import EmbeddingService

        service = EmbeddingService()
        short_count = service.count_tokens("Hello")
        long_count = service.count_tokens("Hello world this is a much longer text")

        assert long_count > short_count
