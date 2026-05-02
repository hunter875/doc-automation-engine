"""Pytest configuration and shared fixtures."""

import os
import uuid
from datetime import datetime
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, event, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.types import TypeDecorator

# Override settings before importing app modules
os.environ["SECRET_KEY"] = "test-secret-key-for-unit-tests-only"
os.environ["POSTGRES_HOST"] = "localhost"
os.environ["POSTGRES_PORT"] = "5432"
os.environ["POSTGRES_USER"] = "test"
os.environ["POSTGRES_PASSWORD"] = "test"
os.environ["POSTGRES_DB"] = "test_rag"
os.environ["REDIS_HOST"] = "localhost"

from app.infrastructure.db.session import Base

# Ensure all SQLAlchemy models are registered on Base.metadata before create_all
import app.domain.models  # noqa: F401


# ============================================================================
# PostgreSQL Test Fixtures (for integration tests)
# ============================================================================

@pytest.fixture(scope="session")
def pg_test_engine():
    """PostgreSQL test engine for integration tests."""
    test_db_url = os.getenv("TEST_DATABASE_URL")

    if not test_db_url:
        pytest.skip("TEST_DATABASE_URL required for Postgres integration tests")

    assert test_db_url.startswith(
        ("postgresql://", "postgresql+psycopg2://", "postgresql+psycopg://")
    ), f"TEST_DATABASE_URL must be PostgreSQL, got: {test_db_url}"

    assert "rag_test" in test_db_url.lower(), (
        f"Refusing to run destructive tests against non-test DB: {test_db_url}"
    )

    engine = create_engine(test_db_url)

    yield engine

    engine.dispose()


@pytest.fixture
def pg_test_session(pg_test_engine) -> Generator[Session, None, None]:
    """PostgreSQL test session with clean schema per test."""
    Base.metadata.drop_all(bind=pg_test_engine)
    Base.metadata.create_all(bind=pg_test_engine)

    SessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=pg_test_engine,
    )

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=pg_test_engine)


# ============================================================================
# SQLite Type Compatibility Shims (for unit tests)
# ============================================================================

class SQLiteARRAY(TypeDecorator):
    """SQLite-compatible ARRAY type using JSON serialization."""
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        import json
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return []
        import json
        return json.loads(value)


class SQLiteJSONB(TypeDecorator):
    """SQLite-compatible JSONB type using JSON serialization."""
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        import json
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        import json
        return json.loads(value)


class SQLiteUUID(TypeDecorator):
    """SQLite-compatible UUID type using string storage."""
    impl = String(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        import uuid
        if isinstance(value, uuid.UUID):
            return str(value)
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        import uuid
        return uuid.UUID(value)


@compiles(ARRAY, "sqlite")
def compile_array_sqlite(type_, compiler, **kw):
    return "TEXT"


@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "TEXT"


@compiles(PG_UUID, "sqlite")
def compile_uuid_sqlite(type_, compiler, **kw):
    return "VARCHAR(36)"


# ============================================================================
# Database Fixtures (SQLite in-memory for tests)
# ============================================================================

@pytest.fixture(scope="session")
def sqlite_test_engine():
    """Create test database engine using SQLite in-memory."""
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )

    # Enable foreign keys in SQLite
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    assert "users" in Base.metadata.tables
    assert "tenants" in Base.metadata.tables
    assert "extraction_templates" in Base.metadata.tables
    assert "extraction_jobs" in Base.metadata.tables
    # Create all tables
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session(sqlite_test_engine) -> Generator[Session, None, None]:
    """Create a fresh database session for each test."""
    TestSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=sqlite_test_engine,
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
def mock_s3():
    """Mock S3/MinIO client."""
    with patch("app.application.doc_service.s3_client") as mock:
        mock.put_object.return_value = {}
        mock.get_object.return_value = {
            "Body": MagicMock(read=lambda: b"test file content")
        }
        mock.delete_object.return_value = {}
        yield mock
