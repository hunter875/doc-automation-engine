"""PostgreSQL + pgvector vector operations.

Replaces OpenSearch for vector storage and similarity search.
Uses pgvector extension for efficient vector indexing and search.
"""

import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import VectorStoreError

logger = logging.getLogger(__name__)


def ensure_pgvector_extension(db: Session) -> None:
    """Create pgvector extension if not exists.

    Args:
        db: SQLAlchemy session
    """
    try:
        db.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        db.commit()
        logger.info("pgvector extension ensured")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create pgvector extension: {e}")
        raise VectorStoreError(
            message="Failed to create pgvector extension",
            original_error=str(e),
        )


def create_vector_index(db: Session) -> None:
    """Create HNSW index on document_chunks.embedding for fast ANN search.

    Args:
        db: SQLAlchemy session
    """
    try:
        # HNSW index — good balance between speed and recall
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding
            ON document_chunks
            USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 200)
        """))
        # GIN index for full-text search
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_document_chunks_content_fts
            ON document_chunks
            USING gin (to_tsvector('english', content))
        """))
        db.commit()
        logger.info("Vector and FTS indexes created")
    except Exception as e:
        db.rollback()
        logger.warning(f"Index creation warning (may already exist): {e}")


def index_document(
    db: Session,
    document_id: str,
    tenant_id: str,
    chunk_id: str,
    content: str,
    vector: list[float],
    chunk_index: int = 0,
    metadata: Optional[dict[str, Any]] = None,
) -> str:
    """Index a single document chunk with its embedding vector.

    Args:
        db: SQLAlchemy session
        document_id: ID of the parent document
        tenant_id: ID of the tenant
        chunk_id: Unique ID for this chunk
        content: Text content of the chunk
        vector: Embedding vector
        chunk_index: Position index of chunk in document
        metadata: Additional metadata

    Returns:
        ID of the indexed chunk
    """
    from app.domain.models.document import DocumentChunk

    try:
        chunk = DocumentChunk(
            chunk_id=chunk_id,
            document_id=document_id,
            tenant_id=tenant_id,
            content=content,
            embedding=vector,
            chunk_index=chunk_index,
            embedding_model=settings.GEMINI_EMBEDDING_MODEL,
            metadata_=metadata or {},
        )
        db.add(chunk)
        db.flush()
        logger.debug(f"Indexed chunk {chunk_id}")
        return chunk_id
    except Exception as e:
        logger.error(f"Failed to index document chunk: {e}")
        raise VectorStoreError(
            message="Failed to index document chunk",
            original_error=str(e),
        )


def bulk_index_documents(
    db: Session,
    documents: list[dict[str, Any]],
) -> int:
    """Bulk index multiple document chunks.

    Args:
        db: SQLAlchemy session
        documents: List of document dicts with required fields:
            - chunk_id, document_id, tenant_id, content, embedding
            - optional: chunk_index, metadata

    Returns:
        Number of successfully indexed documents
    """
    from app.domain.models.document import DocumentChunk

    try:
        chunks = []
        for doc in documents:
            chunk = DocumentChunk(
                chunk_id=doc["chunk_id"],
                document_id=doc["document_id"],
                tenant_id=doc["tenant_id"],
                content=doc["content"],
                embedding=doc["embedding"],
                chunk_index=doc.get("chunk_index", 0),
                embedding_model=settings.GEMINI_EMBEDDING_MODEL,
                metadata_=doc.get("metadata", {}),
            )
            chunks.append(chunk)

        db.add_all(chunks)
        db.flush()
        logger.info(f"Bulk indexed {len(chunks)} chunks")
        return len(chunks)

    except Exception as e:
        logger.error(f"Bulk indexing failed: {e}")
        raise VectorStoreError(
            message="Bulk indexing failed",
            original_error=str(e),
        )


def search_vectors(
    db: Session,
    query_vector: list[float],
    tenant_id: str,
    top_k: int = 5,
    document_ids: Optional[list[str]] = None,
    min_score: float = 0.0,
) -> list[dict[str, Any]]:
    """Search for similar vectors using pgvector cosine distance.

    Args:
        db: SQLAlchemy session
        query_vector: Query embedding vector
        tenant_id: Tenant ID for filtering (CRITICAL for multi-tenant isolation)
        top_k: Number of results to return
        document_ids: Optional list of document IDs to filter by
        min_score: Minimum cosine similarity score (0-1)

    Returns:
        List of matching documents with scores
    """
    try:
        # pgvector: cosine distance = 1 - cosine_similarity
        # so similarity = 1 - distance
        vector_str = f"[{','.join(str(v) for v in query_vector)}]"

        # Build WHERE clause
        conditions = ["dc.tenant_id = :tenant_id"]
        params: dict[str, Any] = {
            "tenant_id": tenant_id,
            "top_k": top_k,
            "query_vector": vector_str,
        }

        if document_ids:
            conditions.append("dc.document_id = ANY(CAST(:document_ids AS uuid[]))")
            params["document_ids"] = document_ids

        if min_score > 0:
            # cosine distance < (1 - min_score) means similarity > min_score
            conditions.append(
                "(1 - (dc.embedding <=> CAST(:query_vector AS vector))) >= :min_score"
            )
            params["min_score"] = min_score

        where_clause = " AND ".join(conditions)

        query = text(f"""
            SELECT
                dc.chunk_id,
                dc.document_id,
                dc.content,
                dc.chunk_index,
                dc.metadata as metadata,
                (1 - (dc.embedding <=> CAST(:query_vector AS vector))) AS score
            FROM document_chunks dc
            WHERE {where_clause}
            ORDER BY dc.embedding <=> CAST(:query_vector AS vector)
            LIMIT :top_k
        """)

        result = db.execute(query, params)
        rows = result.fetchall()

        return [
            {
                "chunk_id": row.chunk_id,
                "document_id": row.document_id,
                "content": row.content,
                "chunk_index": row.chunk_index,
                "metadata": row.metadata or {},
                "score": float(row.score),
            }
            for row in rows
        ]

    except Exception as e:
        logger.error(f"Vector search failed: {e}")
        raise VectorStoreError(
            message="Vector search failed",
            original_error=str(e),
        )


def hybrid_search(
    db: Session,
    query_text: str,
    query_vector: list[float],
    tenant_id: str,
    top_k: int = 5,
    document_ids: Optional[list[str]] = None,
    vector_weight: float = 0.7,
) -> list[dict[str, Any]]:
    """Hybrid search combining vector similarity and full-text search (BM25-like).

    Uses PostgreSQL ts_rank for text relevance and pgvector for semantic similarity.
    Results are scored as: vector_weight * vector_score + (1 - vector_weight) * text_score

    Args:
        db: SQLAlchemy session
        query_text: Text query for full-text search
        query_vector: Query embedding for vector search
        tenant_id: Tenant ID for filtering
        top_k: Number of results
        document_ids: Optional document ID filter
        vector_weight: Weight for vector score (1 - this = text weight)

    Returns:
        List of matching documents with combined scores
    """
    try:
        vector_str = f"[{','.join(str(v) for v in query_vector)}]"

        conditions = ["dc.tenant_id = :tenant_id"]
        params: dict[str, Any] = {
            "tenant_id": tenant_id,
            "top_k": top_k,
            "query_vector": vector_str,
            "query_text": query_text,
            "vector_weight": vector_weight,
            "text_weight": 1.0 - vector_weight,
        }

        if document_ids:
            conditions.append("dc.document_id = ANY(CAST(:document_ids AS uuid[]))")
            params["document_ids"] = document_ids

        where_clause = " AND ".join(conditions)

        query = text(f"""
            SELECT
                dc.chunk_id,
                dc.document_id,
                dc.content,
                dc.chunk_index,
                dc.metadata as metadata,
                (1 - (dc.embedding <=> CAST(:query_vector AS vector))) AS vector_score,
                COALESCE(
                    ts_rank_cd(
                        to_tsvector('english', dc.content),
                        plainto_tsquery('english', :query_text)
                    ),
                    0
                ) AS text_score,
                (
                    :vector_weight * (1 - (dc.embedding <=> CAST(:query_vector AS vector)))
                    + :text_weight * COALESCE(
                        ts_rank_cd(
                            to_tsvector('english', dc.content),
                            plainto_tsquery('english', :query_text)
                        ),
                        0
                    )
                ) AS combined_score
            FROM document_chunks dc
            WHERE {where_clause}
            ORDER BY combined_score DESC
            LIMIT :top_k
        """)

        result = db.execute(query, params)
        rows = result.fetchall()

        return [
            {
                "chunk_id": row.chunk_id,
                "document_id": row.document_id,
                "content": row.content,
                "chunk_index": row.chunk_index,
                "metadata": row.metadata or {},
                "score": float(row.combined_score),
            }
            for row in rows
        ]

    except Exception as e:
        logger.error(f"Hybrid search failed: {e}")
        raise VectorStoreError(
            message="Hybrid search failed",
            original_error=str(e),
        )


def delete_document_chunks(
    db: Session,
    document_id: str,
    tenant_id: str,
) -> int:
    """Delete all chunks for a document.

    Args:
        db: SQLAlchemy session
        document_id: Document ID
        tenant_id: Tenant ID (for safety — multi-tenant isolation)

    Returns:
        Number of deleted chunks
    """
    from app.domain.models.document import DocumentChunk

    try:
        deleted = (
            db.query(DocumentChunk)
            .filter(
                DocumentChunk.document_id == document_id,
                DocumentChunk.tenant_id == tenant_id,
            )
            .delete(synchronize_session=False)
        )
        db.flush()
        logger.info(f"Deleted {deleted} chunks for document {document_id}")
        return deleted
    except Exception as e:
        logger.error(f"Failed to delete document chunks: {e}")
        raise VectorStoreError(
            message="Failed to delete document chunks",
            original_error=str(e),
        )


def get_document_chunks(
    db: Session,
    document_id: str,
    tenant_id: str,
    page: int = 1,
    page_size: int = 20,
) -> list[dict[str, Any]]:
    """Get chunks for a specific document with pagination.

    Args:
        db: SQLAlchemy session
        document_id: Document UUID
        tenant_id: Tenant UUID
        page: Page number (1-indexed)
        page_size: Items per page

    Returns:
        List of chunk dictionaries
    """
    from app.domain.models.document import DocumentChunk

    try:
        offset = (page - 1) * page_size
        chunks = (
            db.query(DocumentChunk)
            .filter(
                DocumentChunk.document_id == document_id,
                DocumentChunk.tenant_id == tenant_id,
            )
            .order_by(DocumentChunk.chunk_index.asc())
            .offset(offset)
            .limit(page_size)
            .all()
        )

        return [
            {
                "chunk_id": c.chunk_id,
                "chunk_index": c.chunk_index,
                "content": c.content,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in chunks
        ]
    except Exception as e:
        logger.error(f"Failed to get document chunks: {e}")
        raise VectorStoreError(
            message="Failed to get document chunks",
            original_error=str(e),
        )


def check_pgvector_connection(db: Session) -> bool:
    """Check if pgvector extension is available.

    Args:
        db: SQLAlchemy session

    Returns:
        True if pgvector is available
    """
    try:
        result = db.execute(
            text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        )
        return result.fetchone() is not None
    except Exception:
        return False
