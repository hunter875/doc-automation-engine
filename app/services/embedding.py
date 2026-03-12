"""Gemini embedding and chat service."""

import logging
from typing import Optional

from google import genai
from google.genai import types

from app.core.config import settings
from app.core.exceptions import OpenAIError

logger = logging.getLogger(__name__)

# Initialize new google-genai client
_genai_client = genai.Client(api_key=settings.GEMINI_API_KEY)

# Initialize OpenAI-compat client for chat
from openai import OpenAI

openai_client = OpenAI(
    api_key=settings.GEMINI_API_KEY,
    base_url=settings.GEMINI_BASE_URL,
    timeout=settings.GEMINI_TIMEOUT,
    max_retries=settings.GEMINI_MAX_RETRIES,
)


class EmbeddingService:
    """Service for generating text embeddings using Gemini."""

    def __init__(
        self,
        model: str = None,
        batch_size: int = None,
    ):
        self.model = model or settings.GEMINI_EMBEDDING_MODEL
        self.batch_size = batch_size or settings.EMBEDDING_BATCH_SIZE

    def count_tokens(self, text: str) -> int:
        """Estimate token count (approx 4 chars per token)."""
        return max(1, len(text) // 4)

    def embed_single(self, text: str) -> list[float]:
        """Generate embedding for a single text."""
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")
        try:
            result = _genai_client.models.embed_content(
                model=self.model,
                contents=text.strip(),
                config={"output_dimensionality": settings.EMBEDDING_DIMENSION},
            )
            return result.embeddings[0].values
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            raise OpenAIError(message="Failed to generate embedding", original_error=str(e))

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        if not texts:
            return []
        clean_texts = [t.strip() for t in texts if t and t.strip()]
        if not clean_texts:
            return []
        embeddings = []
        try:
            for i in range(0, len(clean_texts), self.batch_size):
                batch = clean_texts[i: i + self.batch_size]
                for text in batch:
                    result = _genai_client.models.embed_content(
                        model=self.model,
                        contents=text,
                        config={"output_dimensionality": settings.EMBEDDING_DIMENSION},
                    )
                    embeddings.append(result.embeddings[0].values)
                logger.debug(f"Embedded batch {i // self.batch_size + 1}, total: {len(embeddings)}/{len(clean_texts)}")
            return embeddings
        except Exception as e:
            logger.error(f"Failed to generate embeddings: {e}")
            raise OpenAIError(message="Failed to generate embeddings", original_error=str(e))

    def embed_with_token_count(self, texts: list[str]) -> tuple[list[list[float]], int]:
        """Generate embeddings and return total token count."""
        total_tokens = sum(self.count_tokens(t) for t in texts if t)
        embeddings = self.embed_batch(texts)
        return embeddings, total_tokens


class ChatService:
    """Service for chat completions using OpenAI."""

    def __init__(
        self,
        model: str = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
    ):
        self.model = model or settings.GEMINI_CHAT_MODEL
        self.temperature = temperature
        self.max_tokens = max_tokens

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> tuple[str, dict]:
        """Generate chat completion.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            temperature: Override temperature
            max_tokens: Override max tokens

        Returns:
            Tuple of (response_text, usage_dict)

        Raises:
            OpenAIError: If generation fails
        """
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        try:
            response = openai_client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature or self.temperature,
                max_tokens=max_tokens or self.max_tokens,
            )

            content = response.choices[0].message.content
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

            return content, usage

        except Exception as e:
            logger.error(f"Chat completion failed: {e}")
            raise OpenAIError(
                message="Failed to generate response",
                original_error=str(e),
            )

    def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ):
        """Generate chat completion with streaming.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            temperature: Override temperature
            max_tokens: Override max tokens

        Yields:
            Content chunks as they arrive

        Raises:
            OpenAIError: If generation fails
        """
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        try:
            stream = openai_client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature or self.temperature,
                max_tokens=max_tokens or self.max_tokens,
                stream=True,
            )

            for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            logger.error(f"Streaming chat completion failed: {e}")
            raise OpenAIError(
                message="Failed to generate streaming response",
                original_error=str(e),
            )


# RAG-specific prompts
RAG_SYSTEM_PROMPT = """You are a helpful assistant that answers questions based on the provided context.

Instructions:
1. Answer the question using ONLY the information from the provided context
2. If the context doesn't contain enough information, say so clearly
3. Cite specific parts of the context when possible
4. Be concise but comprehensive
5. Use markdown formatting for better readability
6. If asked in Vietnamese, respond in Vietnamese

Context will be provided in the user message."""


def build_rag_prompt(question: str, context_chunks: list[str]) -> str:
    """Build RAG prompt with context.

    Args:
        question: User's question
        context_chunks: Retrieved context chunks

    Returns:
        Formatted prompt string
    """
    context = "\n\n---\n\n".join(context_chunks)

    prompt = f"""Context:
{context}

---

Question: {question}

Please answer the question based on the context provided above."""

    return prompt
