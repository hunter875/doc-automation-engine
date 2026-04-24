"""Celery tasks for Phase 3: FileOperator + BatchCloser.

FileOperator  — polls MinIO inbox/ prefix for new PDFs, auto-detects template
                & mode, creates jobs, triggers extraction.
BatchCloser   — monitors active batches, auto-closes when all jobs reach
                a terminal state, optionally triggers aggregation.
"""

import logging
import uuid
from datetime import datetime, timedelta

import boto3
from botocore.exceptions import ClientError
from celery import shared_task
from sqlalchemy import and_, func, distinct

from app.infrastructure.worker.celery_app import celery_app  # noqa: F401
from app.core.config import settings
from app.infrastructure.db.session import SessionLocal
from app.domain.models.extraction_job import (
    ExtractionJob,
    ExtractionJobStatus,
    ExtractionTemplate,
)
from app.domain.models.document import Document
from app.domain.models.tenant import Tenant

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# S3 helpers (reuse same boto3 config as doc_service)
# ──────────────────────────────────────────────────────────────────────────────

def _get_s3():
    return boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT_URL,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        region_name=settings.S3_REGION,
    )


def _list_inbox_objects(s3, bucket: str, prefix: str) -> list[dict]:
    """List PDF objects in inbox/ prefix."""
    objects = []
    try:
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.lower().endswith(".pdf") and obj["Size"] > 0:
                    objects.append(obj)
    except ClientError as e:
        logger.error(f"[FileOperator] S3 list failed: {e}")
    return objects


def _move_s3_object(s3, bucket: str, src_key: str, dst_key: str):
    """Copy object to destination then delete source (atomic move)."""
    s3.copy_object(
        Bucket=bucket,
        CopySource={"Bucket": bucket, "Key": src_key},
        Key=dst_key,
    )
    s3.delete_object(Bucket=bucket, Key=src_key)


def _parse_tenant_from_key(key: str, prefix: str) -> str | None:
    """Extract tenant_id from inbox path.

    Expected layout:  inbox/{tenant_id}/filename.pdf
    """
    remainder = key[len(prefix):]  # strip prefix
    parts = remainder.split("/", 1)
    if len(parts) == 2 and parts[0]:
        return parts[0]
    return None


# ──────────────────────────────────────────────────────────────────────────────
# FileOperator — hot-folder poller
# ──────────────────────────────────────────────────────────────────────────────

@shared_task(bind=False, ignore_result=True)
def poll_inbox():
    """Poll MinIO inbox/ for new PDFs and auto-process them.

    Expected bucket structure:
        inbox/{tenant_id}/file1.pdf
        inbox/{tenant_id}/file2.pdf

    For each PDF:
      1. Download content
      2. Auto-detect template (TemplateManager.detect_template)
      3. Auto-detect extraction mode
      4. Create Document + Job records
      5. Move file to processed/ prefix
      6. Dispatch extract_document_task

    Runs periodically via Celery Beat.
    """
    if not settings.FILE_OPERATOR_ENABLED:
        return {"skipped": True, "reason": "FILE_OPERATOR_ENABLED=false"}

    s3 = _get_s3()
    bucket = settings.S3_BUCKET_NAME
    inbox = settings.FILE_OPERATOR_INBOX_PREFIX
    processed = settings.FILE_OPERATOR_PROCESSED_PREFIX

    objects = _list_inbox_objects(s3, bucket, inbox)
    if not objects:
        return {"picked_up": 0}

    logger.info(f"[FileOperator] Found {len(objects)} PDF(s) in inbox/")

    db = SessionLocal()
    picked = 0
    errors = 0

    try:
        from app.application.doc_service import DocumentService
        from app.application.template_service import TemplateManager
        from app.application.job_service import JobManager
        from app.infrastructure.worker.extraction_tasks import extract_document_task

        doc_service = DocumentService(db)
        tpl_manager = TemplateManager(db)
        job_manager = JobManager(db)

        # Group files by tenant for batch_id assignment
        tenant_files: dict[str, list[dict]] = {}
        for obj in objects:
            tenant_id = _parse_tenant_from_key(obj["Key"], inbox)
            if not tenant_id:
                logger.warning(f"[FileOperator] Skipping {obj['Key']}: cannot parse tenant_id")
                continue
            tenant_files.setdefault(tenant_id, []).append(obj)

        for tenant_id, files in tenant_files.items():
            # Verify tenant exists
            tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
            if not tenant:
                logger.warning(f"[FileOperator] Unknown tenant {tenant_id}, skipping {len(files)} files")
                continue

            batch_id = uuid.uuid4()

            for obj in files:
                key = obj["Key"]
                filename = key.rsplit("/", 1)[-1]

                try:
                    # 1. Download
                    resp = s3.get_object(Bucket=bucket, Key=key)
                    content = resp["Body"].read()

                    # 2. Auto-detect template
                    first_page_text = _extract_first_page_text(content)
                    matched_tpl = tpl_manager.detect_template(
                        tenant_id=tenant_id,
                        filename=filename,
                        first_page_text=first_page_text,
                    )
                    if not matched_tpl:
                        logger.warning(f"[FileOperator] No template match for {filename} (tenant={tenant_id})")
                        errors += 1
                        continue

                    # 3. Auto-detect mode
                    mode = _auto_detect_mode(content)

                    # 4. Create document
                    document = doc_service.create_document(
                        tenant_id=tenant_id,
                        file_content=content,
                        filename=filename,
                        user_id=str(tenant.created_by) if hasattr(tenant, "created_by") else "system",
                    )

                    # 5. Create job
                    job = job_manager.create_job(
                        tenant_id=tenant_id,
                        template_id=str(matched_tpl.id),
                        document_id=str(document.id),
                        user_id="system",
                        batch_id=str(batch_id),
                        mode=mode,
                    )

                    # 6. Move to processed/
                    dst_key = f"{processed}{tenant_id}/{filename}"
                    _move_s3_object(s3, bucket, key, dst_key)

                    # 7. Dispatch extraction
                    extract_document_task.delay(str(job.id))

                    picked += 1
                    logger.info(
                        f"[FileOperator] Queued {filename} → job={job.id} "
                        f"tpl={matched_tpl.name} mode={mode} batch={batch_id}"
                    )

                except Exception as e:
                    logger.error(f"[FileOperator] Failed to process {key}: {e}")
                    errors += 1
                    db.rollback()

    except Exception as e:
        logger.error(f"[FileOperator] Fatal error: {e}")
    finally:
        db.close()

    result = {"picked_up": picked, "errors": errors}
    logger.info(f"[FileOperator] Done: {result}")
    return result


def _auto_detect_mode(content: bytes) -> str:
    """Detect extraction mode from PDF content."""
    try:
        import io
        import pdfplumber

        with pdfplumber.open(io.BytesIO(content)) as pdf:
            if not pdf.pages:
                return "standard"
            page = pdf.pages[0]
            text = (page.extract_text() or "").strip()
            tables = page.find_tables()
            if tables or len(text) < 100:
                return "block"
            return "standard"
    except Exception:
        return "standard"


def _extract_first_page_text(content: bytes) -> str:
    """Extract text from the first page for template matching."""
    try:
        import io
        import pdfplumber

        with pdfplumber.open(io.BytesIO(content)) as pdf:
            if pdf.pages:
                return (pdf.pages[0].extract_text() or "").strip()
    except Exception:
        pass
    return ""


# ──────────────────────────────────────────────────────────────────────────────
# BatchCloser — auto-close completed batches + trigger aggregation
# ──────────────────────────────────────────────────────────────────────────────

# Terminal states where no further processing will happen
_TERMINAL_STATES = frozenset({
    ExtractionJobStatus.APPROVED,
    ExtractionJobStatus.REJECTED,
    ExtractionJobStatus.AGGREGATED,
    ExtractionJobStatus.FAILED,
})

# States that indicate batch is "closeable" for aggregation
_APPROVED_STATES = frozenset({
    ExtractionJobStatus.APPROVED,
})


@shared_task(bind=False, ignore_result=True)
def close_completed_batches():
    """Find batches where all jobs have reached terminal states and trigger aggregation.

    A batch is "closeable" when:
      - ALL jobs in the batch are in a terminal state (approved/rejected/failed/aggregated)
      - At least ONE job is approved (something to aggregate)
      - The batch hasn't already been aggregated

    For each closeable batch:
      1. Collect all approved job IDs
      2. Determine template (all jobs in a batch share the same template)
      3. Call AggregationService.aggregate()
      4. Mark jobs as AGGREGATED via workflow transition

    Runs periodically via Celery Beat.
    """
    db = SessionLocal()
    closed = 0
    errors = 0

    try:
        from app.application.aggregation_service import AggregationService
        from app.domain.workflow import transition_job_state, JobStatus

        agg_service = AggregationService(db)

        # Find distinct batch_ids that have at least one non-aggregated job
        active_batches = (
            db.query(distinct(ExtractionJob.batch_id))
            .filter(
                ExtractionJob.batch_id.isnot(None),
                ExtractionJob.status != ExtractionJobStatus.AGGREGATED,
            )
            .all()
        )
        batch_ids = [row[0] for row in active_batches if row[0]]

        if not batch_ids:
            return {"closed": 0, "reason": "no active batches"}

        for batch_id in batch_ids:
            try:
                # Load all jobs in this batch
                batch_jobs = (
                    db.query(ExtractionJob)
                    .filter(ExtractionJob.batch_id == batch_id)
                    .all()
                )
                if not batch_jobs:
                    continue

                statuses = {j.status for j in batch_jobs}
                all_terminal = statuses.issubset(_TERMINAL_STATES)

                if not all_terminal:
                    # Check max wait time — force-close stale batches
                    oldest = min(j.created_at for j in batch_jobs)
                    age_minutes = (datetime.utcnow() - oldest).total_seconds() / 60
                    if age_minutes < settings.BATCH_CLOSER_MAX_WAIT_MINUTES:
                        continue
                    logger.warning(
                        f"[BatchCloser] Force-closing stale batch {batch_id} "
                        f"(age={age_minutes:.0f}min, statuses={statuses})"
                    )

                approved_jobs = [j for j in batch_jobs if j.status == ExtractionJobStatus.APPROVED]
                if not approved_jobs:
                    logger.info(f"[BatchCloser] Batch {batch_id} complete but 0 approved jobs — skipping aggregation")
                    continue

                if not settings.BATCH_CLOSER_AUTO_AGGREGATE:
                    logger.info(f"[BatchCloser] Batch {batch_id} ready but auto-aggregate disabled")
                    continue

                # All approved jobs should share the same template
                template_ids = {str(j.template_id) for j in approved_jobs}
                if len(template_ids) > 1:
                    logger.warning(
                        f"[BatchCloser] Batch {batch_id} has mixed templates {template_ids}, "
                        "aggregating per template"
                    )

                tenant_id = str(batch_jobs[0].tenant_id)

                for tpl_id in template_ids:
                    tpl_jobs = [j for j in approved_jobs if str(j.template_id) == tpl_id]
                    job_ids = [str(j.id) for j in tpl_jobs]

                    try:
                        report = agg_service.aggregate(
                            template_id=tpl_id,
                            job_ids=job_ids,
                            tenant_id=tenant_id,
                            report_name=f"Auto-report batch {str(batch_id)[:8]}",
                            user_id="system",
                            description=f"Auto-aggregated by BatchCloser at {datetime.utcnow().isoformat()}",
                        )

                        # Mark jobs as AGGREGATED
                        for j in tpl_jobs:
                            try:
                                transition_job_state(
                                    db,
                                    job_id=str(j.id),
                                    to_state=JobStatus.AGGREGATED,
                                    actor_type="system",
                                    reason=f"auto-aggregated by BatchCloser (report={report.id})",
                                )
                            except Exception as te:
                                logger.warning(f"[BatchCloser] Failed to transition job {j.id}: {te}")

                        db.commit()
                        closed += 1
                        logger.info(
                            f"[BatchCloser] Batch {batch_id} → aggregated "
                            f"{len(tpl_jobs)} jobs into report {report.id}"
                        )

                        # Auto-export: render Excel + Word to S3
                        _auto_export_report(db, report, tpl_id, tenant_id)

                    except Exception as ae:
                        logger.error(f"[BatchCloser] Aggregation failed for batch {batch_id} tpl {tpl_id}: {ae}")
                        db.rollback()
                        errors += 1

            except Exception as be:
                logger.error(f"[BatchCloser] Error processing batch {batch_id}: {be}")
                db.rollback()
                errors += 1

    except Exception as e:
        logger.error(f"[BatchCloser] Fatal error: {e}")
    finally:
        db.close()

    result = {"closed": closed, "errors": errors}
    logger.info(f"[BatchCloser] Done: {result}")
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Auto-export helper — renders Excel + Word to S3 after aggregation
# ──────────────────────────────────────────────────────────────────────────────

def _auto_export_report(db, report, template_id: str, tenant_id: str):
    """Best-effort auto-export: save Excel and (optionally) Word to S3.

    Files are stored at:
        exports/{tenant_id}/{report_id}.xlsx
        exports/{tenant_id}/{report_id}.docx
    """
    from app.application.aggregation_service import AggregationService, ExportService, build_word_export_context
    from app.application.template_service import TemplateManager

    s3 = _get_s3()
    bucket = settings.S3_BUCKET_NAME
    report_id = str(report.id)

    # ── Excel export ─────────────────────────────────────────────
    try:
        jobs = (
            db.query(ExtractionJob)
            .filter(ExtractionJob.id.in_(report.job_ids or []))
            .all()
        )
        excel_buf = ExportService.to_excel(report, jobs=jobs)
        excel_key = f"exports/{tenant_id}/{report_id}.xlsx"
        s3.put_object(
            Bucket=bucket,
            Key=excel_key,
            Body=excel_buf.getvalue(),
            ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        logger.info(f"[AutoExport] Excel saved: {excel_key}")
    except Exception as e:
        logger.warning(f"[AutoExport] Excel failed for report {report_id}: {e}")

    # ── Word export (only if template has a saved .docx) ─────────
    try:
        tpl_manager = TemplateManager(db)
        template = tpl_manager.get_template(template_id, tenant_id)
        if template and template.word_template_s3_key:
            from app.utils.word_export import render_word_template

            s3_resp = s3.get_object(Bucket=bucket, Key=template.word_template_s3_key)
            template_bytes = s3_resp["Body"].read()

            extra_context = {
                "report_name": report.name,
                "report_description": report.description or "",
                "total_jobs": report.total_jobs,
                "approved_jobs": report.approved_jobs,
            }
            context = build_word_export_context(
                report.aggregated_data,
                extra_context=extra_context,
            )
            rendered = render_word_template(
                template_bytes=template_bytes,
                context_data=context,
            )
            word_key = f"exports/{tenant_id}/{report_id}.docx"
            s3.put_object(
                Bucket=bucket,
                Key=word_key,
                Body=rendered,
                ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            logger.info(f"[AutoExport] Word saved: {word_key}")
    except Exception as e:
        logger.warning(f"[AutoExport] Word failed for report {report_id}: {e}")
