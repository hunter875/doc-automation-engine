"""Service for daily report review workflow."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import not_
from sqlalchemy.orm import Session

from app.core.exceptions import ProcessingError
from app.domain.models.daily_report_edit import DailyReportEdit
from app.domain.models.daily_report_review import DailyReportReview
from app.domain.models.extraction_job import ExtractionJob
from app.engines.extraction.schemas import BlockExtractionOutput
from app.engines.extraction.kv30_enrichment import enrich_kv30_block_output


def unwrap_extracted_data(extracted_data: dict) -> dict:
    """Extract BlockExtractionOutput from wrapper if present."""
    if isinstance(extracted_data, dict) and isinstance(extracted_data.get("data"), dict):
        nested = extracted_data["data"]
        if "header" in nested:
            return nested
    return extracted_data


def validate_block_output(data: dict) -> dict:
    """Validate and return canonical dict."""
    try:
        model = BlockExtractionOutput.model_validate(data)
        return model.model_dump()
    except Exception as e:
        raise ProcessingError(message=f"Invalid report data: {e}")


class DailyReportReviewService:
    """Review workflow service."""

    def __init__(self, db: Session):
        self.db = db

    def get_latest_extraction_job(
        self, tenant_id: UUID, template_id: UUID, report_date: date
    ) -> Optional[ExtractionJob]:
        """Get latest usable snapshot job (exclude failed/pending/processing)."""
        return (
            self.db.query(ExtractionJob)
            .filter(
                ExtractionJob.tenant_id == tenant_id,
                ExtractionJob.template_id == template_id,
                ExtractionJob.report_date == report_date,
                ExtractionJob.parser_used == "google_sheets",
                ExtractionJob.sheet_revision_hash.is_not(None),
                not_(ExtractionJob.status.in_(["failed", "pending", "processing"])),
            )
            .order_by(ExtractionJob.report_version.desc(), ExtractionJob.created_at.desc())
            .first()
        )

    def get_latest_manual_edit(
        self, tenant_id: UUID, template_id: UUID, report_date: date
    ) -> Optional[DailyReportEdit]:
        """Get latest manual edit."""
        return (
            self.db.query(DailyReportEdit)
            .filter(
                DailyReportEdit.tenant_id == tenant_id,
                DailyReportEdit.template_id == template_id,
                DailyReportEdit.report_date == report_date,
            )
            .order_by(DailyReportEdit.created_at.desc(), DailyReportEdit.id.desc())
            .first()
        )

    def get_latest_review(
        self, tenant_id: UUID, template_id: UUID, report_date: date
    ) -> Optional[DailyReportReview]:
        """Get latest review decision."""
        return (
            self.db.query(DailyReportReview)
            .filter(
                DailyReportReview.tenant_id == tenant_id,
                DailyReportReview.template_id == template_id,
                DailyReportReview.report_date == report_date,
            )
            .order_by(DailyReportReview.created_at.desc(), DailyReportReview.id.desc())
            .first()
        )

    def get_effective_report(self, tenant_id: UUID, template_id: UUID, report_date: date) -> dict:
        """Return effective report based on review state."""
        latest_job = self.get_latest_extraction_job(tenant_id, template_id, report_date)
        if not latest_job:
            raise ProcessingError(message=f"No extraction job for date {report_date.isoformat()}")

        latest_edit = self.get_latest_manual_edit(tenant_id, template_id, report_date)
        latest_review = self.get_latest_review(tenant_id, template_id, report_date)

        def build_response(source: str, data: dict, review_status: Optional[str] = None, review_id: Optional[str] = None, manual_edit_id: Optional[str] = None, is_finalized: bool = False, approved_source: Optional[str] = None, has_conflict: bool = False):
            # Apply KV30 enrichment if this is a google_sheets KV30 report
            if latest_job.parser_used == "google_sheets":
                report_date_str = report_date.strftime("%d/%m/%Y") if report_date else None
                data = enrich_kv30_block_output(data, report_date_str)

            return {
                "date": report_date.isoformat(),
                "source": source,
                "data": data,
                "review_status": review_status,
                "is_finalized": is_finalized,
                "review_id": review_id,
                "manual_edit_id": manual_edit_id,
                "job_id": str(latest_job.id),
                "has_manual_edits": latest_edit is not None,
                "source_displayed_by_default": source,
                "approved_source": approved_source,
                "has_conflict": has_conflict,
                "validation_report": latest_job.validation_report or {},
            }

        # Finalized: locked snapshot
        if latest_review and latest_review.status == "finalized":
            if not latest_review.approved_data:
                raise ProcessingError(message="Finalized review missing approved_data")
            return build_response(
                source=latest_review.approved_source or "auto_sync",
                data=latest_review.approved_data,
                review_status="finalized",
                review_id=str(latest_review.id),
                manual_edit_id=str(latest_review.manual_edit_id) if latest_review.manual_edit_id else None,
                is_finalized=True,
                approved_source=latest_review.approved_source,
            )

        # Approved (but not finalized): approved snapshot
        if latest_review and latest_review.status == "approved":
            if not latest_review.approved_data:
                raise ProcessingError(message="Approved review missing approved_data")
            return build_response(
                source=latest_review.approved_source or "auto_sync",
                data=latest_review.approved_data,
                review_status="approved",
                review_id=str(latest_review.id),
                manual_edit_id=str(latest_review.manual_edit_id) if latest_review.manual_edit_id else None,
                approved_source=latest_review.approved_source,
            )

        # Conflict detected: show approved if exists else auto
        if latest_review and latest_review.status == "conflict_detected":
            if latest_review.approved_data:
                return build_response(
                    source=latest_review.approved_source or "auto_sync",
                    data=latest_review.approved_data,
                    review_status="conflict_detected",
                    review_id=str(latest_review.id),
                    manual_edit_id=str(latest_review.manual_edit_id) if latest_review.manual_edit_id else None,
                    approved_source=latest_review.approved_source,
                    has_conflict=True,
                )
            else:
                # No approved yet; fall back to auto
                auto_data = unwrap_extracted_data(latest_job.extracted_data)
                return build_response(
                    source="auto_sync",
                    data=auto_data,
                    review_status="conflict_detected",
                    has_conflict=True,
                )

        # Rejected: show auto data, but keep manual_edit_id from review
        if latest_review and latest_review.status == "rejected":
            auto_data = unwrap_extracted_data(latest_job.extracted_data)
            return build_response(
                source="auto_sync",
                data=auto_data,
                review_status="rejected",
                review_id=str(latest_review.id),
                manual_edit_id=str(latest_review.manual_edit_id) if latest_review.manual_edit_id else None,
            )

        # Manual edited (and no review decision)
        if latest_edit:
            return build_response(
                source="manual_edit",
                data=latest_edit.edited_data,
                review_status="manual_edited",
                manual_edit_id=str(latest_edit.id),
            )

        # Auto synced (no manual edit)
        auto_data = unwrap_extracted_data(latest_job.extracted_data)
        return build_response(
            source="auto_sync",
            data=auto_data,
            review_status="auto_synced",
        )

    def approve_report(
        self,
        tenant_id: UUID,
        template_id: UUID,
        report_date: date,
        source: str,
        manual_edit_id: Optional[UUID] = None,
        reason: Optional[str] = None,
        reviewed_by: Optional[UUID] = None,
    ) -> dict:
        latest_job = self.get_latest_extraction_job(tenant_id, template_id, report_date)
        if not latest_job:
            raise ProcessingError(message=f"No extraction job for date {report_date.isoformat()}")

        if source == "auto_sync":
            approved_data = unwrap_extracted_data(latest_job.extracted_data)
            approved_source = "auto_sync"
            manual_edit_id = None
        elif source == "manual_edit":
            if not manual_edit_id:
                raise ProcessingError(message="manual_edit_id required for manual_edit source")
            edit = (
                self.db.query(DailyReportEdit)
                .filter(
                    DailyReportEdit.id == manual_edit_id,
                    DailyReportEdit.tenant_id == tenant_id,
                    DailyReportEdit.template_id == template_id,
                    DailyReportEdit.report_date == report_date,
                )
                .first()
            )
            if not edit:
                raise ProcessingError(message=f"Manual edit not found: {manual_edit_id}")
            approved_data = edit.edited_data
            approved_source = "manual_edit"
        else:
            raise ProcessingError(message=f"Invalid source: {source}")

        # Validate
        validate_block_output(approved_data)

        # Create review
        review = DailyReportReview(
            tenant_id=tenant_id,
            template_id=template_id,
            report_date=report_date,
            extraction_job_id=latest_job.id,
            manual_edit_id=manual_edit_id,
            status="approved",
            approved_data=approved_data,
            approved_source=approved_source,
            reason=reason,
            reviewed_by=reviewed_by,
            reviewed_at=datetime.utcnow(),
            base_extraction_job_id=latest_job.id,
            base_extraction_hash=latest_job.sheet_revision_hash,
        )
        self.db.add(review)
        self.db.commit()
        self.db.refresh(review)

        return self.get_effective_report(tenant_id, template_id, report_date)

    def reject_manual_edit(
        self,
        tenant_id: UUID,
        template_id: UUID,
        report_date: date,
        manual_edit_id: UUID,
        reason: Optional[str] = None,
        reviewed_by: Optional[UUID] = None,
    ) -> dict:
        edit = (
            self.db.query(DailyReportEdit)
            .filter(
                DailyReportEdit.id == manual_edit_id,
                DailyReportEdit.tenant_id == tenant_id,
                DailyReportEdit.template_id == template_id,
                DailyReportEdit.report_date == report_date,
            )
            .first()
        )
        if not edit:
            raise ProcessingError(message=f"Manual edit not found: {manual_edit_id}")

        latest_job = self.get_latest_extraction_job(tenant_id, template_id, report_date)
        if not latest_job:
            raise ProcessingError(message=f"No extraction job for date {report_date.isoformat()}")

        review = DailyReportReview(
            tenant_id=tenant_id,
            template_id=template_id,
            report_date=report_date,
            extraction_job_id=latest_job.id,
            manual_edit_id=manual_edit_id,
            status="rejected",
            approved_data=None,
            approved_source=None,
            reason=reason,
            reviewed_by=reviewed_by,
            reviewed_at=datetime.utcnow(),
        )
        self.db.add(review)
        self.db.commit()
        self.db.refresh(review)

        return self.get_effective_report(tenant_id, template_id, report_date)

    def finalize_report(
        self,
        tenant_id: UUID,
        template_id: UUID,
        report_date: date,
        source: str,
        manual_edit_id: Optional[UUID] = None,
        reason: Optional[str] = None,
        reviewed_by: Optional[UUID] = None,
    ) -> dict:
        latest_job = self.get_latest_extraction_job(tenant_id, template_id, report_date)
        if not latest_job:
            raise ProcessingError(message=f"No extraction job for date {report_date.isoformat()}")

        if source == "auto_sync":
            approved_data = unwrap_extracted_data(latest_job.extracted_data)
            approved_source = "auto_sync"
            manual_edit_id = None
        elif source == "manual_edit":
            if not manual_edit_id:
                raise ProcessingError(message="manual_edit_id required for manual_edit source")
            edit = (
                self.db.query(DailyReportEdit)
                .filter(
                    DailyReportEdit.id == manual_edit_id,
                    DailyReportEdit.tenant_id == tenant_id,
                    DailyReportEdit.template_id == template_id,
                    DailyReportEdit.report_date == report_date,
                )
                .first()
            )
            if not edit:
                raise ProcessingError(message=f"Manual edit not found: {manual_edit_id}")
            approved_data = edit.edited_data
            approved_source = "manual_edit"
        else:
            raise ProcessingError(message=f"Invalid source: {source}")

        validate_block_output(approved_data)

        review = DailyReportReview(
            tenant_id=tenant_id,
            template_id=template_id,
            report_date=report_date,
            extraction_job_id=latest_job.id,
            manual_edit_id=manual_edit_id,
            status="finalized",
            approved_data=approved_data,
            approved_source=approved_source,
            reason=reason,
            reviewed_by=reviewed_by,
            reviewed_at=datetime.utcnow(),
            finalized_at=datetime.utcnow(),
            base_extraction_job_id=latest_job.id,
            base_extraction_hash=latest_job.sheet_revision_hash,
        )
        self.db.add(review)
        self.db.commit()
        self.db.refresh(review)

        return self.get_effective_report(tenant_id, template_id, report_date)

    def detect_report_conflict(self, tenant_id: UUID, template_id: UUID, report_date: date) -> bool:
        latest_review = self.get_latest_review(tenant_id, template_id, report_date)
        if not latest_review:
            return False
        if latest_review.status not in ("approved", "finalized"):
            return False

        latest_job = self.get_latest_extraction_job(tenant_id, template_id, report_date)
        if not latest_job:
            return False

        # If base extraction job changed
        if latest_review.base_extraction_job_id and latest_review.base_extraction_job_id != latest_job.id:
            return True
        # If hash changed
        if latest_review.base_extraction_hash and latest_review.base_extraction_hash != latest_job.sheet_revision_hash:
            return True
        return False

    def mark_conflict_if_needed(self, tenant_id: UUID, template_id: UUID, report_date: date) -> Optional[DailyReportReview]:
        if self.detect_report_conflict(tenant_id, template_id, report_date):
            latest_job = self.get_latest_extraction_job(tenant_id, template_id, report_date)
            if latest_job:
                review = DailyReportReview(
                    tenant_id=tenant_id,
                    template_id=template_id,
                    report_date=report_date,
                    extraction_job_id=latest_job.id,
                    status="conflict_detected",
                    approved_data=None,
                    approved_source=None,
                    reason="New auto-sync data exists after reviewed/finalized report",
                )
                self.db.add(review)
                self.db.commit()
                self.db.refresh(review)
                return review
        return None

    def diff_reports(self, auto_data: dict, compare_data: dict, max_changes: int = 500) -> list[dict]:
        """Simple recursive diff, index-based for lists."""
        changes: list[dict] = []

        def recurse(a: Any, b: Any, path: str):
            if len(changes) >= max_changes:
                return
            if a == b:
                return
            if isinstance(a, dict) and isinstance(b, dict):
                for key in a:
                    if key not in b:
                        changes.append({
                            "path": f"{path}.{key}" if path else key,
                            "auto_value": a[key],
                            "review_value": None,
                            "change_type": "removed",
                        })
                    else:
                        recurse(a[key], b[key], f"{path}.{key}" if path else key)
                        if len(changes) >= max_changes:
                            return
                for key in b:
                    if key not in a:
                        changes.append({
                            "path": f"{path}.{key}" if path else key,
                            "auto_value": None,
                            "review_value": b[key],
                            "change_type": "added",
                        })
                        if len(changes) >= max_changes:
                            return
            elif isinstance(a, list) and isinstance(b, list):
                # index-based compare
                max_len = max(len(a), len(b))
                for i in range(max_len):
                    ai = a[i] if i < len(a) else None
                    bi = b[i] if i < len(b) else None
                    recurse(ai, bi, f"{path}[{i}]")
                    if len(changes) >= max_changes:
                        return
            else:
                changes.append({
                    "path": path,
                    "auto_value": a,
                    "review_value": b,
                    "change_type": "changed",
                })

        recurse(auto_data, compare_data, "")
        return changes

    def get_report_diff(
        self, tenant_id: UUID, template_id: UUID, report_date: date, against: str = "latest_manual_or_review"
    ) -> dict:
        latest_job = self.get_latest_extraction_job(tenant_id, template_id, report_date)
        if not latest_job:
            raise ProcessingError(message=f"No extraction job for date {report_date.isoformat()}")
        auto_data = unwrap_extracted_data(latest_job.extracted_data)

        compare_data = None
        compare_source = None

        if against == "latest_manual_or_review":
            latest_review = self.get_latest_review(tenant_id, template_id, report_date)
            if latest_review and latest_review.approved_data:
                compare_data = latest_review.approved_data
                compare_source = latest_review.status
            else:
                latest_edit = self.get_latest_manual_edit(tenant_id, template_id, report_date)
                if latest_edit:
                    compare_data = latest_edit.edited_data
                    compare_source = "manual_edit"
                else:
                    compare_source = "auto_sync"
                    compare_data = auto_data
        else:
            raise ProcessingError(message=f"Invalid against: {against}")

        changes = self.diff_reports(auto_data, compare_data)
        return {
            "report_date": report_date.isoformat(),
            "base_source": "auto_sync",
            "compare_source": compare_source,
            "changes": changes,
        }
