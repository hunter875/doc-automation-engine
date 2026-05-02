"""Pipeline registry for source-type-to-pipeline resolution.

This module provides a centralized registry that maps parser_used values to
pipeline factory functions. The orchestrator uses this registry to resolve
the appropriate pipeline without knowing concrete implementations.

Adding a new source type requires ONLY registering the pipeline in this module.
"""

from __future__ import annotations

from typing import Callable, Protocol, runtime_checkable
from dataclasses import dataclass, field


@runtime_checkable
class ExtractionPipeline(Protocol):
    """Protocol that all extraction pipelines must implement."""

    def run(self, *args, **kwargs) -> object:
        """Execute the pipeline and return a result.

        The result must be either:
        - PipelineResult with output=BlockExtractionOutput (preferred)
        - BlockExtractionOutput directly (will be wrapped)
        """
        ...


@dataclass
class PipelineRegistry:
    """Registry for mapping parser_used strings to pipeline factories.

    Usage:
        registry = PipelineRegistry()
        registry.register("pdfplumber", lambda: BlockExtractionPipeline(...))
        registry.register("google_sheets", lambda: SheetExtractionPipeline(...))
        pipeline = registry.resolve("pdfplumber")()
    """

    _factories: dict[str, Callable[[], ExtractionPipeline]] = field(default_factory=dict)

    def register(self, parser_used: str, factory: Callable[[], ExtractionPipeline]) -> None:
        """Register a pipeline factory for a parser_used value."""
        self._factories[parser_used] = factory

    def resolve(self, parser_used: str) -> Callable[[], ExtractionPipeline]:
        """Get the factory for a parser_used value.

        Raises:
            ProcessingError: If parser_used is not registered.
        """
        if parser_used not in self._factories:
            from app.core.exceptions import ProcessingError
            raise ProcessingError(
                message=f"No pipeline registered for parser_used='{parser_used}'. "
                f"Registered: {list(self._factories.keys())}"
            )
        return self._factories[parser_used]

    def is_registered(self, parser_used: str) -> bool:
        """Check if a parser_used has a registered pipeline."""
        return parser_used in self._factories


# Global registry instance - populated at application startup
_default_registry = PipelineRegistry()


def get_default_registry() -> PipelineRegistry:
    """Return the global default registry."""
    return _default_registry


def register_default_pipelines() -> None:
    """Register the standard pipelines with the default registry.

    This is called during application startup to ensure all built-in
    pipelines are available. Custom pipelines can be registered separately.
    """
    from app.engines.extraction.block_pipeline import BlockExtractionPipeline
    from app.engines.extraction.sheet_pipeline import SheetExtractionPipeline
    from app.core.config import settings

    # PDF pipeline
    def create_pdf_pipeline() -> BlockExtractionPipeline:
        return BlockExtractionPipeline(
            model=settings.OLLAMA_MODEL,
            temperature=0.0,
        )

    # Sheet pipeline
    def create_sheet_pipeline() -> SheetExtractionPipeline:
        return SheetExtractionPipeline()

    _default_registry.register("pdfplumber", create_pdf_pipeline)
    _default_registry.register("google_sheets", create_sheet_pipeline)
    _default_registry.register("sheet", create_sheet_pipeline)  # alias
