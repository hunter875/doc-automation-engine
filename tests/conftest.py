"""Pytest configuration and shared fixtures."""

import os
import uuid
from datetime import datetime
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Override settings before importing app modules
os.environ["SECRET_KEY"] = "test-secret-key-for-unit-tests-only"
os.environ["GEMINI_API_KEY"] = "fake-gemini-key"
os.environ["POSTGRES_HOST"] = "localhost"
os.environ["POSTGRES_PORT"] = "5432"
os.environ["POSTGRES_USER"] = "test"
os.environ["POSTGRES_PASSWORD"] = "test"
os.environ["POSTGRES_DB"] = "test_rag"
os.environ["REDIS_HOST"] = "localhost"

from app.infrastructure.db.session import Base


# ============================================================================
# Database Fixtures (SQLite in-memory for tests)
# ============================================================================

@pytest.fixture(scope="session")
def test_engine():
    """Create test database engine using SQLite in-memory."""
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    # Create all tables
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session(test_engine) -> Generator[Session, None, None]:
    """Create a fresh database session for each test."""
    TestSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=test_engine,
    )

    session = TestSessionLocal()

    try:
        yield session
    finally:
        session.rollback()
        session.close()


# ============================================================================
# User / Auth Fixtures
# ============================================================================

@pytest.fixture
def test_user_data():
    """Sample user registration data."""
    return {
        "email": "test@example.com",
        "password": "StrongPass123",
        "full_name": "Test User",
    }


@pytest.fixture
def test_user(db_session):
    """Create a test user in the database."""
    from app.core.security import get_password_hash
    from app.domain.models.user import User

    user = User(
        id=uuid.uuid4(),
        email="testuser@example.com",
        password_hash=get_password_hash("StrongPass123"),
        full_name="Test User",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def inactive_user(db_session):
    """Create an inactive test user."""
    from app.core.security import get_password_hash
    from app.domain.models.user import User

    user = User(
        id=uuid.uuid4(),
        email="inactive@example.com",
        password_hash=get_password_hash("StrongPass123"),
        full_name="Inactive User",
        is_active=False,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


# ============================================================================
# Tenant Fixtures
# ============================================================================

@pytest.fixture
def test_tenant(db_session):
    """Create a test tenant."""
    from app.domain.models.tenant import Tenant

    tenant = Tenant(
        id=uuid.uuid4(),
        name="Test Tenant",
        description="Test tenant for unit tests",
        billing_status="active",
    )
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return tenant


@pytest.fixture
def test_user_role(db_session, test_user, test_tenant):
    """Create a user-tenant role mapping."""
    from app.domain.models.tenant import UserTenantRole

    role = UserTenantRole(
        id=uuid.uuid4(),
        user_id=test_user.id,
        tenant_id=test_tenant.id,
        role="admin",
    )
    db_session.add(role)
    db_session.commit()
    db_session.refresh(role)
    return role


# ============================================================================
# Mock Fixtures
# ============================================================================

@pytest.fixture
def mock_openai():
    """Mock OpenAI client."""
    with patch("app.engines.rag.embedding_service.openai_client") as mock:
        # Mock embeddings
        mock_embedding_response = MagicMock()
        mock_embedding_data = MagicMock()
        mock_embedding_data.embedding = [0.1] * 1536
        mock_embedding_data.index = 0
        mock_embedding_response.data = [mock_embedding_data]
        mock.embeddings.create.return_value = mock_embedding_response

        # Mock chat completions
        mock_chat_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "This is a test answer."
        mock_chat_response.choices = [mock_choice]
        mock_chat_response.usage.prompt_tokens = 100
        mock_chat_response.usage.completion_tokens = 50
        mock_chat_response.usage.total_tokens = 150
        mock.chat.completions.create.return_value = mock_chat_response

        yield mock


@pytest.fixture
def mock_pgvector():
    """Mock pgvector operations."""
    with patch("app.engines.rag.vector_search.search_vectors") as mock_search, \
         patch("app.engines.rag.vector_search.hybrid_search") as mock_hybrid, \
         patch("app.engines.rag.vector_search.bulk_index_documents") as mock_bulk, \
         patch("app.engines.rag.vector_search.delete_document_chunks") as mock_delete:

        # Mock search response
        mock_search.return_value = [
            {
                "chunk_id": "chunk_1",
                "document_id": "doc_1",
                "content": "Test content 1",
                "chunk_index": 0,
                "metadata": {},
                "score": 0.95,
            },
            {
                "chunk_id": "chunk_2",
                "document_id": "doc_1",
                "content": "Test content 2",
                "chunk_index": 1,
                "metadata": {},
                "score": 0.85,
            },
        ]

        mock_hybrid.return_value = mock_search.return_value
        mock_bulk.return_value = 5
        mock_delete.return_value = 3

        yield {
            "search": mock_search,
            "hybrid": mock_hybrid,
            "bulk": mock_bulk,
            "delete": mock_delete,
        }


@pytest.fixture
def mock_s3():
    """Mock S3/MinIO client."""
    with patch("app.application.doc_service.s3_client") as mock:
        mock.put_object.return_value = {}
        mock.get_object.return_value = {
            "Body": MagicMock(read=lambda: b"test file content")
        }
        mock.delete_object.return_value = {}
        yield mock
