"""FastAPI main application."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import auth, document, tenant
from app.api.v1.jobs import router as extraction_jobs_router
from app.api.v1.aggregation import router as extraction_reports_router
from app.api.v1.templates import router as extraction_templates_router
from app.api.v1.ingestion import router as ingestion_router
from app.api.v1.reports import router as report_calendar_router
from app.api.v1.sheets import router as sheets_router
from app.core.config import settings
from app.core.exceptions import RAGException
from app.core.logging import configure_logging
from app.infrastructure.db.session import engine, Base

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
    logger.info("Starting IDP Extraction API server...")

    # Create database tables
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created/verified")

    yield

    # Shutdown
    logger.info("Shutting down IDP Extraction API server...")


# Create FastAPI application
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="""
## IDP Extraction System

A production-ready Intelligent Document Processing (IDP) platform.

### Features
- 📄 **Document Management**: Upload and manage documents
- ⚙️ **Engine 2 Extraction**: Block-based deterministic extraction + LLM enrichment
- 📊 **Aggregation**: Merge extraction results into reports
- 👥 **Multi-Tenant**: Full data isolation between organizations
- 🔐 **RBAC**: Role-based access control (Owner, Admin, Viewer)

### Authentication
All endpoints require JWT Bearer token authentication.

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
app.include_router(extraction_templates_router, prefix="/api/v1/extraction", tags=["Extraction Templates"])
app.include_router(extraction_jobs_router, prefix="/api/v1/extraction", tags=["Extraction Jobs"])
app.include_router(extraction_reports_router, prefix="/api/v1/extraction", tags=["Extraction Reports"])
app.include_router(ingestion_router, prefix="/api/v1/extraction", tags=["Extraction Ingestion"])
app.include_router(report_calendar_router, prefix="/api/reports", tags=["Report Calendar"])
app.include_router(sheets_router, prefix="/api/v1/sheets", tags=["Sheet Inspector"])
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
        from app.infrastructure.db.session import SessionLocal
        db = SessionLocal()
        db.execute(sa_text("SELECT 1"))
        db.close()
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"

    return {
        "status": "ready",
        "checks": {
            "database": db_status,
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
