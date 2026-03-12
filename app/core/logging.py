"""Centralized logging configuration."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(
    log_level: str,
    log_dir: str,
    log_file: str,
    max_bytes: int,
    backup_count: int,
) -> None:
    """Configure root logger to output both console and rotating file logs."""
    root_logger = logging.getLogger()

    if root_logger.handlers:
        return

    level = getattr(logging, log_level.upper(), logging.INFO)
    root_logger.setLevel(level)

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    log_directory = Path(log_dir)
    log_directory.mkdir(parents=True, exist_ok=True)

    file_handler = RotatingFileHandler(
        filename=log_directory / log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
