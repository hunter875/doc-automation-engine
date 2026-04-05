"""Unit tests for document service."""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.core.exceptions import (
    DocumentNotFoundError,
)
from app.domain.models.document import Document
from app.domain.models.tenant import Tenant


# ============================================================================
# Document Model Tests
# ============================================================================


class TestDocumentModel:
    """Tests for Document model."""

    def test_create_document(self, db_session, test_tenant, test_user):
        """Test creating a document in the database."""
        doc = Document(
            id=uuid.uuid4(),
            tenant_id=test_tenant.id,
            title="Test Document",
            file_name="test.pdf",
            file_size_bytes=1024,
            mime_type="application/pdf",
            s3_key=f"tenants/{test_tenant.id}/documents/test.pdf",
            status="pending",
            uploaded_by=test_user.id,
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        assert doc.id is not None
        assert doc.title == "Test Document"
        assert doc.status == "pending"
        assert doc.file_name == "test.pdf"
        assert doc.file_size_bytes == 1024

    def test_document_status_properties(self, db_session, test_tenant):
        """Test document status helper properties."""
        doc = Document(
            id=uuid.uuid4(),
            tenant_id=test_tenant.id,
            title="Status Test",
            file_name="test.txt",
            status="pending",
        )
        db_session.add(doc)
        db_session.commit()

        assert doc.is_processing is False
        assert doc.is_completed is False
        assert doc.is_failed is False

        doc.status = "processing"
        assert doc.is_processing is True

        doc.status = "completed"
        assert doc.is_completed is True

        doc.status = "failed"
        assert doc.is_failed is True

    def test_document_default_values(self, db_session, test_tenant):
        """Test document default field values."""
        doc = Document(
            id=uuid.uuid4(),
            tenant_id=test_tenant.id,
            title="Defaults Test",
            file_name="test.txt",
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        assert doc.status == "pending"
        assert doc.chunk_count == 0
        assert doc.created_at is not None

    def test_document_repr(self, db_session, test_tenant):
        """Test document string representation."""
        doc = Document(
            id=uuid.uuid4(),
            tenant_id=test_tenant.id,
            title="Repr Test",
            file_name="test.txt",
            status="pending",
        )

        assert "Repr Test" in repr(doc)
        assert "pending" in repr(doc)


# ============================================================================
# Document CRUD Tests (with mocked S3)
# ============================================================================


class TestDocumentCRUD:
    """Tests for document CRUD operations against database."""

    def test_create_and_retrieve_document(self, db_session, test_tenant, test_user):
        """Test creating and then querying a document."""
        doc_id = uuid.uuid4()
        doc = Document(
            id=doc_id,
            tenant_id=test_tenant.id,
            title="Retrieve Test",
            file_name="retrieve.pdf",
            uploaded_by=test_user.id,
            status="pending",
        )
        db_session.add(doc)
        db_session.commit()

        # Query it back
        found = db_session.query(Document).filter(Document.id == doc_id).first()

        assert found is not None
        assert found.title == "Retrieve Test"
        assert found.tenant_id == test_tenant.id

    def test_list_documents_by_tenant(self, db_session, test_tenant):
        """Test listing documents filtered by tenant."""
        other_tenant_id = uuid.uuid4()

        # Create docs for test tenant
        for i in range(3):
            doc = Document(
                id=uuid.uuid4(),
                tenant_id=test_tenant.id,
                title=f"Tenant Doc {i}",
                file_name=f"doc_{i}.txt",
                status="pending",
            )
            db_session.add(doc)

        # Create doc for another tenant
        other_doc = Document(
            id=uuid.uuid4(),
            tenant_id=other_tenant_id,
            title="Other Tenant Doc",
            file_name="other.txt",
            status="pending",
        )
        db_session.add(other_doc)
        db_session.commit()

        # Query by tenant
        docs = (
            db_session.query(Document)
            .filter(Document.tenant_id == test_tenant.id)
            .all()
        )

        assert len(docs) >= 3
        for doc in docs:
            assert doc.tenant_id == test_tenant.id

    def test_update_document_status(self, db_session, test_tenant):
        """Test updating document status."""
        doc_id = uuid.uuid4()
        doc = Document(
            id=doc_id,
            tenant_id=test_tenant.id,
            title="Status Update",
            file_name="status.txt",
            status="pending",
        )
        db_session.add(doc)
        db_session.commit()

        # Update status
        doc.status = "processing"
        db_session.commit()

        refreshed = db_session.query(Document).filter(Document.id == doc_id).first()
        assert refreshed.status == "processing"

        # Update to completed with chunk count
        refreshed.status = "completed"
        refreshed.chunk_count = 15
        db_session.commit()

        final = db_session.query(Document).filter(Document.id == doc_id).first()
        assert final.status == "completed"
        assert final.chunk_count == 15

    def test_delete_document(self, db_session, test_tenant):
        """Test deleting a document."""
        doc_id = uuid.uuid4()
        doc = Document(
            id=doc_id,
            tenant_id=test_tenant.id,
            title="Delete Test",
            file_name="delete.txt",
            status="pending",
        )
        db_session.add(doc)
        db_session.commit()

        # Delete
        db_session.delete(doc)
        db_session.commit()

        # Verify deleted
        found = db_session.query(Document).filter(Document.id == doc_id).first()
        assert found is None

    def test_filter_by_status(self, db_session, test_tenant):
        """Test filtering documents by status."""
        statuses = ["pending", "processing", "completed", "failed"]

        for status in statuses:
            doc = Document(
                id=uuid.uuid4(),
                tenant_id=test_tenant.id,
                title=f"Status {status}",
                file_name=f"{status}.txt",
                status=status,
            )
            db_session.add(doc)
        db_session.commit()

        completed = (
            db_session.query(Document)
            .filter(
                Document.tenant_id == test_tenant.id,
                Document.status == "completed",
            )
            .all()
        )

        assert len(completed) >= 1
        for doc in completed:
            assert doc.status == "completed"


# ============================================================================
# Tenant Isolation Tests
# ============================================================================


class TestTenantIsolation:
    """Tests to verify multi-tenant data isolation."""

    def test_documents_isolated_by_tenant(self, db_session):
        """Test that documents are properly isolated between tenants."""
        tenant_a_id = uuid.uuid4()
        tenant_b_id = uuid.uuid4()

        # Create docs for tenant A
        doc_a = Document(
            id=uuid.uuid4(),
            tenant_id=tenant_a_id,
            title="Tenant A Secret Doc",
            file_name="secret_a.pdf",
            status="completed",
        )
        db_session.add(doc_a)

        # Create docs for tenant B
        doc_b = Document(
            id=uuid.uuid4(),
            tenant_id=tenant_b_id,
            title="Tenant B Secret Doc",
            file_name="secret_b.pdf",
            status="completed",
        )
        db_session.add(doc_b)
        db_session.commit()

        # Tenant A should only see their docs
        docs_a = (
            db_session.query(Document)
            .filter(Document.tenant_id == tenant_a_id)
            .all()
        )
        assert len(docs_a) == 1
        assert docs_a[0].title == "Tenant A Secret Doc"

        # Tenant B should only see their docs
        docs_b = (
            db_session.query(Document)
            .filter(Document.tenant_id == tenant_b_id)
            .all()
        )
        assert len(docs_b) == 1
        assert docs_b[0].title == "Tenant B Secret Doc"

    def test_cannot_access_other_tenant_document(self, db_session):
        """Test that querying with wrong tenant_id returns nothing."""
        real_tenant_id = uuid.uuid4()
        wrong_tenant_id = uuid.uuid4()

        doc = Document(
            id=uuid.uuid4(),
            tenant_id=real_tenant_id,
            title="Protected Doc",
            file_name="protected.pdf",
            status="completed",
        )
        db_session.add(doc)
        db_session.commit()

        # Try to access with wrong tenant ID
        result = (
            db_session.query(Document)
            .filter(
                Document.id == doc.id,
                Document.tenant_id == wrong_tenant_id,
            )
            .first()
        )

        assert result is None  # Should not be accessible
