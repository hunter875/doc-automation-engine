# 🛠 Development Guide - Enterprise Multi-Tenant RAG

> Hướng dẫn chi tiết cho developers tham gia phát triển hệ thống RAG.

---

## 📑 Mục Lục

- [Thiết Lập Môi Trường](#-thiết-lập-môi-trường)
- [Cấu Trúc Project](#-cấu-trúc-project)
- [Coding Standards](#-coding-standards)
- [Development Workflow](#-development-workflow)
- [Testing](#-testing)
- [Debugging](#-debugging)
- [Common Patterns](#-common-patterns)
- [Best Practices](#-best-practices)

---

## 🚀 Thiết Lập Môi Trường

### Prerequisites

```bash
# Kiểm tra versions
python --version  # >= 3.10
docker --version  # >= 24.0
docker-compose --version  # >= 2.20
```

### 1. Clone Repository

```bash
git clone https://github.com/your-org/ragPJ.git
cd ragPJ
```

### 2. Tạo Virtual Environment

```bash
# Tạo venv
python -m venv venv

# Activate
source venv/bin/activate  # Linux/Mac
# hoặc
.\venv\Scripts\activate   # Windows

# Verify
which python
```

### 3. Install Dependencies

```bash
# Install production dependencies
pip install -r requirements.txt

# Install development dependencies
pip install -r requirements-dev.txt

# Hoặc install all
pip install -r requirements.txt -r requirements-dev.txt
```

### 4. Setup Pre-commit Hooks

```bash
# Install pre-commit
pip install pre-commit

# Setup hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

### 5. Cấu Hình Environment

```bash
# Copy template
cp .env.example .env

# Edit với editor
nano .env
```

**.env cho development:**
```bash
# Application
APP_ENV=development
DEBUG=true
SECRET_KEY=dev-secret-key-not-for-production

# PostgreSQL (Docker)
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=raguser
POSTGRES_PASSWORD=ragpassword
POSTGRES_DB=ragdb

# OpenSearch (Docker)
OPENSEARCH_HOST=localhost
OPENSEARCH_PORT=9200

# Redis (Docker)
REDIS_HOST=localhost
REDIS_PORT=6379

# MinIO (Docker)
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=rag-documents

# OpenAI (Lấy từ https://platform.openai.com)
OPENAI_API_KEY=sk-your-api-key
```

### 6. Start Infrastructure Services

```bash
# Start PostgreSQL, Redis, OpenSearch, MinIO
docker-compose up -d postgres redis opensearch minio

# Verify services
docker-compose ps

# Check logs nếu có vấn đề
docker-compose logs opensearch
```

### 7. Database Setup

```bash
# Run migrations
alembic upgrade head

# Hoặc tạo migration mới
alembic revision --autogenerate -m "Add new table"
```

### 8. Run Application

```bash
# Development mode với auto-reload
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Hoặc với debugger
python -m debugpy --listen 5678 -m uvicorn app.main:app --reload
```

### 9. Start Celery Worker (Terminal khác)

```bash
# Start worker
celery -A app.worker.celery_app worker --loglevel=debug

# Start beat (scheduler) nếu cần
celery -A app.worker.celery_app beat --loglevel=debug
```

### 10. Verify Setup

```bash
# Check API
curl http://localhost:8000/health

# Check OpenAPI docs
open http://localhost:8000/docs
```

---

## 📁 Cấu Trúc Project

```
ragPJ/
├── app/                          # Main application code
│   ├── __init__.py
│   ├── main.py                   # FastAPI app initialization
│   │
│   ├── api/                      # API layer
│   │   ├── __init__.py
│   │   ├── dependencies.py       # Shared dependencies (auth, db)
│   │   └── v1/                   # API version 1
│   │       ├── __init__.py
│   │       ├── auth.py           # Auth endpoints
│   │       ├── document.py       # Document endpoints
│   │       ├── rag.py            # RAG query endpoints
│   │       └── tenant.py         # Tenant endpoints
│   │
│   ├── core/                     # Core configurations
│   │   ├── __init__.py
│   │   ├── config.py             # Settings (Pydantic BaseSettings)
│   │   ├── exceptions.py         # Custom exceptions
│   │   └── security.py           # JWT, password hashing
│   │
│   ├── db/                       # Database connections
│   │   ├── __init__.py
│   │   ├── postgres.py           # SQLAlchemy setup
│   │   └── opensearch.py         # OpenSearch client
│   │
│   ├── models/                   # SQLAlchemy models
│   │   ├── __init__.py
│   │   ├── base.py               # Base model class
│   │   ├── user.py               # User model
│   │   ├── tenant.py             # Tenant model
│   │   └── document.py           # Document model
│   │
│   ├── schemas/                  # Pydantic schemas
│   │   ├── __init__.py
│   │   ├── auth_schema.py        # Auth request/response
│   │   ├── doc_schema.py         # Document schemas
│   │   └── rag_schema.py         # RAG query schemas
│   │
│   ├── services/                 # Business logic layer
│   │   ├── __init__.py
│   │   ├── auth_service.py       # Authentication logic
│   │   ├── doc_service.py        # Document processing
│   │   ├── rag_service.py        # RAG pipeline
│   │   ├── chunking.py           # Text chunking
│   │   └── embedding.py          # OpenAI embeddings
│   │
│   └── worker/                   # Celery background tasks
│       ├── __init__.py
│       ├── celery_app.py         # Celery configuration
│       └── tasks.py              # Task definitions
│
├── tests/                        # Test files
│   ├── __init__.py
│   ├── conftest.py               # Pytest fixtures
│   ├── test_auth.py
│   ├── test_documents.py
│   └── test_rag.py
│
├── alembic/                      # Database migrations
│   ├── versions/
│   ├── env.py
│   └── alembic.ini
│
├── scripts/                      # Utility scripts
│   ├── init-db.sql
│   └── seed_data.py
│
├── docs/                         # Documentation
│   ├── API_REFERENCE.md
│   ├── DEPLOYMENT.md
│   └── DEVELOPMENT.md
│
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── requirements-dev.txt
├── .env.example
├── .pre-commit-config.yaml
├── pyproject.toml
└── README.md
```

### Layer Responsibilities

```
┌─────────────────────────────────────────────────────────────┐
│                        API Layer                             │
│   • Nhận HTTP requests                                       │
│   • Validate input (Pydantic schemas)                        │
│   • Call services                                            │
│   • Return HTTP responses                                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      Service Layer                           │
│   • Business logic                                           │
│   • Orchestration                                            │
│   • Transaction management                                   │
│   • External API calls (OpenAI)                              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      Data Layer                              │
│   • SQLAlchemy models (PostgreSQL)                          │
│   • OpenSearch client                                        │
│   • S3/MinIO client                                          │
│   • Redis client                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 📏 Coding Standards

### Python Style Guide

Sử dụng **PEP 8** với một số customizations:

```python
# Line length: 100 characters max
# Use Black for formatting
# Use isort for import sorting
```

### Type Hints

**Bắt buộc** cho tất cả functions:

```python
# ✅ Good
def get_user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email).first()

# ❌ Bad
def get_user_by_email(db, email):
    return db.query(User).filter(User.email == email).first()
```

### Docstrings

Sử dụng **Google Style**:

```python
def process_document(
    document_id: str,
    tenant_id: str,
    options: ProcessingOptions | None = None
) -> ProcessingResult:
    """Process uploaded document through RAG pipeline.

    Extracts text, chunks content, generates embeddings, and indexes
    to OpenSearch.

    Args:
        document_id: UUID of the document to process.
        tenant_id: UUID of the tenant owning the document.
        options: Optional processing configuration.

    Returns:
        ProcessingResult containing chunk count and status.

    Raises:
        DocumentNotFoundError: If document doesn't exist.
        ProcessingError: If extraction or embedding fails.

    Example:
        >>> result = process_document("doc-123", "tenant-456")
        >>> print(result.chunk_count)
        45
    """
    pass
```

### Naming Conventions

```python
# Classes: PascalCase
class UserTenantRole:
    pass

# Functions/Methods: snake_case
def get_user_tenant_roles():
    pass

# Constants: UPPER_SNAKE_CASE
MAX_FILE_SIZE_MB = 10
ALLOWED_MIME_TYPES = ["application/pdf", "text/plain"]

# Private methods: _leading_underscore
def _validate_file_content(file: UploadFile):
    pass

# Variables: snake_case
user_count = 10
current_tenant_id = "..."
```

### Import Order

```python
# 1. Standard library
import os
import json
from datetime import datetime
from typing import Any

# 2. Third-party packages
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import openai

# 3. Local imports
from app.core.config import settings
from app.models.user import User
from app.services.auth_service import AuthService
```

### Error Handling

```python
# Define custom exceptions
class RAGException(Exception):
    """Base exception for RAG system."""
    pass

class DocumentNotFoundError(RAGException):
    """Raised when document doesn't exist."""
    pass

class ProcessingError(RAGException):
    """Raised when document processing fails."""
    pass

# Use in services
def get_document(document_id: str) -> Document:
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise DocumentNotFoundError(f"Document {document_id} not found")
    return document

# Handle in API layer
@router.get("/documents/{document_id}")
async def get_document_endpoint(document_id: str):
    try:
        return doc_service.get_document(document_id)
    except DocumentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ProcessingError as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### Async/Await

```python
# ✅ Good - Use async for I/O operations
async def get_embeddings(texts: list[str]) -> list[list[float]]:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.openai.com/v1/embeddings",
            json={"input": texts, "model": "text-embedding-3-small"},
            headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"}
        )
    return [item["embedding"] for item in response.json()["data"]]

# ✅ Good - Concurrent I/O
async def process_multiple_documents(doc_ids: list[str]):
    tasks = [process_document(doc_id) for doc_id in doc_ids]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results

# ❌ Bad - Blocking call in async function
async def bad_example():
    # This blocks the event loop!
    response = requests.get("https://api.example.com")
```

---

## 🔄 Development Workflow

### Git Branching Strategy

```
main (production)
  │
  ├── develop (staging)
  │     │
  │     ├── feature/add-hybrid-search
  │     ├── feature/improve-chunking
  │     └── bugfix/fix-upload-validation
  │
  └── hotfix/critical-security-patch
```

### Branch Naming

```bash
# Features
feature/RAG-123-add-streaming-response
feature/add-document-tags

# Bug fixes
bugfix/RAG-456-fix-upload-timeout
bugfix/fix-opensearch-query

# Hotfixes (production)
hotfix/fix-critical-auth-bypass

# Chores
chore/update-dependencies
chore/improve-logging
```

### Commit Messages

Sử dụng **Conventional Commits**:

```bash
# Format: <type>(<scope>): <description>

# Types:
# feat     - New feature
# fix      - Bug fix
# docs     - Documentation
# style    - Code style (formatting, no logic change)
# refactor - Code refactoring
# test     - Adding/updating tests
# chore    - Maintenance tasks

# Examples:
git commit -m "feat(rag): add hybrid search with BM25"
git commit -m "fix(upload): validate MIME type using magic bytes"
git commit -m "docs(api): update RAG endpoint documentation"
git commit -m "refactor(chunking): extract chunking strategies to separate module"
git commit -m "test(auth): add integration tests for login flow"
```

### Pull Request Process

1. **Create branch** từ `develop`
2. **Implement feature** với commits nhỏ
3. **Write/update tests**
4. **Run tests locally**: `pytest`
5. **Update documentation** nếu cần
6. **Create PR** với description chi tiết
7. **Request review** từ ít nhất 1 người
8. **Address feedback**
9. **Squash and merge**

### PR Template

```markdown
## Description
Brief description of changes.

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Changes Made
- Added X
- Updated Y
- Removed Z

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests pass
- [ ] Manual testing done

## Screenshots (if applicable)

## Checklist
- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] No new warnings
```

---

## 🧪 Testing

### Test Structure

```
tests/
├── conftest.py              # Shared fixtures
├── unit/                    # Unit tests
│   ├── test_chunking.py
│   ├── test_embedding.py
│   └── test_security.py
├── integration/             # Integration tests
│   ├── test_auth_flow.py
│   ├── test_document_upload.py
│   └── test_rag_query.py
└── e2e/                     # End-to-end tests
    └── test_full_pipeline.py
```

### Pytest Configuration

```toml
# pyproject.toml

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_functions = ["test_*"]
addopts = [
    "-v",
    "--tb=short",
    "--strict-markers",
    "-ra",
]
markers = [
    "slow: marks tests as slow",
    "integration: marks tests requiring external services",
]
asyncio_mode = "auto"
```

### Shared Fixtures

```python
# tests/conftest.py

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db.postgres import Base, get_db
from app.core.config import settings

# Test database
TEST_DATABASE_URL = "postgresql://test:test@localhost:5432/ragdb_test"

@pytest.fixture(scope="session")
def engine():
    """Create test database engine."""
    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def db_session(engine):
    """Create new database session for each test."""
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.rollback()
        session.close()

@pytest.fixture
def client(db_session):
    """FastAPI test client with database override."""
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

@pytest.fixture
def auth_headers(client):
    """Get authenticated headers."""
    # Register user
    client.post("/api/v1/auth/register", json={
        "email": "test@example.com",
        "password": "TestPassword123!",
        "full_name": "Test User"
    })
    
    # Login
    response = client.post("/api/v1/auth/login", data={
        "username": "test@example.com",
        "password": "TestPassword123!"
    })
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def sample_tenant(client, auth_headers):
    """Create sample tenant."""
    response = client.post(
        "/api/v1/tenants",
        headers=auth_headers,
        json={"name": "Test Tenant", "description": "For testing"}
    )
    return response.json()["data"]
```

### Unit Test Example

```python
# tests/unit/test_chunking.py

import pytest
from app.services.chunking import TextChunker, ChunkingStrategy

class TestTextChunker:
    """Tests for TextChunker service."""

    def test_chunk_by_sentences(self):
        """Should split text into sentence chunks."""
        chunker = TextChunker(strategy=ChunkingStrategy.SENTENCE)
        text = "First sentence. Second sentence. Third sentence."
        
        chunks = chunker.chunk(text, max_chunk_size=50)
        
        assert len(chunks) == 3
        assert chunks[0] == "First sentence."

    def test_chunk_with_overlap(self):
        """Should create overlapping chunks."""
        chunker = TextChunker(
            strategy=ChunkingStrategy.FIXED_SIZE,
            chunk_size=100,
            overlap=20
        )
        text = "A" * 200
        
        chunks = chunker.chunk(text)
        
        assert len(chunks) == 3  # 0-100, 80-180, 160-200

    def test_empty_text_returns_empty_list(self):
        """Should return empty list for empty input."""
        chunker = TextChunker()
        
        chunks = chunker.chunk("")
        
        assert chunks == []

    @pytest.mark.parametrize("text,expected_count", [
        ("Short text", 1),
        ("A" * 500, 5),
        ("A" * 1000, 10),
    ])
    def test_chunk_count(self, text, expected_count):
        """Should produce expected number of chunks."""
        chunker = TextChunker(chunk_size=100, overlap=0)
        
        chunks = chunker.chunk(text)
        
        assert len(chunks) == expected_count
```

### Integration Test Example

```python
# tests/integration/test_document_upload.py

import pytest
from io import BytesIO

class TestDocumentUpload:
    """Integration tests for document upload flow."""

    def test_upload_pdf_success(self, client, auth_headers, sample_tenant):
        """Should successfully upload PDF document."""
        # Create fake PDF
        pdf_content = b"%PDF-1.4 fake pdf content"
        file = BytesIO(pdf_content)
        
        response = client.post(
            f"/api/v1/tenants/{sample_tenant['id']}/documents",
            headers=auth_headers,
            files={"file": ("test.pdf", file, "application/pdf")},
            data={"title": "Test Document"}
        )
        
        assert response.status_code == 202
        data = response.json()["data"]
        assert data["status"] == "processing"
        assert data["title"] == "Test Document"

    def test_upload_rejects_oversized_file(self, client, auth_headers, sample_tenant):
        """Should reject files over 10MB."""
        large_file = BytesIO(b"x" * (11 * 1024 * 1024))  # 11MB
        
        response = client.post(
            f"/api/v1/tenants/{sample_tenant['id']}/documents",
            headers=auth_headers,
            files={"file": ("large.pdf", large_file, "application/pdf")},
            data={"title": "Large File"}
        )
        
        assert response.status_code == 413
        assert "FILE_TOO_LARGE" in response.json()["error"]["code"]

    def test_upload_rejects_invalid_mime_type(self, client, auth_headers, sample_tenant):
        """Should reject unsupported file types."""
        exe_file = BytesIO(b"MZ" + b"\x00" * 100)  # EXE magic bytes
        
        response = client.post(
            f"/api/v1/tenants/{sample_tenant['id']}/documents",
            headers=auth_headers,
            files={"file": ("virus.exe", exe_file, "application/x-msdownload")},
            data={"title": "Bad File"}
        )
        
        assert response.status_code == 415
        assert "UNSUPPORTED_FILE_TYPE" in response.json()["error"]["code"]

    @pytest.mark.integration
    def test_upload_triggers_processing_task(
        self, client, auth_headers, sample_tenant, mocker
    ):
        """Should enqueue Celery task after upload."""
        mock_task = mocker.patch("app.worker.tasks.process_document.delay")
        
        pdf_content = b"%PDF-1.4 content"
        response = client.post(
            f"/api/v1/tenants/{sample_tenant['id']}/documents",
            headers=auth_headers,
            files={"file": ("test.pdf", BytesIO(pdf_content), "application/pdf")},
            data={"title": "Test"}
        )
        
        assert response.status_code == 202
        mock_task.assert_called_once()
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific file
pytest tests/unit/test_chunking.py -v

# Run specific test
pytest tests/unit/test_chunking.py::TestTextChunker::test_chunk_by_sentences -v

# Run only fast tests (exclude slow/integration)
pytest -m "not slow and not integration"

# Run with parallel execution
pytest -n auto

# Run and stop at first failure
pytest -x

# Run failed tests from last run
pytest --lf
```

---

## 🐛 Debugging

### VS Code Configuration

```json
// .vscode/launch.json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "FastAPI",
      "type": "python",
      "request": "launch",
      "module": "uvicorn",
      "args": ["app.main:app", "--reload", "--port", "8000"],
      "jinja": true,
      "justMyCode": false
    },
    {
      "name": "Celery Worker",
      "type": "python",
      "request": "launch",
      "module": "celery",
      "args": ["-A", "app.worker.celery_app", "worker", "--loglevel=debug"],
      "justMyCode": false
    },
    {
      "name": "Pytest",
      "type": "python",
      "request": "launch",
      "module": "pytest",
      "args": ["-v", "-s"],
      "justMyCode": false
    }
  ]
}
```

### Logging Configuration

```python
# app/core/logging.py

import logging
import sys
from app.core.config import settings

def setup_logging():
    """Configure structured logging."""
    
    log_format = (
        "%(asctime)s | %(levelname)-8s | %(name)s | "
        "%(filename)s:%(lineno)d | %(message)s"
    )
    
    if settings.APP_ENV == "production":
        # JSON format for production
        import json_log_formatter
        formatter = json_log_formatter.JSONFormatter()
    else:
        # Human-readable for development
        formatter = logging.Formatter(log_format)
    
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    
    root_logger = logging.getLogger()
    root_logger.setLevel(settings.LOG_LEVEL)
    root_logger.addHandler(handler)
    
    # Reduce noise from libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

# Usage in code
logger = logging.getLogger(__name__)

def process_document(document_id: str):
    logger.info(f"Starting document processing", extra={
        "document_id": document_id,
        "action": "process_start"
    })
    
    try:
        # Processing logic
        logger.debug("Extracting text from document")
        # ...
    except Exception as e:
        logger.error(f"Processing failed: {e}", extra={
            "document_id": document_id,
            "error_type": type(e).__name__
        }, exc_info=True)
        raise
```

### Debug Endpoints (Development Only)

```python
# app/api/v1/debug.py

from fastapi import APIRouter, Depends
from app.core.config import settings

router = APIRouter(prefix="/debug", tags=["Debug"])

@router.get("/config")
async def get_config():
    """View current configuration (development only)."""
    if settings.APP_ENV != "development":
        raise HTTPException(status_code=404)
    
    return {
        "app_env": settings.APP_ENV,
        "debug": settings.DEBUG,
        "postgres_host": settings.POSTGRES_HOST,
        "opensearch_host": settings.OPENSEARCH_HOST,
    }

@router.post("/clear-cache")
async def clear_cache():
    """Clear Redis cache (development only)."""
    if settings.APP_ENV != "development":
        raise HTTPException(status_code=404)
    
    redis_client.flushdb()
    return {"message": "Cache cleared"}
```

### Useful Debug Commands

```bash
# Check database connection
python -c "from app.db.postgres import engine; print(engine.execute('SELECT 1').scalar())"

# Check OpenSearch
curl -X GET "http://localhost:9200/_cluster/health?pretty"

# Check Redis
redis-cli ping

# View Celery tasks
celery -A app.worker.celery_app inspect active
celery -A app.worker.celery_app inspect reserved

# Monitor Celery (flower)
pip install flower
celery -A app.worker.celery_app flower --port=5555
```

---

## 🎯 Common Patterns

### Dependency Injection

```python
# app/api/dependencies.py

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.db.postgres import get_db
from app.models.user import User
from app.core.security import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    """Get current authenticated user from JWT token."""
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )
    
    user = db.query(User).filter(User.id == payload.get("sub")).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
    return user

async def get_current_tenant(
    tenant_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Tenant:
    """Get tenant and verify user has access."""
    role = db.query(UserTenantRole).filter(
        UserTenantRole.user_id == current_user.id,
        UserTenantRole.tenant_id == tenant_id
    ).first()
    
    if not role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this tenant"
        )
    
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    return tenant

# Usage in router
@router.get("/tenants/{tenant_id}/documents")
async def list_documents(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
):
    return db.query(Document).filter(Document.tenant_id == tenant.id).all()
```

### Repository Pattern

```python
# app/repositories/document_repository.py

from sqlalchemy.orm import Session
from typing import Optional
from uuid import UUID

from app.models.document import Document

class DocumentRepository:
    """Repository for Document database operations."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, document_id: UUID) -> Optional[Document]:
        return self.db.query(Document).filter(
            Document.id == document_id
        ).first()

    def get_by_tenant(
        self,
        tenant_id: UUID,
        skip: int = 0,
        limit: int = 20,
        status: Optional[str] = None
    ) -> list[Document]:
        query = self.db.query(Document).filter(
            Document.tenant_id == tenant_id
        )
        
        if status:
            query = query.filter(Document.status == status)
        
        return query.offset(skip).limit(limit).all()

    def create(self, **kwargs) -> Document:
        document = Document(**kwargs)
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)
        return document

    def update(self, document: Document, **kwargs) -> Document:
        for key, value in kwargs.items():
            setattr(document, key, value)
        self.db.commit()
        self.db.refresh(document)
        return document

    def delete(self, document: Document) -> None:
        self.db.delete(document)
        self.db.commit()
```

### Service Layer Pattern

```python
# app/services/doc_service.py

from uuid import UUID
from sqlalchemy.orm import Session

from app.repositories.document_repository import DocumentRepository
from app.services.storage import StorageService
from app.worker.tasks import process_document
from app.schemas.doc_schema import DocumentCreate, DocumentResponse

class DocumentService:
    """Service layer for document operations."""

    def __init__(self, db: Session):
        self.db = db
        self.repo = DocumentRepository(db)
        self.storage = StorageService()

    async def upload_document(
        self,
        tenant_id: UUID,
        user_id: UUID,
        file: UploadFile,
        data: DocumentCreate
    ) -> DocumentResponse:
        """Upload and process a new document."""
        
        # 1. Validate file
        self._validate_file(file)
        
        # 2. Upload to S3
        s3_key = await self.storage.upload(
            file=file,
            bucket="rag-documents",
            key=f"{tenant_id}/{uuid.uuid4()}/{file.filename}"
        )
        
        # 3. Create database record
        document = self.repo.create(
            tenant_id=tenant_id,
            uploaded_by=user_id,
            title=data.title,
            description=data.description,
            file_name=file.filename,
            file_size_bytes=file.size,
            mime_type=file.content_type,
            s3_key=s3_key,
            status="processing",
            tags=data.tags
        )
        
        # 4. Queue processing task
        process_document.delay(str(document.id))
        
        return DocumentResponse.from_orm(document)

    def _validate_file(self, file: UploadFile) -> None:
        """Validate file size and type."""
        if file.size > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
            raise FileTooLargeError()
        
        # Check magic bytes
        mime_type = magic.from_buffer(file.file.read(1024), mime=True)
        file.file.seek(0)
        
        if mime_type not in settings.ALLOWED_MIME_TYPES:
            raise UnsupportedFileTypeError(mime_type)
```

### Celery Task Pattern

```python
# app/worker/tasks.py

from celery import shared_task
from sqlalchemy.orm import Session

from app.db.postgres import SessionLocal
from app.services.embedding import EmbeddingService
from app.services.chunking import TextChunker
from app.db.opensearch import opensearch_client

@shared_task(
    bind=True,
    autoretry_for=(OpenAIError, ConnectionError),
    retry_backoff=True,
    retry_backoff_max=60,
    max_retries=3
)
def process_document(self, document_id: str):
    """Process document through RAG pipeline.
    
    Steps:
    1. Extract text from file
    2. Chunk text
    3. Generate embeddings
    4. Index to OpenSearch
    5. Update status
    """
    db = SessionLocal()
    
    try:
        # Get document
        document = db.query(Document).filter(
            Document.id == document_id
        ).first()
        
        if not document:
            raise DocumentNotFoundError(document_id)
        
        # Update status
        document.status = "processing"
        db.commit()
        
        # 1. Extract text
        text = extract_text(document.s3_key, document.mime_type)
        
        # 2. Chunk
        chunker = TextChunker(chunk_size=500, overlap=50)
        chunks = chunker.chunk(text)
        
        # 3. Generate embeddings
        embedding_service = EmbeddingService()
        embeddings = embedding_service.embed(chunks)
        
        # 4. Index to OpenSearch
        bulk_data = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            bulk_data.append({
                "_index": "rag_vectors",
                "_source": {
                    "tenant_id": str(document.tenant_id),
                    "document_id": str(document.id),
                    "chunk_id": f"chunk_{i}",
                    "content": chunk,
                    "vector": embedding,
                    "embedding_model": "text-embedding-3-small"
                }
            })
        
        opensearch_client.bulk(body=bulk_data)
        
        # 5. Update document
        document.status = "completed"
        document.chunk_count = len(chunks)
        document.processed_at = datetime.utcnow()
        db.commit()
        
        return {"document_id": document_id, "chunks": len(chunks)}
        
    except Exception as e:
        # Mark as failed after max retries
        if self.request.retries >= self.max_retries:
            document.status = "failed"
            document.error_message = str(e)
            db.commit()
        raise
        
    finally:
        db.close()
```

---

## 💡 Best Practices

### 1. Security

```python
# ✅ Always validate tenant access
async def get_document(
    document_id: str,
    tenant: Tenant = Depends(get_current_tenant),  # Validates access
    db: Session = Depends(get_db)
):
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.tenant_id == tenant.id  # Double check tenant
    ).first()
    
    if not document:
        raise HTTPException(status_code=404)
    
    return document

# ✅ Sanitize file names
import re

def sanitize_filename(filename: str) -> str:
    # Remove path separators and special chars
    return re.sub(r'[^\w\-_\.]', '', filename)

# ✅ Use parameterized queries (SQLAlchemy does this automatically)
# Never string concatenate SQL!
```

### 2. Performance

```python
# ✅ Use pagination
@router.get("/documents")
async def list_documents(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    skip = (page - 1) * limit
    documents = db.query(Document).offset(skip).limit(limit).all()
    total = db.query(Document).count()
    
    return {
        "items": documents,
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit
    }

# ✅ Use connection pooling
engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True
)

# ✅ Cache expensive operations
from functools import lru_cache

@lru_cache(maxsize=100)
def get_tenant_settings(tenant_id: str) -> TenantSettings:
    # Expensive DB query
    pass

# ✅ Batch OpenAI requests
async def embed_chunks(chunks: list[str]) -> list[list[float]]:
    # Batch up to 100 texts per request
    batch_size = 100
    embeddings = []
    
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        result = await openai_client.embeddings.create(
            input=batch,
            model="text-embedding-3-small"
        )
        embeddings.extend([e.embedding for e in result.data])
    
    return embeddings
```

### 3. Error Handling

```python
# ✅ Create specific exceptions
class RAGError(Exception):
    """Base RAG exception."""
    def __init__(self, message: str, code: str, details: dict = None):
        self.message = message
        self.code = code
        self.details = details or {}

class RateLimitError(RAGError):
    def __init__(self, retry_after: int):
        super().__init__(
            message="Rate limit exceeded",
            code="RATE_LIMITED",
            details={"retry_after": retry_after}
        )

# ✅ Global exception handler
@app.exception_handler(RAGError)
async def rag_exception_handler(request: Request, exc: RAGError):
    return JSONResponse(
        status_code=get_status_code(exc.code),
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details
            },
            "request_id": request.state.request_id
        }
    )

# ✅ Log errors with context
except Exception as e:
    logger.error(
        f"Document processing failed: {e}",
        extra={
            "document_id": document_id,
            "tenant_id": tenant_id,
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc()
        }
    )
    raise
```

### 4. Testing

```python
# ✅ Use fixtures for common setup
@pytest.fixture
def sample_document(db_session, sample_tenant):
    document = Document(
        tenant_id=sample_tenant.id,
        title="Test Doc",
        status="completed"
    )
    db_session.add(document)
    db_session.commit()
    return document

# ✅ Mock external services
def test_embedding_service(mocker):
    mock_openai = mocker.patch("app.services.embedding.openai_client")
    mock_openai.embeddings.create.return_value = MockResponse(
        data=[MockEmbedding(embedding=[0.1] * 1536)]
    )
    
    service = EmbeddingService()
    result = service.embed(["test text"])
    
    assert len(result) == 1
    assert len(result[0]) == 1536

# ✅ Test edge cases
@pytest.mark.parametrize("input,expected", [
    ("", []),
    ("   ", []),
    ("a" * 10000, ...),  # Very long text
    ("Unicode: 你好 🎉", ...),  # Unicode
])
def test_chunking_edge_cases(input, expected):
    pass
```

---

## 📚 Additional Resources

### Documentation
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [OpenSearch Python Client](https://opensearch.org/docs/latest/clients/python/)
- [Celery Documentation](https://docs.celeryq.dev/)

### Useful Tools
- **httpie**: `pip install httpie` - Better curl for API testing
- **pgcli**: `pip install pgcli` - Better PostgreSQL CLI
- **ipython**: `pip install ipython` - Better Python REPL
- **rich**: `pip install rich` - Better console output

### Getting Help
- Slack channel: #rag-dev
- Wiki: https://wiki.company.com/rag
- Tech lead: tech-lead@company.com

---

<p align="center">
  <strong>Happy Coding! 🚀</strong>
</p>
