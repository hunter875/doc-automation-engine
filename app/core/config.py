"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    APP_NAME: str = "Enterprise RAG System"
    APP_ENV: str = "development"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"
    VERSION: str = "1.0.0"

    @property
    def PROJECT_NAME(self) -> str:
        return self.APP_NAME

    # Security
    SECRET_KEY: str = "change-this-in-production-use-256-bit-key"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # PostgreSQL
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "raguser"
    POSTGRES_PASSWORD: str = "ragpassword"
    POSTGRES_DB: str = "ragdb"

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    @property
    def REDIS_URL(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # MinIO / S3
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "rag-documents"
    MINIO_SECURE: bool = False

    @property
    def S3_ENDPOINT_URL(self) -> str:
        scheme = "https" if self.MINIO_SECURE else "http"
        return f"{scheme}://{self.MINIO_ENDPOINT}"

    @property
    def S3_ACCESS_KEY(self) -> str:
        return self.MINIO_ACCESS_KEY

    @property
    def S3_SECRET_KEY(self) -> str:
        return self.MINIO_SECRET_KEY

    @property
    def S3_BUCKET_NAME(self) -> str:
        return self.MINIO_BUCKET

    @property
    def S3_REGION(self) -> str:
        return "us-east-1"

    @property
    def MAX_FILE_SIZE(self) -> int:
        return self.MAX_FILE_SIZE_MB * 1024 * 1024

    # Gemini
    GEMINI_API_KEY: str = ""
    GEMINI_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    GEMINI_EMBEDDING_MODEL: str = "gemini-embedding-001"
    GEMINI_CHAT_MODEL: str = "gemini-2.0-flash"
    GEMINI_TIMEOUT: int = 15
    GEMINI_MAX_RETRIES: int = 3

    # Ollama (Hybrid extraction)
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_API_KEY: str = "ollama"
    OLLAMA_MODEL: str = "qwen2.5:7b"

    # File Upload
    MAX_FILE_SIZE_MB: int = 10
    ALLOWED_MIME_TYPES: List[str] = [
        "application/pdf",
        "text/plain",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ]

    # Chunking
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 50

    # Embedding
    EMBEDDING_DIMENSION: int = 768
    EMBEDDING_BATCH_SIZE: int = 100

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_DEFAULT: str = "100/minute"

    # CORS
    CORS_ORIGINS: List[str] = ["*"]

    # ── Engine 2: Extraction ──────────────────────────────
    # Gemini models for extraction (free API)
    GEMINI_FLASH_MODEL: str = "gemini-2.5-flash"    # standard + fast + vision modes
    GEMINI_PRO_MODEL: str = "gemini-2.5-flash"       # vision mode (alias → flash)
    EXTRACTION_MAX_TOKENS: int = 65536
    EXTRACTION_TEMPERATURE: float = 0.0

    # Default extraction mode: standard | vision | fast
    DEFAULT_EXTRACTION_MODE: str = "standard"

    # Legacy / optional
    OPENAI_API_KEY: str = ""
    LLAMAPARSE_API_KEY: str = ""

    # Extraction
    EXTRACTION_MAX_RETRIES: int = 3
    EXTRACTION_TIMEOUT_MINUTES: int = 30
    EXTRACTION_BATCH_MAX_FILES: int = 20

    # Hybrid extraction fallback
    HYBRID_MAX_RETRIES: int = 3
    HYBRID_MANUAL_REVIEW_DIR: str = "Needs_Manual_Review"

    # Confidence thresholds (for UI rendering)
    CONFIDENCE_HIGH: float = 0.85
    CONFIDENCE_MEDIUM: float = 0.50

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"
    LOG_DIR: str = "logs"
    LOG_FILE: str = "app.log"
    LOG_MAX_BYTES: int = 10485760
    LOG_BACKUP_COUNT: int = 5


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
