"""Integration test fixtures using PostgreSQL."""

import os
import uuid
from typing import Generator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.db.session import Base
import app.domain.models  # noqa: F401


@pytest.fixture(scope="session")
def pg_engine():
    """Create PostgreSQL test engine using TEST_DATABASE_URL."""
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL required for Postgres integration tests")

    assert url.startswith(
        ("postgresql://", "postgresql+psycopg2://", "postgresql+psycopg://")
    ), f"TEST_DATABASE_URL must be PostgreSQL, got: {url}"

    assert "test" in url.lower(), (
        f"Refusing to run destructive tests against non-test DB: {url}"
    )

    engine = create_engine(url, echo=False)

    # Verify connection and initialize schema once per session.
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    yield engine

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def pg_test_session(pg_engine) -> Generator[Session, None, None]:
    """Create a fresh database session for each test with transaction rollback."""
    connection = pg_engine.connect()
    transaction = connection.begin()

    SessionLocal = sessionmaker(bind=connection, autoflush=False, autocommit=False)
    session = SessionLocal()

    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()


@pytest.fixture
def test_tenant_pg(pg_test_session):
    """Create a test tenant in PostgreSQL."""
    from app.domain.models.tenant import Tenant

    tenant = Tenant(
        id=uuid.uuid4(),
        name="Test Tenant KV30",
        description="Test tenant for KV30 integration tests",
        billing_status="active",
    )
    pg_test_session.add(tenant)
    pg_test_session.commit()
    pg_test_session.refresh(tenant)
    return tenant


@pytest.fixture
def test_user_pg(pg_test_session):
    """Create a test user in PostgreSQL."""
    from app.core.security import get_password_hash
    from app.domain.models.user import User

    user = User(
        id=uuid.uuid4(),
        email="kv30test@example.com",
        password_hash=get_password_hash("TestPass123"),
        full_name="KV30 Test User",
        is_active=True,
    )
    pg_test_session.add(user)
    pg_test_session.commit()
    pg_test_session.refresh(user)
    return user


@pytest.fixture
def test_template_pg(pg_test_session, test_tenant_pg, test_user_pg):
    """Create a test extraction template in PostgreSQL."""
    from app.domain.models.extraction_job import ExtractionTemplate

    template = ExtractionTemplate(
        id=uuid.uuid4(),
        tenant_id=test_tenant_pg.id,
        name="KV30 Test Template",
        description="Test template for KV30 ingestion",
        schema_definition={"fields": []},
        aggregation_rules={},
        extraction_mode="block",
        google_sheet_id="test_sheet_id",
        google_sheet_worksheet="BC NGAY",
        google_sheet_range="A1:ZZZ",
        google_sheet_schema_path="bc_ngay_kv30_schema.yaml",
        google_sheet_configs=[
            {"worksheet": "BC NGAY", "schema_path": "bc_ngay_kv30_schema.yaml"},
            {"worksheet": "VU CHAY THONG KE", "schema_path": "vu_chay_kv30_schema.yaml"},
            {"worksheet": "CHI VIEN", "schema_path": "chi_vien_kv30_schema.yaml"},
            {"worksheet": "CNCH", "schema_path": "cnch_kv30_schema.yaml"},
            {"worksheet": "SCLQ DEN PCCC&CNCH", "schema_path": "sclq_kv30_schema.yaml"},
        ],
        created_by=test_user_pg.id,
        is_active=True,
    )
    pg_test_session.add(template)
    pg_test_session.commit()
    pg_test_session.refresh(template)
    return template


@pytest.fixture
def test_document_pg(pg_test_session, test_tenant_pg, test_user_pg):
    """Create a test source document in PostgreSQL."""
    from app.domain.models.document import Document

    document = Document(
        id=uuid.uuid4(),
        tenant_id=test_tenant_pg.id,
        uploaded_by=test_user_pg.id,
        file_name="kv30_test_sheet.json",
        file_size_bytes=1024,
        mime_type="application/json",
        s3_key="test/kv30_sheet.json",
        checksum="test_checksum_kv30",
        status="completed",
        tags=[],
    )
    pg_test_session.add(document)
    pg_test_session.commit()
    pg_test_session.refresh(document)
    return document
