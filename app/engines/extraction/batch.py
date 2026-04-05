"""Batch extraction — run block pipeline on multiple PDFs in parallel with backpressure."""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings
from app.utils.metrics import PipelineMetrics
from app.domain.templates.template_loader import DocumentTemplate, get_default_template
from app.engines.extraction.block_workflow import BlockBusinessWorkflow

logger = logging.getLogger(__name__)


@dataclass
class BatchItem:
    filename: str
    pdf_bytes: bytes


@dataclass
class BatchResult:
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    results: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


def run_batch(
    items: list[BatchItem],
    *,
    max_workers: int | None = None,
    max_queue_size: int | None = None,
    model: str | None = None,
    template: DocumentTemplate | None = None,
) -> BatchResult:
    """Process multiple PDFs through the block pipeline with parallelism.

    Args:
        items: list of BatchItem(filename, pdf_bytes).
        max_workers: thread pool size (default: settings.EXTRACTION_BATCH_MAX_FILES / 2,
                     capped at 4 for LLM backends to avoid OOM).
        max_queue_size: reject items beyond this count (backpressure).
        model: LLM model override.
        template: document template override.
    """

    tpl = template or get_default_template()
    max_q = max_queue_size or settings.EXTRACTION_BATCH_MAX_FILES
    workers = max_workers or min(max(settings.EXTRACTION_BATCH_MAX_FILES // 2, 1), 4)

    batch_metrics = PipelineMetrics()
    result = BatchResult(total=len(items))

    # ── Backpressure: reject if queue exceeds limit ───────────────────
    if len(items) > max_q:
        logger.warning(
            "Batch backpressure: %s items submitted, limit is %s. Rejecting excess.",
            len(items), max_q,
        )
        excess = items[max_q:]
        items = items[:max_q]
        for item in excess:
            result.errors.append({
                "filename": item.filename,
                "error": f"backpressure: queue full ({max_q} max)",
            })
            result.failed += 1
        result.total = len(items) + len(excess)

    def _process_one(item: BatchItem) -> dict[str, Any]:
        workflow = BlockBusinessWorkflow(model=model, template=tpl)
        wf_result = workflow.run_from_bytes(item.pdf_bytes, item.filename)
        return workflow.build_final_payload(item.filename, wf_result)

    if workers <= 1 or len(items) <= 1:
        # Sequential — simpler, no thread overhead
        for item in items:
            try:
                with batch_metrics.timer("batch_item"):
                    payload = _process_one(item)
                result.results.append(payload)
                result.succeeded += 1
            except Exception as exc:
                result.errors.append({"filename": item.filename, "error": str(exc)})
                result.failed += 1
    else:
        # Parallel
        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_to_item = {
                pool.submit(_process_one, item): item for item in items
            }
            for future in as_completed(future_to_item):
                item = future_to_item[future]
                try:
                    with batch_metrics.timer("batch_item"):
                        payload = future.result()
                    result.results.append(payload)
                    result.succeeded += 1
                except Exception as exc:
                    result.errors.append({"filename": item.filename, "error": str(exc)})
                    result.failed += 1

    batch_metrics.inc("batch_total", result.total)
    batch_metrics.inc("batch_succeeded", result.succeeded)
    batch_metrics.inc("batch_failed", result.failed)
    result.metrics = batch_metrics.to_dict()

    logger.info(
        "Batch complete: %s/%s succeeded, %s failed, workers=%s",
        result.succeeded, result.total, result.failed, workers,
    )
    return result


def run_batch_from_directory(
    directory: str,
    *,
    max_workers: int | None = None,
    model: str | None = None,
    template: DocumentTemplate | None = None,
) -> BatchResult:
    """Convenience: gather all PDFs from a directory and run batch extraction."""

    items: list[BatchItem] = []
    for fname in sorted(os.listdir(directory)):
        if not fname.lower().endswith(".pdf"):
            continue
        fpath = os.path.join(directory, fname)
        with open(fpath, "rb") as f:
            items.append(BatchItem(filename=fname, pdf_bytes=f.read()))

    if not items:
        logger.warning("No PDF files found in %s", directory)
        return BatchResult()

    return run_batch(items, max_workers=max_workers, model=model, template=template)
