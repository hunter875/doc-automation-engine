"""FastAPI main application."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import auth, document, extraction, rag, tenant
from app.core.config import settings
from app.core.exceptions import RAGException
from app.core.logging import configure_logging
from app.db.postgres import engine, Base

# Configure logging
configure_logging(
    log_level=settings.LOG_LEVEL,
    log_dir=settings.LOG_DIR,
    log_file=settings.LOG_FILE,
    max_bytes=settings.LOG_MAX_BYTES,
    backup_count=settings.LOG_BACKUP_COUNT,
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting RAG API server...")

    # Initialize pgvector extension FIRST (before creating tables)
    from app.db.postgres import SessionLocal
    from app.db.pgvector import ensure_pgvector_extension, create_vector_index
    db = SessionLocal()
    try:
        ensure_pgvector_extension(db)
        logger.info("pgvector extension initialized")
    except Exception as e:
        logger.warning(f"pgvector extension warning: {e}")
    finally:
        db.close()

    # Create database tables (after extension is enabled)
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created/verified")

    # Create vector indexes
    db = SessionLocal()
    try:
        create_vector_index(db)
        logger.info("Vector indexes created/verified")
    except Exception as e:
        logger.warning(f"Vector index warning: {e}")
    finally:
        db.close()
    
    yield
    
    # Shutdown
    logger.info("Shutting down RAG API server...")


# Create FastAPI application
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="""
## Enterprise Multi-Tenant RAG System

A production-ready Retrieval-Augmented Generation (RAG) system with multi-tenant support.

### Features
- 📄 **Document Management**: Upload, process, and manage documents
- 🔍 **Semantic Search**: Vector similarity search with hybrid BM25
- 🤖 **RAG Queries**: AI-powered Q&A based on your documents
- 👥 **Multi-Tenant**: Full data isolation between organizations
- 🔐 **RBAC**: Role-based access control (Owner, Admin, Viewer)

### Authentication
All endpoints require JWT Bearer token authentication.
Include `Authorization: Bearer <token>` header.

### Tenant Context
Most endpoints require `X-Tenant-ID` header to specify the tenant context.
""",
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers
@app.exception_handler(RAGException)
async def rag_exception_handler(request: Request, exc: RAGException):
    """Handle custom RAG exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.__class__.__name__,
            "message": exc.message,
            "details": exc.details,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors — log full detail so bugs are visible."""
    errors = exc.errors()
    # Log every error with the offending field path + value
    logger.error(
        f"422 Validation error on {request.method} {request.url.path}\n"
        + "\n".join(
            f"  [{' -> '.join(str(p) for p in e.get('loc', []))}] "
            f"{e.get('msg')} (input={repr(e.get('input'))})"
            for e in errors
        )
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "ValidationError",
            "message": "Request validation failed",
            "details": errors,
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "InternalError",
            "message": "An unexpected error occurred",
        },
    )


# Include routers
app.include_router(auth.router, prefix="/api/v1")
app.include_router(document.router, prefix="/api/v1")
app.include_router(rag.router, prefix="/api/v1")
app.include_router(extraction.router, prefix="/api/v1")
app.include_router(tenant.router, prefix="/api/v1")


# Health check endpoints
@app.get("/", tags=["Health"])
def root():
    """Root endpoint."""
    return {
        "name": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "running",
    }


@app.get("/health", tags=["Health"])
def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": settings.VERSION,
    }


@app.get("/health/ready", tags=["Health"])
def readiness_check():
    """Readiness check endpoint."""
    # Check database connection
    try:
        from sqlalchemy import text as sa_text
        from app.db.postgres import SessionLocal
        db = SessionLocal()
        db.execute(sa_text("SELECT 1"))
        db.close()
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"
    
    # Check pgvector connection
    try:
        from app.db.pgvector import check_pgvector_connection, ensure_pgvector_extension
        db_session = SessionLocal()
        ensure_pgvector_extension(db_session)
        pgvector_ok = check_pgvector_connection(db_session)
        db_session.close()
        vector_status = "connected" if pgvector_ok else "extension not installed"
    except Exception as e:
        vector_status = f"error: {str(e)}"
    
    return {
        "status": "ready",
        "checks": {
            "database": db_status,
            "pgvector": vector_status,
        },
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="info",
    )
