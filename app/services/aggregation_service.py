"""Aggregation & Export service for Engine 2.

Handles the Reduce phase: merge N extraction JSONs → 1 report.
Uses Pandas for computation. AI is NOT involved in this step.
"""

import io
import itertools
import logging
from decimal import Decimal, InvalidOperation
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.exceptions import ProcessingError
from app.models.extraction import (
    AggregationReport,
    ExtractionJob,
    ExtractionJobStatus,
    ExtractionTemplate,
)

logger = logging.getLogger(__name__)


def build_word_export_context(
    aggregated_data: dict[str, Any],
    *,
    record_index: int | None = None,
    extra_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a clean DTO for Word rendering from aggregation payload.

    Export layer should receive a template-ready context only, without touching
    internal aggregation keys.
    """
    strip_keys = {"_source_records", "_flat_records", "_metadata", "metrics"}
    payload = aggregated_data or {}

    records = payload.get("records", [])
    safe_records = records if isinstance(records, list) else []

    context: dict[str, Any] = {
        "records": safe_records,
    }

    selected_record: dict[str, Any] = {}
    selected_index = int(record_index or 0)
    if safe_records:
        if 0 <= selected_index < len(safe_records) and isinstance(safe_records[selected_index], dict):
            selected_record = dict(safe_records[selected_index])
        elif isinstance(safe_records[0], dict):
            selected_record = dict(safe_records[0])
            selected_index = 0

    context["record"] = selected_record
    context["record_index"] = selected_index

    if selected_record:
        context.update(selected_record)

    for key, value in payload.items():
        if key in strip_keys or key.startswith("_") or key == "records":
            continue
        context[key] = value

    if extra_context:
        context.update(extra_context)

    return context


def _sanitize_for_json(obj: Any) -> Any:
    """Recursively replace NaN/Inf with None so JSONB INSERT doesn't crash."""
    import math
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_json(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    # numpy scalar types
    try:
        import numpy as np
        if isinstance(obj, (np.floating, np.integer)):
            v = obj.item()
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                return None
            return v
    except ImportError:
        pass
    return obj


IGNORE_KEYS = {
    "stt", "id", "index", "ghi_ch", "ghi_chu", "danh_m_c",
    "danh_muc", "tieu_de", "danh_m_c_ch_ti_u_th_ng_k",
}


def _extract_number_from_garbage(val: Any) -> Decimal:
    """Extract numeric value from noisy nested structures produced by LLM."""
    if val is None:
        return Decimal("0")

    if isinstance(val, bool):
        return Decimal("1") if val else Decimal("0")

    if isinstance(val, (int, float, Decimal)):
        return Decimal(str(val))

    if isinstance(val, str):
        text = val.strip().replace(",", ".")
        if not text:
            return Decimal("0")
        try:
            return Decimal(text)
        except InvalidOperation:
            return Decimal("0")

    if isinstance(val, list):
        return sum((_extract_number_from_garbage(item) for item in val), Decimal("0"))

    if isinstance(val, dict):
        dict_sum = Decimal("0")
        for key, value in val.items():
            if str(key).lower().strip() in IGNORE_KEYS:
                continue
            dict_sum += _extract_number_from_garbage(value)
        return dict_sum

    return Decimal("0")


def _default_value_for_field(field_def: dict[str, Any]) -> Any:
    """Return a safe default render value for a schema field."""
    field_type = (field_def or {}).get("type", "string")
    if field_type == "array":
        return []
    if field_type == "number":
        return 0
    if field_type == "boolean":
        return False
    if field_type == "object":
        return {}
    return ""


def _normalize_master_payload(
    schema_definition: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Force payload into a docxtpl-safe shape based on template schema.

    Rules:
      - top-level scalar fields always exist
      - top-level arrays always exist and default to []
      - values remain flat for static fields
    """
    normalized = dict(payload or {})
    for field_def in schema_definition.get("fields", []):
        field_name = field_def.get("name")
        if not field_name:
            continue

        if field_name not in normalized or normalized[field_name] is None:
            normalized[field_name] = _default_value_for_field(field_def)
            continue

        if field_def.get("type") == "array":
            current = normalized.get(field_name)
            if current is None:
                normalized[field_name] = []
            elif not isinstance(current, list):
                normalized[field_name] = [current]

    return normalized


class AggregationService:
    """Pandas-based aggregation engine."""

    def __init__(self, db: Session):
        self.db = db

    def aggregate(
        self,
        template_id: str,
        job_ids: list[str],
        tenant_id: str,
        report_name: str,
        user_id: str,
        description: str = None,
    ) -> AggregationReport:
        """Aggregate multiple approved extraction jobs into a report.

        Args:
            template_id: Template UUID (all jobs must use same template)
            job_ids: List of approved job UUIDs
            tenant_id: Tenant UUID
            report_name: Name for the report
            user_id: Creator user UUID
            description: Optional description

        Returns:
            AggregationReport with aggregated_data
        """
        import pandas as pd

        # 1. Validate template
        template = (
            self.db.query(ExtractionTemplate)
            .filter(
                ExtractionTemplate.id == template_id,
                ExtractionTemplate.tenant_id == tenant_id,
            )
            .first()
        )
        if not template:
            raise ProcessingError(message=f"Template {template_id} not found")

        # 2. Load jobs — only approved ones
        jobs = (
            self.db.query(ExtractionJob)
            .filter(
                ExtractionJob.id.in_(job_ids),
                ExtractionJob.tenant_id == tenant_id,
                ExtractionJob.template_id == template_id,
                ExtractionJob.status == ExtractionJobStatus.APPROVED,
            )
            .all()
        )

        if not jobs:
            raise ProcessingError(message="No approved jobs found for the given IDs")

        # 3. Collect data (prefer reviewed_data over extracted_data)
        data_rows = []
        for job in jobs:
            row = job.reviewed_data or job.extracted_data
            if row:
                data_rows.append(row)

        if not data_rows:
            raise ProcessingError(message="No extraction data available in jobs")

        # 4. Get aggregation rules
        agg_rules = template.aggregation_rules or {}
        rules = agg_rules.get("rules", [])
        sort_by = agg_rules.get("sort_by")

        # 5. Build DataFrame using json_normalize for proper array flattening
        # This handles nested objects and arrays correctly
        try:
            df = pd.json_normalize(data_rows, sep="_")
        except Exception:
            # Fallback: basic DataFrame if json_normalize fails on complex structures
            df = pd.DataFrame(data_rows)

        # Sort if requested (best-effort, robust for mixed payloads)
        if sort_by:
            try:
                data_rows = sorted(
                    data_rows,
                    key=lambda row: (
                        _extract_number_from_garbage((row or {}).get(sort_by))
                        if isinstance(row, dict) else Decimal("0")
                    ),
                )
            except Exception as exc:
                logger.warning("Cannot sort by '%s': %s", sort_by, exc)

        # 6. Apply aggregation rules
        aggregated_data: dict[str, Any] = {}

        for rule in rules:
            output_field = rule["output_field"]
            source_field = rule["source_field"]
            method = rule.get("method", "SUM").upper()
            round_digits = rule.get("round_digits")

            try:
                if method == "CONCAT":
                    all_arrays = []
                    for row in data_rows:
                        val = row.get(source_field)
                        if isinstance(val, list):
                            all_arrays.extend(val)
                        elif val is not None:
                            all_arrays.append(val)
                    aggregated_data[output_field] = all_arrays

                elif method == "LAST":
                    val = None
                    for row in reversed(data_rows):
                        if source_field in row and row[source_field] is not None:
                            val = row[source_field]
                            break
                    aggregated_data[output_field] = val

                elif method in {"SUM", "AVG", "MAX", "MIN", "COUNT"}:
                    extracted_numbers: list[Decimal] = []
                    for row in data_rows:
                        val = row.get(source_field)
                        if val is None:
                            continue
                        if method == "COUNT":
                            extracted_numbers.append(Decimal("1"))
                        else:
                            extracted_numbers.append(_extract_number_from_garbage(val))

                    if not extracted_numbers:
                        result: Decimal | None = Decimal("0") if method != "AVG" else None
                    else:
                        if method in {"SUM", "COUNT"}:
                            result = sum(extracted_numbers)
                        elif method == "AVG":
                            result = sum(extracted_numbers) / Decimal(len(extracted_numbers))
                        elif method == "MAX":
                            result = max(extracted_numbers)
                        else:
                            result = min(extracted_numbers)

                    if result is not None:
                        if round_digits is not None:
                            result_value: Any = round(float(result), round_digits)
                        else:
                            result_value = int(result) if result == int(result) else float(result)
                    else:
                        result_value = None

                    aggregated_data[output_field] = result_value
                else:
                    aggregated_data[output_field] = None
                    logger.warning(f"Unknown aggregation method '{method}'")

            except Exception as e:
                logger.error(f"Aggregation error for rule '{output_field}': {e}")
                aggregated_data[output_field] = None

        # 7. Build ONE summary record from the aggregated results.
        #    output_field == source_field (scanner giờ giữ nguyên tên)
        #    nên chỉ cần lấy aggregated_data trực tiếp, không cần set 2 key.
        summary_record: dict[str, Any] = {}
        for rule in rules:
            output_field = rule["output_field"]
            val = aggregated_data.get(output_field)
            summary_record[output_field] = val

        # Add any scalar fields from the LAST row that aren't covered by rules
        # (e.g. nguoi_ky, don_vi, etc. — static fields the Word template needs)
        if data_rows:
            last_row = data_rows[-1]
            rule_outputs = {r["output_field"] for r in rules}
            for k, v in last_row.items():
                if k not in summary_record and k not in rule_outputs:
                    if not isinstance(v, dict):
                        summary_record[k] = v

        # 7.25. Force a docxtpl-safe master payload shape from schema_definition.
        # Arrays must always exist as [], and top-level static fields stay flat.
        summary_record = _normalize_master_payload(template.schema_definition or {}, summary_record)
        normalized_top_level = _normalize_master_payload(template.schema_definition or {}, aggregated_data)
        for key, value in normalized_top_level.items():
            if key not in aggregated_data or aggregated_data.get(key) is None:
                aggregated_data[key] = value

        aggregated_data["records"] = [summary_record] if summary_record else []

        # Keep raw source rows for Excel detail sheet & debugging
        aggregated_data["_source_records"] = data_rows

        # 7.5. Include flattened view (json_normalize result) for easy export
        try:
            flat_df = pd.json_normalize(data_rows, sep="_")
            aggregated_data["_flat_records"] = flat_df.to_dict(orient="records")
        except Exception:
            aggregated_data["_flat_records"] = data_rows

        # 8. Add metadata & metrics
        aggregated_data["_metadata"] = {
            "total_jobs": len(jobs),
            "total_data_rows": len(data_rows),
            "generated_at": datetime.utcnow().isoformat(),
            "template_name": template.name,
            "template_version": template.version,
        }
        aggregated_data["metrics"] = {
            "total_records": len(data_rows),
            "total_jobs": len(jobs),
            "rules_applied": len(rules),
        }

        # Sanitize: replace NaN/Inf (not valid in JSON/JSONB) with None
        aggregated_data = _sanitize_for_json(aggregated_data)

        # 9. Create report record
        report = AggregationReport(
            tenant_id=tenant_id,
            template_id=template_id,
            name=report_name,
            description=description,
            job_ids=[str(j.id) for j in jobs],
            aggregated_data=aggregated_data,
            total_jobs=len(job_ids),
            approved_jobs=len(jobs),
            created_by=user_id,
        )
        self.db.add(report)
        self.db.commit()
        self.db.refresh(report)

        logger.info(
            f"Created aggregation report '{report_name}' (id={report.id}): "
            f"{len(jobs)} jobs, {len(rules)} rules applied"
        )

        return report

    def get_report(self, report_id: str, tenant_id: str) -> AggregationReport:
        """Get a report by ID."""
        report = (
            self.db.query(AggregationReport)
            .filter(
                AggregationReport.id == report_id,
                AggregationReport.tenant_id == tenant_id,
            )
            .first()
        )
        if not report:
            raise ProcessingError(message=f"Report {report_id} not found")
        return report

    def list_reports(
        self,
        tenant_id: str,
        page: int = 1,
        per_page: int = 20,
        template_id: str = None,
    ) -> tuple[list[AggregationReport], int]:
        """List reports for a tenant."""
        query = self.db.query(AggregationReport).filter(
            AggregationReport.tenant_id == tenant_id,
        )
        if template_id:
            query = query.filter(AggregationReport.template_id == template_id)

        total = query.count()
        items = (
            query.order_by(AggregationReport.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )
        return items, total

    def delete_report(self, report_id: str, tenant_id: str) -> None:
        """Delete an aggregation report by ID."""
        report = self.get_report(report_id, tenant_id)
        self.db.delete(report)
        self.db.commit()


# ──────────────────────────────────────────────
# Export Service
# ──────────────────────────────────────────────

class ExportService:
    """Export aggregated data to various formats."""

    @staticmethod
    def to_excel(report: AggregationReport, jobs: list[ExtractionJob] = None) -> io.BytesIO:
        """Export report to Excel (.xlsx).

        Sheet 1: Aggregated summary
        Sheet 2: Per-job detail (if jobs provided)
        """
        import pandas as pd

        buffer = io.BytesIO()

        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            # Sheet 1: Summary (aggregated result — the "Cục Cao")
            agg_data = report.aggregated_data or {}
            _INTERNAL = {"records", "_source_records", "_flat_records", "_metadata", "metrics"}
            summary_rows = []
            for key, value in agg_data.items():
                if key in _INTERNAL or key.startswith("_"):
                    continue
                if isinstance(value, list):
                    summary_rows.append({"Trường": key, "Giá trị": f"[{len(value)} phần tử]"})
                elif isinstance(value, dict):
                    summary_rows.append({"Trường": key, "Giá trị": str(value)})
                else:
                    summary_rows.append({"Trường": key, "Giá trị": value})

            df_summary = pd.DataFrame(summary_rows)
            df_summary.to_excel(writer, sheet_name="Tổng hợp", index=False)

            # Sheet 2: Source records (raw data from each day/document)
            source_records = agg_data.get("_source_records", [])
            if source_records:
                try:
                    flat_src = pd.json_normalize(source_records, sep="_")
                    flat_src.to_excel(writer, sheet_name="Tài liệu gốc", index=False)
                except Exception:
                    pd.DataFrame(source_records).to_excel(writer, sheet_name="Tài liệu gốc", index=False)

            # Sheet 3: Detail (per-job from DB)
            if jobs:
                detail_rows = []
                for job in jobs:
                    data = job.reviewed_data or job.extracted_data or {}
                    row = {"job_id": str(job.id), "document_id": str(job.document_id)}
                    for k, v in data.items():
                        if isinstance(v, (list, dict)):
                            row[k] = str(v)
                        else:
                            row[k] = v
                    detail_rows.append(row)

                df_detail = pd.DataFrame(detail_rows)
                df_detail.to_excel(writer, sheet_name="Detail", index=False)

            # Sheet 3: Metadata
            metadata = agg_data.get("_metadata", {})
            df_meta = pd.DataFrame([metadata])
            df_meta.to_excel(writer, sheet_name="Metadata", index=False)

        buffer.seek(0)
        return buffer

    @staticmethod
    def to_csv(report: AggregationReport) -> io.BytesIO:
        """Export aggregated data as CSV."""
        import pandas as pd

        agg_data = report.aggregated_data or {}
        rows = []
        for key, value in agg_data.items():
            if key == "_metadata":
                continue
            rows.append({"Field": key, "Value": value})

        df = pd.DataFrame(rows)
        buffer = io.BytesIO()
        df.to_csv(buffer, index=False, encoding="utf-8")
        buffer.seek(0)
        return buffer
