"""PostgreSQL database connection and session management."""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.infrastructure.db.base import Base  # noqa: F401 — re-export for convenience

# Create SQLAlchemy engine
engine = create_engine(
    settings.DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # Check connection health before using
    pool_recycle=300,  # Recycle connections after 5 minutes
    echo=settings.DEBUG,  # Log SQL queries in debug mode
)

# Session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db() -> Generator[Session, None, None]:
    """Dependency to get database session.

    Yields:
        SQLAlchemy Session

    Usage:
        @app.get("/items")
        def get_items(db: Session = Depends(get_db)):
            return db.query(Item).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """Context manager for database session.

    Usage:
        with get_db_context() as db:
            db.query(User).all()
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """Initialize database tables.

    This should be called once at application startup
    or during migrations.
    """
    Base.metadata.create_all(bind=engine)


def check_db_connection() -> bool:
    """Check if database connection is healthy.

    Returns:
        True if connection is healthy, False otherwise
    """
    try:
        from sqlalchemy import text as sa_text
        with engine.connect() as conn:
            conn.execute(sa_text("SELECT 1"))
        return True
    except Exception:
        return False
