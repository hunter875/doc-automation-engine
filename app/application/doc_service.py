"""Document management service."""

import hashlib
import io
import logging
import mimetypes
import os
import tempfile
import uuid
from datetime import datetime
from typing import BinaryIO, Optional

import boto3
from botocore.exceptions import ClientError
from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import (
    DocumentNotFoundError,
    FileValidationError,
    S3Error,
    StorageError,
)
from app.domain.models.document import Document, DocumentStatus
from app.schemas.doc_schema import (
    DocumentCreate,
    DocumentUpdate,
    PaginatedDocuments,
)

logger = logging.getLogger(__name__)

# Magic bytes for file type detection
MAGIC_BYTES = {
    b"%PDF": "application/pdf",
    b"PK\x03\x04": "application/vnd.openxmlformats-officedocument",
    b"\xd0\xcf\x11\xe0": "application/msword",
    b"{\n": "application/json",
    b"{\r\n": "application/json",
    b"[": "application/json",
}

# Allowed file extensions
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".md", ".json", ".csv"}

# Initialize S3/MinIO client
s3_client = boto3.client(
    "s3",
    endpoint_url=settings.S3_ENDPOINT_URL,
    aws_access_key_id=settings.S3_ACCESS_KEY,
    aws_secret_access_key=settings.S3_SECRET_KEY,
    region_name=settings.S3_REGION,
)


class DocumentService:
    """Service for document management operations."""

    def __init__(self, db: Session):
        self.db = db

    def validate_file(
        self,
        file_content: bytes,
        filename: str,
        max_size: int = None,
    ) -> str:
        """Validate uploaded file.

        Args:
            file_content: File content bytes
            filename: Original filename
            max_size: Maximum allowed size in bytes

        Returns:
            Detected MIME type

        Raises:
            FileValidationError: If validation fails
        """
        max_size = max_size or settings.MAX_FILE_SIZE

        # Check file size
        if len(file_content) > max_size:
            raise FileValidationError(
                message=f"File size exceeds maximum allowed ({max_size} bytes)",
            )

        # Check extension
        ext = os.path.splitext(filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise FileValidationError(
                message=f"File extension '{ext}' not allowed",
                supported_types=list(ALLOWED_EXTENSIONS),
            )

        # Detect MIME type from magic bytes
        mime_type = None
        for magic, detected_mime in MAGIC_BYTES.items():
            if file_content.startswith(magic):
                mime_type = detected_mime
                break

        # Fall back to mimetypes module
        if not mime_type:
            mime_type, _ = mimetypes.guess_type(filename)
            mime_type = mime_type or "application/octet-stream"

        return mime_type

    def calculate_checksum(self, file_content: bytes) -> str:
        """Calculate MD5 checksum of file content.

        Args:
            file_content: File content bytes

        Returns:
            MD5 hex digest
        """
        return hashlib.md5(file_content).hexdigest()

    def upload_to_s3(
        self,
        file_content: bytes,
        s3_key: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload file to S3/MinIO.

        Args:
            file_content: File content bytes
            s3_key: S3 object key
            content_type: File content type

        Returns:
            S3 URL

        Raises:
            S3Error: If upload fails
        """
        try:
            s3_client.put_object(
                Bucket=settings.S3_BUCKET_NAME,
                Key=s3_key,
                Body=file_content,
                ContentType=content_type,
            )

            url = f"{settings.S3_ENDPOINT_URL}/{settings.S3_BUCKET_NAME}/{s3_key}"
            logger.info(f"Uploaded file to S3: {s3_key}")
            return url

        except ClientError as e:
            logger.error(f"Failed to upload to S3: {e}")
            raise S3Error(
                message="Failed to upload file to storage",
                original_error=str(e),
            )

    def download_from_s3(self, s3_key: str) -> bytes:
        """Download file from S3/MinIO.

        Args:
            s3_key: S3 object key

        Returns:
            File content bytes

        Raises:
            S3Error: If download fails
        """
        try:
            response = s3_client.get_object(
                Bucket=settings.S3_BUCKET_NAME,
                Key=s3_key,
            )
            return response["Body"].read()

        except ClientError as e:
            logger.error(f"Failed to download from S3: {e}")
            raise S3Error(
                message="Failed to download file from storage",
                original_error=str(e),
            )

    def delete_from_s3(self, s3_key: str) -> bool:
        """Delete file from S3/MinIO.

        Args:
            s3_key: S3 object key

        Returns:
            True if deleted

        Raises:
            S3Error: If deletion fails
        """
        try:
            s3_client.delete_object(
                Bucket=settings.S3_BUCKET_NAME,
                Key=s3_key,
            )
            logger.info(f"Deleted file from S3: {s3_key}")
            return True

        except ClientError as e:
            logger.error(f"Failed to delete from S3: {e}")
            raise S3Error(
                message="Failed to delete file from storage",
                original_error=str(e),
            )

    def generate_s3_key(
        self,
        tenant_id: str,
        filename: str,
    ) -> str:
        """Generate S3 object key.

        Args:
            tenant_id: Tenant UUID
            filename: Original filename

        Returns:
            S3 object key
        """
        ext = os.path.splitext(filename)[1]
        unique_id = uuid.uuid4().hex[:8]
        timestamp = datetime.utcnow().strftime("%Y%m%d")
        safe_filename = f"{timestamp}_{unique_id}{ext}"
        return f"tenants/{tenant_id}/documents/{safe_filename}"

    def create_document(
        self,
        tenant_id: str,
        owner_id: str,
        filename: str,
        file_content: bytes,
        tags: Optional[list[str]] = None,
    ) -> Document:
        """Create a new document.

        Args:
            tenant_id: Tenant UUID
            owner_id: Owner user UUID
            filename: Original filename
            file_content: File content bytes
            tags: Optional document tags

        Returns:
            Created Document model

        Raises:
            FileValidationError: If file validation fails
            StorageError: If S3 upload fails
        """
        # Validate file
        mime_type = self.validate_file(file_content, filename)

        # Calculate checksum
        checksum = self.calculate_checksum(file_content)

        # Check for duplicate (same checksum in same tenant)
        existing = (
            self.db.query(Document)
            .filter(
                and_(
                    Document.tenant_id == tenant_id,
                    Document.checksum == checksum,
                )
            )
            .first()
        )

        if existing:
            logger.warning(f"Duplicate document detected: {existing.id}")
            return existing

        # Generate S3 key and upload
        s3_key = self.generate_s3_key(tenant_id, filename)
        self.upload_to_s3(file_content, s3_key, mime_type)

        # Create document record
        document = Document(
            tenant_id=tenant_id,
            uploaded_by=owner_id,
            file_name=filename,
            file_size_bytes=len(file_content),
            mime_type=mime_type,
            s3_key=s3_key,
            checksum=checksum,
            tags=tags or [],
            status=DocumentStatus.PENDING,
        )

        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)

        logger.info(f"Created document: {document.id}")
        return document

    def get_document(
        self,
        document_id: str,
        tenant_id: str,
    ) -> Document:
        """Get document by ID.

        Args:
            document_id: Document UUID
            tenant_id: Tenant UUID (for isolation)

        Returns:
            Document model

        Raises:
            DocumentNotFoundError: If document not found
        """
        document = (
            self.db.query(Document)
            .filter(
                and_(
                    Document.id == document_id,
                    Document.tenant_id == tenant_id,
                )
            )
            .first()
        )

        if not document:
            raise DocumentNotFoundError(document_id=document_id)

        return document

    def list_documents(
        self,
        tenant_id: str,
        page: int = 1,
        page_size: int = 20,
        status: Optional[DocumentStatus] = None,
        owner_id: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> PaginatedDocuments:
        """List documents with pagination.

        Args:
            tenant_id: Tenant UUID
            page: Page number (1-indexed)
            page_size: Items per page
            status: Filter by status
            owner_id: Filter by owner
            tag: Filter by tag

        Returns:
            PaginatedDocuments schema
        """
        query = self.db.query(Document).filter(
            Document.tenant_id == tenant_id,
        )

        # Apply filters
        if status:
            query = query.filter(Document.status == status)
        if owner_id:
            query = query.filter(Document.uploaded_by == owner_id)
        if tag:
            query = query.filter(Document.tags.contains([tag]))

        # Get total count
        total = query.count()

        # Apply pagination
        offset = (page - 1) * page_size
        documents = (
            query.order_by(Document.created_at.desc())
            .offset(offset)
            .limit(page_size)
            .all()
        )

        return PaginatedDocuments(
            items=documents,
            total=total,
            page=page,
            page_size=page_size,
            pages=(total + page_size - 1) // page_size,
        )

    def update_document(
        self,
        document_id: str,
        tenant_id: str,
        update_data: DocumentUpdate,
    ) -> Document:
        """Update document metadata.

        Args:
            document_id: Document UUID
            tenant_id: Tenant UUID
            update_data: Update data schema

        Returns:
            Updated Document model

        Raises:
            DocumentNotFoundError: If document not found
        """
        document = self.get_document(document_id, tenant_id)

        update_dict = update_data.model_dump(exclude_unset=True)
        for key, value in update_dict.items():
            setattr(document, key, value)

        self.db.commit()
        self.db.refresh(document)

        logger.info(f"Updated document: {document_id}")
        return document

    def update_document_status(
        self,
        document_id: str,
        status: DocumentStatus,
        chunk_count: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> Document:
        """Update document processing status.

        Args:
            document_id: Document UUID
            status: New status
            chunk_count: Number of chunks (if processed)
            error_message: Error message (if failed)

        Returns:
            Updated Document model
        """
        document = self.db.query(Document).filter(
            Document.id == document_id
        ).first()

        if not document:
            raise DocumentNotFoundError(document_id=document_id)

        document.status = status

        if chunk_count is not None:
            document.chunk_count = chunk_count

        if status in (DocumentStatus.PROCESSED, "completed", "processed"):
            document.processed_at = datetime.utcnow()

        if error_message:
            document.error_message = error_message
            logger.error(f"Document {document_id} processing failed: {error_message}")

        self.db.commit()
        self.db.refresh(document)

        return document

    def delete_document(
        self,
        document_id: str,
        tenant_id: str,
    ) -> bool:
        """Delete document and associated data.

        Args:
            document_id: Document UUID
            tenant_id: Tenant UUID

        Returns:
            True if deleted

        Raises:
            DocumentNotFoundError: If document not found
        """
        document = self.get_document(document_id, tenant_id)

        # Delete from S3
        try:
            self.delete_from_s3(document.s3_key)
        except S3Error as e:
            logger.warning(f"Failed to delete S3 object: {e}")

        # Delete database record
        self.db.delete(document)
        self.db.commit()

        logger.info(f"Deleted document: {document_id}")
        return True

    def get_document_content(
        self,
        document_id: str,
        tenant_id: str,
    ) -> tuple[bytes, str, str]:
        """Get document content from S3.

        Args:
            document_id: Document UUID
            tenant_id: Tenant UUID

        Returns:
            Tuple of (content_bytes, filename, mime_type)

        Raises:
            DocumentNotFoundError: If document not found
            S3Error: If download fails
        """
        document = self.get_document(document_id, tenant_id)
        content = self.download_from_s3(document.s3_key)
        return content, document.file_name, document.mime_type

    def get_tenant_stats(
        self,
        tenant_id: str,
    ) -> dict:
        """Get document statistics for tenant.

        Args:
            tenant_id: Tenant UUID

        Returns:
            Statistics dictionary
        """
        base_query = self.db.query(Document).filter(
            Document.tenant_id == tenant_id
        )

        total_docs = base_query.count()
        total_size = (
            self.db.query(func.sum(Document.file_size_bytes))
            .filter(Document.tenant_id == tenant_id)
            .scalar()
        ) or 0

        status_counts = {}
        for s in ["pending", "processing", "completed", "failed"]:
            count = base_query.filter(Document.status == s).count()
            status_counts[s] = count

        return {
            "total_documents": total_docs,
            "total_size_bytes": total_size,
            "status_counts": status_counts,
        }
