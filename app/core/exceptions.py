"""Custom exceptions for the RAG application."""

from typing import Any, Optional


class RAGException(Exception):
    """Base exception for RAG application."""

    status_code: int = 500

    def __init__(
        self,
        message: str,
        code: str,
        details: Optional[dict[str, Any]] = None,
    ):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(self.message)


# Authentication Exceptions
class AuthenticationError(RAGException):
    """Raised when authentication fails."""
    status_code = 401

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message=message, code="AUTHENTICATION_ERROR")


class InvalidCredentialsError(RAGException):
    """Raised when credentials are invalid."""
    status_code = 401

    def __init__(self, message: str = "Invalid email or password"):
        super().__init__(message=message, code="INVALID_CREDENTIALS")


class TokenExpiredError(RAGException):
    """Raised when token has expired."""
    status_code = 401

    def __init__(self, message: str = "Token has expired"):
        super().__init__(message=message, code="TOKEN_EXPIRED")


class TokenInvalidError(RAGException):
    """Raised when token is invalid."""
    status_code = 401

    def __init__(self, message: str = "Invalid token"):
        super().__init__(message=message, code="TOKEN_INVALID")


# Authorization Exceptions
class PermissionDeniedError(RAGException):
    """Raised when user lacks required permissions."""
    status_code = 403

    def __init__(
        self,
        message: str = "Permission denied",
        required_role: Optional[str] = None,
    ):
        details = {}
        if required_role:
            details["required_role"] = required_role
        super().__init__(message=message, code="PERMISSION_DENIED", details=details)


# Resource Exceptions
class ResourceNotFoundError(RAGException):
    """Raised when a resource is not found."""
    status_code = 404

    def __init__(
        self,
        resource_type: str,
        resource_id: str,
    ):
        message = f"{resource_type} with id '{resource_id}' not found"
        super().__init__(
            message=message,
            code=f"{resource_type.upper()}_NOT_FOUND",
            details={"resource_type": resource_type, "resource_id": resource_id},
        )


class TenantNotFoundError(ResourceNotFoundError):
    """Raised when tenant is not found."""

    def __init__(self, tenant_id: str):
        super().__init__(resource_type="Tenant", resource_id=tenant_id)


class DocumentNotFoundError(ResourceNotFoundError):
    """Raised when document is not found."""

    def __init__(self, document_id: str):
        super().__init__(resource_type="Document", resource_id=document_id)


class UserNotFoundError(ResourceNotFoundError):
    """Raised when user is not found."""

    def __init__(self, user_id: str):
        super().__init__(resource_type="User", resource_id=user_id)


class ResourceAlreadyExistsError(RAGException):
    """Raised when a resource already exists."""
    status_code = 409

    def __init__(self, resource_type: str = "Resource", detail: str = None):
        message = f"{resource_type} already exists"
        if detail:
            message = detail
        super().__init__(
            message=message,
            code="RESOURCE_ALREADY_EXISTS",
            details={"resource_type": resource_type},
        )


# File Exceptions
class FileValidationError(RAGException):
    """Base exception for file validation errors."""
    status_code = 400

    def __init__(self, message: str = "File validation failed", code: str = "FILE_VALIDATION_ERROR", details=None):
        super().__init__(message=message, code=code, details=details)


class FileTooLargeError(FileValidationError):
    """Raised when file exceeds size limit."""

    def __init__(self, max_size_mb: int = 10):
        super().__init__(
            message=f"File exceeds maximum size of {max_size_mb}MB",
            code="FILE_TOO_LARGE",
            details={"max_size_mb": max_size_mb},
        )


class UnsupportedFileTypeError(FileValidationError):
    """Raised when file type is not supported."""

    def __init__(self, mime_type: str, allowed_types: list[str] = None):
        super().__init__(
            message=f"File type '{mime_type}' is not supported",
            code="UNSUPPORTED_FILE_TYPE",
            details={
                "mime_type": mime_type,
                "allowed_types": allowed_types or [],
            },
        )


class CorruptedFileError(FileValidationError):
    """Raised when file is corrupted or unreadable."""

    def __init__(self, message: str = "File is corrupted or cannot be read"):
        super().__init__(message=message, code="CORRUPTED_FILE")


# Processing Exceptions
class ProcessingError(RAGException):
    """Raised when document processing fails."""
    status_code = 422

    def __init__(self, message: str = "Processing failed", document_id: str = None, reason: str = None):
        details = {}
        if document_id:
            details["document_id"] = document_id
        if reason:
            details["reason"] = reason
            message = f"Failed to process document: {reason}"
        super().__init__(
            message=message,
            code="PROCESSING_ERROR",
            details=details,
        )


# External Service Exceptions
class ExternalServiceError(RAGException):
    """Raised when an external service fails."""
    status_code = 502

    def __init__(self, message: str = "External service error", code: str = "EXTERNAL_SERVICE_ERROR", details=None):
        super().__init__(message=message, code=code, details=details)


class OpenAIError(ExternalServiceError):
    """Raised when OpenAI API call fails."""

    def __init__(self, message: str = "OpenAI API error", original_error: str = None):
        super().__init__(
            message=message,
            code="OPENAI_ERROR",
            details={"original_error": original_error} if original_error else {},
        )


class VectorStoreError(ExternalServiceError):
    """Raised when vector store (pgvector) operation fails."""

    def __init__(self, message: str = "Vector store error", original_error: str = None):
        super().__init__(
            message=message,
            code="VECTOR_STORE_ERROR",
            details={"original_error": original_error} if original_error else {},
        )


class StorageError(ExternalServiceError):
    """Raised when storage operation fails."""

    def __init__(self, message: str = "Storage error", original_error: str = None):
        super().__init__(
            message=message,
            code="STORAGE_ERROR",
            details={"original_error": original_error} if original_error else {},
        )


# Alias for S3/MinIO storage errors
S3Error = StorageError


# Extraction Exceptions (Engine 2)
class ExtractionError(RAGException):
    """Raised when extraction processing fails."""
    status_code = 422

    def __init__(self, message: str = "Extraction failed", details: dict = None):
        super().__init__(message=message, code="EXTRACTION_ERROR", details=details)


class SchemaValidationError(RAGException):
    """Raised when template schema definition is invalid."""
    status_code = 400

    def __init__(self, message: str = "Invalid schema definition", details: dict = None):
        super().__init__(message=message, code="SCHEMA_VALIDATION_ERROR", details=details)


# Rate Limiting
class RateLimitError(RAGException):
    """Raised when rate limit is exceeded."""
    status_code = 429

    def __init__(self, retry_after: int = 60):
        super().__init__(
            message="Rate limit exceeded. Please try again later.",
            code="RATE_LIMITED",
            details={"retry_after": retry_after},
        )


# Service Availability
class ServiceUnavailableError(RAGException):
    """Raised when service is temporarily unavailable."""
    status_code = 503

    def __init__(self, message: str = "Service temporarily unavailable"):
        super().__init__(message=message, code="SERVICE_UNAVAILABLE")
