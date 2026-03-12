"""Unit tests for API endpoints."""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import auth as auth_router


# ============================================================================
# Create test FastAPI app
# ============================================================================


def create_test_app():
    """Create a FastAPI app for testing."""
    app = FastAPI()
    app.include_router(auth_router.router, prefix="/api/v1")
    return app


# ============================================================================
# Auth Schema Validation Tests
# ============================================================================


class TestAuthSchemas:
    """Tests for auth request/response schema validation."""

    def test_register_request_valid(self):
        """Test valid registration request."""
        from app.schemas.auth_schema import UserRegisterRequest

        data = UserRegisterRequest(
            email="test@example.com",
            password="StrongPass123",
            full_name="Test User",
        )

        assert data.email == "test@example.com"
        assert data.password == "StrongPass123"
        assert data.full_name == "Test User"

    def test_register_request_weak_password(self):
        """Test registration with weak password is rejected."""
        from pydantic import ValidationError
        from app.schemas.auth_schema import UserRegisterRequest

        # No uppercase
        with pytest.raises(ValidationError):
            UserRegisterRequest(
                email="test@example.com",
                password="weakpass123",
                full_name="Test",
            )

        # No lowercase
        with pytest.raises(ValidationError):
            UserRegisterRequest(
                email="test@example.com",
                password="STRONGPASS123",
                full_name="Test",
            )

        # No digit
        with pytest.raises(ValidationError):
            UserRegisterRequest(
                email="test@example.com",
                password="StrongPassword",
                full_name="Test",
            )

    def test_register_request_short_password(self):
        """Test registration with short password is rejected."""
        from pydantic import ValidationError
        from app.schemas.auth_schema import UserRegisterRequest

        with pytest.raises(ValidationError):
            UserRegisterRequest(
                email="test@example.com",
                password="Ab1",  # Too short (< 8)
                full_name="Test",
            )

    def test_register_request_invalid_email(self):
        """Test registration with invalid email is rejected."""
        from pydantic import ValidationError
        from app.schemas.auth_schema import UserRegisterRequest

        with pytest.raises(ValidationError):
            UserRegisterRequest(
                email="not-an-email",
                password="StrongPass123",
                full_name="Test",
            )

    def test_login_request_valid(self):
        """Test valid login request."""
        from app.schemas.auth_schema import UserLoginRequest

        data = UserLoginRequest(
            email="test@example.com",
            password="anypassword",
        )

        assert data.email == "test@example.com"

    def test_token_response(self):
        """Test token response schema."""
        from app.schemas.auth_schema import TokenResponse

        token = TokenResponse(
            access_token="eyJ0eXAiOiJKV1...",
            token_type="bearer",
            expires_in=1800,
        )

        assert token.access_token == "eyJ0eXAiOiJKV1..."
        assert token.token_type == "bearer"
        assert token.expires_in == 1800

    def test_user_response(self):
        """Test user response schema."""
        from datetime import datetime
        from app.schemas.auth_schema import UserResponse

        user = UserResponse(
            id=uuid.uuid4(),
            email="test@example.com",
            full_name="Test User",
            is_active=True,
            created_at=datetime.utcnow(),
        )

        assert user.email == "test@example.com"
        assert user.is_active is True


# ============================================================================
# Document Schema Validation Tests
# ============================================================================


class TestDocSchemas:
    """Tests for document request/response schema validation."""

    def test_document_create_request(self):
        """Test valid document create request."""
        from app.schemas.doc_schema import DocumentCreateRequest

        data = DocumentCreateRequest(
            title="My Document",
            description="A test document",
            tags=["test", "unit"],
        )

        assert data.title == "My Document"
        assert data.tags == ["test", "unit"]

    def test_document_create_empty_title_rejected(self):
        """Test that empty title is rejected."""
        from pydantic import ValidationError
        from app.schemas.doc_schema import DocumentCreateRequest

        with pytest.raises(ValidationError):
            DocumentCreateRequest(
                title="",
                description="No title",
            )

    def test_document_update_request(self):
        """Test document update request (all fields optional)."""
        from app.schemas.doc_schema import DocumentUpdateRequest

        # All fields optional
        data = DocumentUpdateRequest(title="Updated Title")
        assert data.title == "Updated Title"
        assert data.description is None

        # Empty update
        data2 = DocumentUpdateRequest()
        assert data2.title is None

    def test_document_response(self):
        """Test document response schema."""
        from datetime import datetime
        from app.schemas.doc_schema import DocumentResponse

        doc = DocumentResponse(
            id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            title="Test Doc",
            file_name="test.pdf",
            status="completed",
            chunk_count=10,
            tags=["tag1"],
            created_at=datetime.utcnow(),
        )

        assert doc.title == "Test Doc"
        assert doc.chunk_count == 10
        assert doc.status == "completed"

    def test_document_list_params_defaults(self):
        """Test document list parameters defaults."""
        from app.schemas.doc_schema import DocumentListParams

        params = DocumentListParams()

        assert params.page == 1
        assert params.limit == 20
        assert params.sort_by == "created_at"
        assert params.sort_order == "desc"

    def test_document_list_params_validation(self):
        """Test document list parameters validation."""
        from pydantic import ValidationError
        from app.schemas.doc_schema import DocumentListParams

        # Invalid page
        with pytest.raises(ValidationError):
            DocumentListParams(page=0)

        # Invalid limit
        with pytest.raises(ValidationError):
            DocumentListParams(limit=101)


# ============================================================================
# RAG Schema Validation Tests
# ============================================================================


class TestRAGSchemas:
    """Tests for RAG request/response schema validation."""

    def test_rag_query_request(self):
        """Test valid RAG query request."""
        from app.schemas.rag_schema import RAGQueryRequest

        req = RAGQueryRequest(
            question="What is machine learning?",
            top_k=5,
            temperature=0.7,
        )

        assert req.question == "What is machine learning?"
        assert req.top_k == 5

    def test_search_request(self):
        """Test valid search request."""
        from app.schemas.rag_schema import SearchRequest

        req = SearchRequest(
            query="machine learning algorithms",
            top_k=10,
        )

        assert req.query == "machine learning algorithms"
        assert req.top_k == 10

    def test_tenant_create(self):
        """Test tenant create schema."""
        from app.schemas.rag_schema import TenantCreate

        tenant = TenantCreate(
            name="My Company",
            description="Test company tenant",
        )

        assert tenant.name == "My Company"

    def test_search_result_item(self):
        """Test search result item schema."""
        from app.schemas.rag_schema import SearchResultItem

        result = SearchResultItem(
            chunk_id="chunk_1",
            document_id="doc_1",
            content="Some relevant text",
            score=0.95,
            metadata={"chunk_index": 0},
        )

        assert result.score == 0.95
        assert result.content == "Some relevant text"


# ============================================================================
# Password Change Schema Tests
# ============================================================================


class TestPasswordChangeSchema:
    """Tests for password change schema."""

    def test_valid_password_change(self):
        """Test valid password change request."""
        from app.schemas.auth_schema import PasswordChangeRequest

        req = PasswordChangeRequest(
            current_password="OldPass123",
            new_password="NewStrongPass456",
        )

        assert req.current_password == "OldPass123"
        assert req.new_password == "NewStrongPass456"

    def test_weak_new_password_rejected(self):
        """Test that weak new password is rejected."""
        from pydantic import ValidationError
        from app.schemas.auth_schema import PasswordChangeRequest

        with pytest.raises(ValidationError):
            PasswordChangeRequest(
                current_password="OldPass123",
                new_password="weak",  # Too short and weak
            )
