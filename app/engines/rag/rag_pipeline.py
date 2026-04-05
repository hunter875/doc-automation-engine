"""RAG (Retrieval-Augmented Generation) service."""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import AsyncGenerator, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import (
    DocumentNotFoundError,
    ProcessingError,
)
from app.engines.rag.vector_search import (
    bulk_index_documents,
    delete_document_chunks,
    get_document_chunks as pgvector_get_chunks,
    hybrid_search,
    search_vectors,
)
from app.domain.models.document import Document, DocumentStatus
from app.domain.models.tenant import TenantUsageLog
from app.engines.rag.chunking import ChunkingStrategy, TextChunker
from app.engines.rag.embedding_service import (
    ChatService,
    EmbeddingService,
    RAG_SYSTEM_PROMPT,
    build_rag_prompt,
)

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Search result with score and metadata."""

    chunk_id: str
    document_id: str
    content: str
    score: float
    metadata: dict


@dataclass
class RAGResponse:
    """RAG query response."""

    answer: str
    sources: list[SearchResult]
    usage: dict
    query_time_ms: float


class RAGService:
    """Service for RAG operations."""

    def __init__(self, db: Session):
        self.db = db
        self.embedding_service = EmbeddingService()
        self.chat_service = ChatService()
        self.chunker = TextChunker()

    def process_document(
        self,
        document_id: str,
        content: str,
        tenant_id: str,
        strategy: ChunkingStrategy = ChunkingStrategy.RECURSIVE,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ) -> int:
        """Process document: chunk, embed, and index.

        Args:
            document_id: Document UUID
            content: Document text content
            tenant_id: Tenant UUID
            strategy: Chunking strategy
            chunk_size: Override chunk size
            chunk_overlap: Override chunk overlap

        Returns:
            Number of chunks indexed

        Raises:
            ProcessingError: If processing fails
        """
        chunk_size = chunk_size or settings.CHUNK_SIZE
        chunk_overlap = chunk_overlap or settings.CHUNK_OVERLAP

        try:
            # Step 1: Chunk the document
            chunker = TextChunker(
                strategy=strategy,
                chunk_size=chunk_size,
                overlap=chunk_overlap,
            )
            chunks = chunker.chunk(text=content)

            if not chunks:
                logger.warning(f"No chunks generated for document {document_id}")
                return 0

            logger.info(f"Generated {len(chunks)} chunks for document {document_id}")

            # Step 2: Generate embeddings
            embeddings, token_count = self.embedding_service.embed_with_token_count(
                chunks
            )

            logger.info(
                f"Generated embeddings for {len(embeddings)} chunks, "
                f"total tokens: {token_count}"
            )

            # Step 3: Prepare documents for indexing
            pgvector_docs = []
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                doc = {
                    "chunk_id": f"{document_id}_chunk_{i}",
                    "document_id": document_id,
                    "tenant_id": tenant_id,
                    "content": chunk,
                    "embedding": embedding,
                    "chunk_index": i,
                    "created_at": datetime.utcnow().isoformat(),
                }
                pgvector_docs.append(doc)

            # Step 4: Bulk index to PostgreSQL via pgvector
            indexed_count = bulk_index_documents(self.db, pgvector_docs)

            logger.info(f"Indexed {indexed_count} chunks for document {document_id}")

            # Step 5: Log usage
            self._log_usage(
                tenant_id=tenant_id,
                action="document_process",
                tokens_used=token_count,
                metadata={
                    "document_id": document_id,
                    "chunk_count": len(chunks),
                },
            )

            return indexed_count

        except Exception as e:
            logger.error(f"Failed to process document {document_id}: {e}")
            raise ProcessingError(
                message=f"Failed to process document: {str(e)}",
            )

    def search(
        self,
        query: str,
        tenant_id: str,
        document_ids: Optional[list[str]] = None,
        top_k: int = 5,
        min_score: float = 0.3,
        use_hybrid: bool = True,
    ) -> list[SearchResult]:
        """Search for relevant document chunks.

        Args:
            query: Search query
            tenant_id: Tenant UUID
            document_ids: Optional list of document IDs to search within
            top_k: Number of results to return
            min_score: Minimum similarity score threshold
            use_hybrid: Use hybrid search (vector + BM25)

        Returns:
            List of SearchResult objects
        """
        # Generate query embedding
        query_embedding = self.embedding_service.embed_single(query)

        # Execute search
        if use_hybrid:
            raw_results = hybrid_search(
                db=self.db,
                query_text=query,
                query_vector=query_embedding,
                tenant_id=tenant_id,
                top_k=top_k,
                document_ids=document_ids,
            )
        else:
            raw_results = search_vectors(
                db=self.db,
                query_vector=query_embedding,
                tenant_id=tenant_id,
                top_k=top_k,
                document_ids=document_ids,
            )

        # Convert to SearchResult objects
        results = []
        for hit in raw_results:
            score = hit.get("score", 0)
            if score < min_score:
                continue

            result = SearchResult(
                chunk_id=hit.get("chunk_id", ""),
                document_id=hit.get("document_id", ""),
                content=hit.get("content", ""),
                score=score,
                metadata={
                    "chunk_index": hit.get("chunk_index"),
                },
            )
            results.append(result)

        return results

    def query(
        self,
        question: str,
        tenant_id: str,
        document_ids: Optional[list[str]] = None,
        top_k: int = 5,
        min_score: float = 0.3,
        use_hybrid: bool = True,
        temperature: float = 0.7,
        max_tokens: int = 1000,
    ) -> RAGResponse:
        """Execute RAG query.

        Args:
            question: User's question
            tenant_id: Tenant UUID
            document_ids: Optional list of document IDs to search within
            top_k: Number of context chunks to retrieve
            use_hybrid: Use hybrid search
            temperature: LLM temperature
            max_tokens: Max response tokens

        Returns:
            RAGResponse with answer and sources
        """
        import time

        start_time = time.time()

        # Step 1: Retrieve relevant chunks
        search_results = self.search(
            query=question,
            tenant_id=tenant_id,
            document_ids=document_ids,
            top_k=top_k,
            use_hybrid=use_hybrid,
        )

        if not search_results:
            return RAGResponse(
                answer="Tôi không tìm thấy thông tin liên quan trong tài liệu để trả lời câu hỏi này.",
                sources=[],
                usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                query_time_ms=(time.time() - start_time) * 1000,
            )

        # Step 2: Build prompt with context
        context_chunks = [r.content for r in search_results]
        prompt = build_rag_prompt(question, context_chunks)

        # Step 3: Generate answer
        try:
            answer, usage = self.chat_service.generate(
                prompt=prompt,
                system_prompt=RAG_SYSTEM_PROMPT,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as e:
            logger.warning(f"LLM generation failed, returning context only: {e}")
            # Fallback: return retrieved context without LLM generation
            context_text = "\n\n".join(f"[Source {i+1}]: {c}" for i, c in enumerate(context_chunks))
            answer = f"[LLM unavailable - showing retrieved context]\n\n{context_text}"
            usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        query_time_ms = (time.time() - start_time) * 1000

        # Step 4: Log usage
        self._log_usage(
            tenant_id=tenant_id,
            action="rag_query",
            tokens_used=usage["total_tokens"],
            metadata={
                "question_length": len(question),
                "sources_count": len(search_results),
                "query_time_ms": query_time_ms,
            },
        )

        return RAGResponse(
            answer=answer,
            sources=search_results,
            usage=usage,
            query_time_ms=query_time_ms,
        )

    async def query_stream(
        self,
        question: str,
        tenant_id: str,
        document_ids: Optional[list[str]] = None,
        top_k: int = 5,
        use_hybrid: bool = True,
        temperature: float = 0.7,
        max_tokens: int = 1000,
    ) -> AsyncGenerator[dict, None]:
        """Execute RAG query with streaming response.

        Args:
            question: User's question
            tenant_id: Tenant UUID
            document_ids: Optional list of document IDs to search within
            top_k: Number of context chunks to retrieve
            use_hybrid: Use hybrid search
            temperature: LLM temperature
            max_tokens: Max response tokens

        Yields:
            Event dicts for SSE streaming
        """
        import time

        start_time = time.time()

        # Step 1: Retrieve relevant chunks
        yield {"event": "status", "data": "Đang tìm kiếm thông tin liên quan..."}

        search_results = self.search(
            query=question,
            tenant_id=tenant_id,
            document_ids=document_ids,
            top_k=top_k,
            use_hybrid=use_hybrid,
        )

        # Send sources first
        sources_data = [
            {
                "chunk_id": r.chunk_id,
                "document_id": r.document_id,
                "score": r.score,
                "content_preview": r.content[:200] + "..." if len(r.content) > 200 else r.content,
            }
            for r in search_results
        ]
        yield {"event": "sources", "data": sources_data}

        if not search_results:
            yield {
                "event": "answer",
                "data": "Tôi không tìm thấy thông tin liên quan trong tài liệu để trả lời câu hỏi này.",
            }
            yield {"event": "done", "data": {"query_time_ms": (time.time() - start_time) * 1000}}
            return

        # Step 2: Build prompt
        yield {"event": "status", "data": "Đang tạo câu trả lời..."}

        context_chunks = [r.content for r in search_results]
        prompt = build_rag_prompt(question, context_chunks)

        # Step 3: Stream answer
        for chunk in self.chat_service.generate_stream(
            prompt=prompt,
            system_prompt=RAG_SYSTEM_PROMPT,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            yield {"event": "answer_chunk", "data": chunk}

        query_time_ms = (time.time() - start_time) * 1000

        # Log usage (estimate tokens for streaming)
        self._log_usage(
            tenant_id=tenant_id,
            action="rag_query_stream",
            tokens_used=0,  # Cannot track exactly with streaming
            metadata={
                "question_length": len(question),
                "sources_count": len(search_results),
                "query_time_ms": query_time_ms,
            },
        )

        yield {
            "event": "done",
            "data": {
                "query_time_ms": query_time_ms,
                "sources_count": len(search_results),
            },
        }

    def get_document_chunks(
        self,
        document_id: str,
        tenant_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> list[dict]:
        """Get chunks for a specific document.

        Args:
            document_id: Document UUID
            tenant_id: Tenant UUID
            page: Page number
            page_size: Items per page

        Returns:
            List of chunk dictionaries
        """
        return pgvector_get_chunks(
            db=self.db,
            document_id=document_id,
            tenant_id=tenant_id,
            page=page,
            page_size=page_size,
        )

    def _log_usage(
        self,
        tenant_id: str,
        action: str,
        tokens_used: int,
        metadata: Optional[dict] = None,
    ) -> None:
        """Log API usage for billing.

        Args:
            tenant_id: Tenant UUID
            action: Action type
            tokens_used: Number of tokens used
            metadata: Additional metadata
        """
        try:
            usage_log = TenantUsageLog(
                tenant_id=tenant_id,
                action=action,
                tokens_used=tokens_used,
                metadata=metadata or {},
            )
            self.db.add(usage_log)
            self.db.commit()
        except Exception as e:
            logger.warning(f"Failed to log usage: {e}")
            # Don't fail the main operation for usage logging


class DocumentProcessor:
    """Utility class for document text extraction."""

    @staticmethod
    def extract_text_from_pdf(content: bytes) -> str:
        """Extract text from PDF bytes using pdfplumber.

        Tables are converted to Markdown format to preserve structure.
        Falls back to pypdf if pdfplumber is unavailable.

        Args:
            content: PDF file content

        Returns:
            Extracted text with tables in Markdown
        """
        try:
            import io
            import pdfplumber

            page_parts = []
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                for page in pdf.pages:
                    parts: list[str] = []

                    # Extract tables first and record their bounding boxes
                    tables = page.find_tables()
                    table_bboxes = []
                    for table in tables:
                        data = table.extract()
                        if not data:
                            continue
                        table_bboxes.append(table.bbox)
                        # Convert to Markdown table
                        rows_md = []
                        for i, row in enumerate(data):
                            cells = [str(c or "").replace("\n", " ").strip() for c in row]
                            rows_md.append("| " + " | ".join(cells) + " |")
                            if i == 0:
                                rows_md.append("|" + "|".join(["---"] * len(cells)) + "|")
                        parts.append("\n".join(rows_md))

                    # Extract text, filtering out areas covered by tables
                    if table_bboxes:
                        # Crop page to exclude table regions
                        remaining = page
                        for bbox in table_bboxes:
                            # Mask table areas from text extraction
                            remaining = remaining.filter(
                                lambda obj, b=bbox: not (
                                    b[0] <= obj.get("x0", 0) and obj.get("x1", 0) <= b[2]
                                    and b[1] <= obj.get("top", 0) and obj.get("bottom", 0) <= b[3]
                                )
                            )
                        text = remaining.extract_text() or ""
                    else:
                        text = page.extract_text() or ""

                    if text.strip():
                        parts.insert(0, text.strip())

                    if parts:
                        page_parts.append("\n\n".join(parts))

            return "\n\n".join(page_parts)

        except ImportError:
            logger.warning("pdfplumber not available, falling back to pypdf")
        except Exception as e:
            logger.warning(f"pdfplumber extraction failed ({e}), falling back to pypdf")

        # Fallback: pypdf
        try:
            import io
            import pypdf

            reader = pypdf.PdfReader(io.BytesIO(content))
            text_parts = [p.extract_text() for p in reader.pages if p.extract_text()]
            return "\n\n".join(text_parts)
        except Exception as e:
            logger.error(f"PDF extraction failed: {e}")
            raise ProcessingError(message="Failed to extract text from PDF")

    @staticmethod
    def extract_text_from_docx(content: bytes) -> str:
        """Extract text from DOCX bytes.

        Args:
            content: DOCX file content

        Returns:
            Extracted text
        """
        try:
            import io

            import docx

            doc = docx.Document(io.BytesIO(content))
            text_parts = []

            for para in doc.paragraphs:
                if para.text.strip():
                    text_parts.append(para.text)

            return "\n\n".join(text_parts)

        except Exception as e:
            logger.error(f"DOCX extraction failed: {e}")
            raise ProcessingError(
                message="Failed to extract text from DOCX",
            )

    @staticmethod
    def extract_text(content: bytes, mime_type: str) -> str:
        """Extract text based on MIME type.

        Args:
            content: File content
            mime_type: MIME type

        Returns:
            Extracted text
        """
        if mime_type == "application/pdf":
            return DocumentProcessor.extract_text_from_pdf(content)

        if "officedocument" in mime_type or mime_type == "application/msword":
            return DocumentProcessor.extract_text_from_docx(content)

        # Plain text files
        if mime_type.startswith("text/") or mime_type == "application/json":
            try:
                return content.decode("utf-8")
            except UnicodeDecodeError:
                return content.decode("latin-1")

        raise ProcessingError(
            message=f"Unsupported MIME type for text extraction: {mime_type}",
        )
