"""Schema resolution using Python package resources.

Eliminates filesystem path dependencies by loading YAML schemas
from the app.domain.templates package via importlib.resources.
"""

from __future__ import annotations

import yaml
from importlib import resources
from functools import lru_cache
from pathlib import Path
from typing import Dict, Any

from app.core.exceptions import ProcessingError


class SchemaResolver:
    """Centralized resolver for schema YAML files.

    Uses importlib.resources to access schemas as package resources,
    ensuring portability across Docker, Celery, pytest, and production.
    """

    # Package containing all schema YAML files
    PACKAGE = "app.domain.templates"

    @staticmethod
    @lru_cache(maxsize=32)
    def load_schema(name: str) -> Dict[str, Any]:
        """Load a schema YAML file.

        Args:
            name: Schema filename (e.g., "bc_ngay_kv30_schema.yaml") or
                  absolute/relative file path. For built-in schemas, use the
                  filename only to load from package resources. For custom
                  external schemas (e.g., in tests), a file path may be used.

        Returns:
            Parsed YAML content as a dictionary.

        Raises:
            ProcessingError: If schema cannot be found or parsed.
        """
        # Heuristic: if name contains no path separators, treat as package resource
        if not any(sep in name for sep in ("/", "\\")):
            # Load from package resources
            try:
                with resources.files(SchemaResolver.PACKAGE).joinpath(name).open('r', encoding='utf-8') as f:
                    return yaml.safe_load(f) or {}
            except FileNotFoundError as e:
                raise ProcessingError(
                    message=f"Schema '{name}' not found in package resources "
                            f"(package: {SchemaResolver.PACKAGE})"
                ) from e
            except yaml.YAMLError as e:
                raise ProcessingError(message=f"Invalid YAML in schema '{name}': {e}") from e
            except Exception as e:
                raise ProcessingError(message=f"Error loading schema '{name}': {e}") from e

        # Legacy: if a filesystem path is provided and exists, read it directly
        path = Path(name).expanduser()
        if path.is_file():
            try:
                with open(path, encoding='utf-8') as f:
                    return yaml.safe_load(f) or {}
            except yaml.YAMLError as e:
                raise ProcessingError(message=f"Invalid YAML in schema file '{name}': {e}") from e
            except Exception as e:
                raise ProcessingError(message=f"Error reading schema file '{name}': {e}") from e

        raise ProcessingError(message=f"Schema file not found: {name}")

    @staticmethod
    @lru_cache(maxsize=1)
    def load_sheet_mapping() -> Dict[str, Any]:
        """Load the global sheet_mapping.yaml and return its 'sheet_mapping' key."""
        full = SchemaResolver.load_schema("sheet_mapping.yaml")
        mapping = full.get("sheet_mapping")
        if not isinstance(mapping, dict):
            raise ProcessingError(
                message="Invalid sheet_mapping.yaml: missing or invalid 'sheet_mapping' key"
            )
        return mapping

    @staticmethod
    @lru_cache(maxsize=32)
    def get_sheet_mapping(schema_path: str) -> Dict[str, Any]:
        """Load a custom schema and return its 'sheet_mapping' section.

        Args:
            schema_path: Schema filename or file path.

        Returns:
            The sheet_mapping dictionary from the schema.

        Raises:
            ProcessingError: If schema invalid or missing sheet_mapping.
        """
        full = SchemaResolver.load_schema(schema_path)
        mapping = full.get("sheet_mapping")
        if not isinstance(mapping, dict):
            raise ProcessingError(
                message=f"Invalid schema '{schema_path}': missing or invalid 'sheet_mapping' key"
            )
        return mapping
