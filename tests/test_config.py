"""Unit tests for configuration and exceptions."""

import os

import pytest


# ============================================================================
# Configuration Tests
# ============================================================================


class TestSettings:
    """Tests for application configuration."""

    def test_settings_load(self):
        """Test that settings can be loaded."""
        from app.core.config import settings

        assert settings is not None
        assert settings.APP_NAME is not None

    def test_settings_defaults(self):
        """Test default setting values."""
        from app.core.config import settings

        assert settings.ALGORITHM == "HS256"
        assert settings.ACCESS_TOKEN_EXPIRE_MINUTES == 30
        assert settings.CHUNK_SIZE == 500
        assert settings.CHUNK_OVERLAP == 50
        assert settings.EMBEDDING_DIMENSION == 1536
        assert settings.EMBEDDING_BATCH_SIZE == 100

    def test_database_url_format(self):
        """Test DATABASE_URL is properly formatted."""
        from app.core.config import settings

        url = settings.DATABASE_URL
        assert url.startswith("postgresql://")
        assert "@" in url

    def test_embedding_dimension_default(self):
        """Test EMBEDDING_DIMENSION has a sensible default."""
        from app.core.config import settings

        assert settings.EMBEDDING_DIMENSION > 0
        assert settings.EMBEDDING_DIMENSION == 1536

    def test_redis_url_format(self):
        """Test REDIS_URL is properly formatted."""
        from app.core.config import settings

        url = settings.REDIS_URL
        assert url.startswith("redis://")

    def test_settings_singleton(self):
        """Test that settings is a cached singleton."""
        from app.core.config import get_settings

        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2


# ============================================================================
# Exception Tests
# ============================================================================


class TestExceptions:
    """Tests for custom exceptions."""

    def test_rag_exception_base(self):
        """Test base RAG exception."""
        from app.core.exceptions import RAGException

        exc = RAGException(
            message="Test error",
            code="TEST_ERROR",
            details={"key": "value"},
        )

        assert str(exc) == "Test error"
        assert exc.message == "Test error"
        assert exc.code == "TEST_ERROR"
        assert exc.details == {"key": "value"}

    def test_authentication_error(self):
        """Test authentication error."""
        from app.core.exceptions import AuthenticationError

        exc = AuthenticationError()
        assert exc.code == "AUTHENTICATION_ERROR"
        assert "Authentication" in exc.message

    def test_invalid_credentials_error(self):
        """Test invalid credentials error."""
        from app.core.exceptions import InvalidCredentialsError

        exc = InvalidCredentialsError()
        assert exc.code == "INVALID_CREDENTIALS"

        # Custom message
        exc2 = InvalidCredentialsError("Custom message")
        assert exc2.message == "Custom message"

    def test_token_expired_error(self):
        """Test token expired error."""
        from app.core.exceptions import TokenExpiredError

        exc = TokenExpiredError()
        assert exc.code == "TOKEN_EXPIRED"

    def test_permission_denied_error(self):
        """Test permission denied error."""
        from app.core.exceptions import PermissionDeniedError

        exc = PermissionDeniedError(required_role="admin")
        assert exc.code == "PERMISSION_DENIED"
        assert exc.details["required_role"] == "admin"

    def test_resource_not_found_error(self):
        """Test resource not found error."""
        from app.core.exceptions import ResourceNotFoundError

        exc = ResourceNotFoundError(
            resource_type="Document",
            resource_id="abc-123",
        )
        assert "Document" in exc.message
        assert "abc-123" in exc.message
        assert exc.code == "DOCUMENT_NOT_FOUND"

    def test_tenant_not_found_error(self):
        """Test tenant not found error."""
        from app.core.exceptions import TenantNotFoundError

        exc = TenantNotFoundError("tenant-456")
        assert "Tenant" in exc.message
        assert "tenant-456" in exc.message

    def test_document_not_found_error(self):
        """Test document not found error."""
        from app.core.exceptions import DocumentNotFoundError

        exc = DocumentNotFoundError("doc-789")
        assert "Document" in exc.message
        assert "doc-789" in exc.message

    def test_user_not_found_error(self):
        """Test user not found error."""
        from app.core.exceptions import UserNotFoundError

        exc = UserNotFoundError("user-111")
        assert "User" in exc.message
        assert "user-111" in exc.message

    def test_exception_inheritance(self):
        """Test exception class hierarchy."""
        from app.core.exceptions import (
            AuthenticationError,
            DocumentNotFoundError,
            InvalidCredentialsError,
            RAGException,
            ResourceNotFoundError,
            TenantNotFoundError,
            UserNotFoundError,
        )

        assert issubclass(AuthenticationError, RAGException)
        assert issubclass(InvalidCredentialsError, RAGException)
        assert issubclass(ResourceNotFoundError, RAGException)
        assert issubclass(DocumentNotFoundError, ResourceNotFoundError)
        assert issubclass(TenantNotFoundError, ResourceNotFoundError)
        assert issubclass(UserNotFoundError, ResourceNotFoundError)

    def test_exceptions_are_catchable_as_base(self):
        """Test that specific exceptions can be caught as base."""
        from app.core.exceptions import (
            DocumentNotFoundError,
            RAGException,
        )

        with pytest.raises(RAGException):
            raise DocumentNotFoundError("doc-1")


# ============================================================================
# User Model Tests
# ============================================================================


class TestUserModel:
    """Tests for User SQLAlchemy model."""

    def test_create_user(self, db_session):
        """Test creating a user."""
        import uuid
        from app.models.user import User

        user = User(
            id=uuid.uuid4(),
            email="modeltest@example.com",
            password_hash="$2b$12$hashedvalue",
            full_name="Model Test",
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert user.id is not None
        assert user.email == "modeltest@example.com"
        assert user.is_active is True
        assert user.created_at is not None

    def test_user_repr(self, db_session):
        """Test User string representation."""
        import uuid
        from app.models.user import User

        user = User(
            id=uuid.uuid4(),
            email="repr@example.com",
            password_hash="hash",
        )

        assert "repr@example.com" in repr(user)


# ============================================================================
# Tenant Model Tests
# ============================================================================


class TestTenantModel:
    """Tests for Tenant SQLAlchemy model."""

    def test_create_tenant(self, db_session):
        """Test creating a tenant."""
        import uuid
        from app.models.tenant import Tenant

        tenant = Tenant(
            id=uuid.uuid4(),
            name="Model Test Tenant",
            description="Testing tenant model",
            billing_status="active",
        )
        db_session.add(tenant)
        db_session.commit()
        db_session.refresh(tenant)

        assert tenant.id is not None
        assert tenant.name == "Model Test Tenant"
        assert tenant.billing_status == "active"

    def test_tenant_repr(self):
        """Test Tenant string representation."""
        import uuid
        from app.models.tenant import Tenant

        tenant = Tenant(
            id=uuid.uuid4(),
            name="Repr Tenant",
        )

        assert "Repr Tenant" in repr(tenant)

    def test_user_tenant_role(self, db_session, test_user, test_tenant):
        """Test creating user-tenant role."""
        import uuid
        from app.models.tenant import UserTenantRole

        role = UserTenantRole(
            id=uuid.uuid4(),
            user_id=test_user.id,
            tenant_id=test_tenant.id,
            role="admin",
        )
        db_session.add(role)
        db_session.commit()
        db_session.refresh(role)

        assert role.role == "admin"
        assert role.user_id == test_user.id
        assert role.tenant_id == test_tenant.id

    def test_role_repr(self, test_user, test_tenant):
        """Test UserTenantRole string representation."""
        import uuid
        from app.models.tenant import UserTenantRole

        role = UserTenantRole(
            id=uuid.uuid4(),
            user_id=test_user.id,
            tenant_id=test_tenant.id,
            role="viewer",
        )

        repr_str = repr(role)
        assert "viewer" in repr_str
