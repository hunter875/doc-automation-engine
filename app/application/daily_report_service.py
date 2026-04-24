"""Daily report generation from existing extraction jobs."""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, time, timedelta
from typing import Any

from botocore.exceptions import ClientError
from sqlalchemy.orm import Session

from app.application.doc_service import s3_client
from app.application.template_service import TemplateManager
from app.core.config import settings
from app.core.exceptions import ProcessingError
from app.domain.models.extraction_job import AggregationReport, ExtractionJob, ExtractionJobStatus

logger = logging.getLogger(__name__)


WORD_STT_MAP: dict[int, str] = {
    2: "stt_02_tong_chay",
    3: "stt_03_chay_chet",
    4: "stt_04_chay_thuong",
    5: "stt_05_chay_cuu_nguoi",
    6: "stt_06_chay_thiet_hai",
    7: "stt_07_chay_cuu_tai_san",
    8: "stt_08_tong_no",
    9: "stt_09_no_chet",
    10: "stt_10_no_thuong",
    11: "stt_11_no_cuu_nguoi",
    12: "stt_12_no_thiet_hai",
    13: "stt_13_no_cuu_tai_san",
    14: "stt_14_tong_cnch",
    15: "stt_15_cnch_cuu_nguoi",
    16: "stt_16_cnch_truc_tiep",
    17: "stt_17_cnch_tu_thoat",
    18: "stt_18_cnch_thi_the",
    19: "stt_19_cnch_cuu_tai_san",
    22: "stt_22_tt_mxh_tong",
    23: "stt_23_tt_mxh_tin_bai",
    24: "stt_24_tt_mxh_hinh_anh",
    25: "stt_25_tt_mxh_video",
    27: "stt_27_tt_so_cuoc",
    28: "stt_28_tt_so_nguoi",
    29: "stt_29_tt_to_roi",
    31: "stt_31_kiem_tra_tong",
    32: "stt_32_kiem_tra_dinh_ky",
    33: "stt_33_kiem_tra_dot_xuat",
    34: "stt_34_vi_pham_phat_hien",
    35: "stt_35_xu_phat_tong",
    36: "stt_36_xu_phat_canh_cao",
    37: "stt_37_xu_phat_tam_dinh_chi",
    38: "stt_38_xu_phat_dinh_chi",
    39: "stt_39_xu_phat_tien_mat",
    40: "stt_40_xu_phat_tien",
    43: "stt_43_pa_co_so_duyet",
    44: "stt_44_pa_co_so_thuc_tap",
    46: "stt_46_pa_giao_thong_duyet",
    47: "stt_47_pa_giao_thong_thuc_tap",
    49: "stt_49_pa_cong_an_duyet",
    50: "stt_50_pa_cong_an_thuc_tap",
    52: "stt_52_pa_cnch_ca_duyet",
    53: "stt_53_pa_cnch_ca_thuc_tap",
    55: "stt_55_hl_tong_cbcs",
    56: "stt_56_hl_chi_huy_phong",
    57: "stt_57_hl_chi_huy_doi",
    58: "stt_58_hl_can_bo_tieu_doi",
    59: "stt_59_hl_chien_sy",
    60: "stt_60_hl_lai_xe",
    61: "stt_61_hl_lai_tau",
}


def _to_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        try:
            return int(value)
        except Exception:
            return default
    text = str(value).strip()
    if not text:
        return default
    cleaned = text.replace(".", "").replace(",", "")
    try:
        return int(cleaned)
    except Exception:
        return default


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _to_uuid_or_none(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except Exception:
        return None


def _normalize_operational_payload(extracted_data: Any) -> dict[str, Any]:
    payload = _as_dict(extracted_data)
    if not payload:
        return {}

    nested = _as_dict(payload.get("data"))
    if nested and any(
        key in nested
        for key in (
            "bang_thong_ke",
            "danh_sach_cnch",
            "danh_sach_phuong_tien_hu_hong",
            "danh_sach_cong_tac_khac",
        )
    ):
        return nested

    return payload


def _merge_bang_thong_ke_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    merged_by_key: dict[str, dict[str, Any]] = {}
    stt_totals: dict[str, int] = {}

    for row in rows:
        item = _as_dict(row)
        if not item:
            continue

        stt = _to_text(item.get("stt"))
        noi_dung = _to_text(item.get("noi_dung"))
        ket_qua = _to_int(item.get("ket_qua"), 0)

        if stt:
            key = f"stt:{stt}"
        elif noi_dung:
            key = f"noi_dung:{noi_dung.lower()}"
        else:
            continue

        current = merged_by_key.get(key)
        if current is None:
            current = {"stt": stt, "noi_dung": noi_dung, "ket_qua": 0}
            merged_by_key[key] = current

        current["stt"] = current.get("stt") or stt
        current["noi_dung"] = current.get("noi_dung") or noi_dung
        current["ket_qua"] = _to_int(current.get("ket_qua"), 0) + ket_qua

        if stt:
            stt_totals[stt] = stt_totals.get(stt, 0) + ket_qua

    merged_rows = list(merged_by_key.values())

    def _sort_key(item: dict[str, Any]) -> tuple[int, str]:
        stt = _to_text(item.get("stt"))
        if stt.isdigit():
            return (0, f"{int(stt):04d}")
        return (1, _to_text(item.get("noi_dung")).lower())

    merged_rows.sort(key=_sort_key)
    return merged_rows, stt_totals


def _merge_unique_dict_items(items: list[dict[str, Any]], fields: list[str]) -> list[dict[str, Any]]:
    seen: set[tuple[str, ...]] = set()
    merged: list[dict[str, Any]] = []

    for raw in items:
        item = _as_dict(raw)
        if not item:
            continue
        signature = tuple(_to_text(item.get(field)).lower() for field in fields)
        if signature in seen:
            continue
        seen.add(signature)
        merged.append(item)

    return merged


def _merge_unique_text_items(items: list[Any]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []

    for raw in items:
        text = _to_text(raw)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        merged.append(text)

    return merged


def _sum_nested_field(payloads: list[dict[str, Any]], nested_key: str, field_name: str) -> int:
    total = 0
    for payload in payloads:
        nested = _as_dict(payload.get(nested_key))
        total += _to_int(nested.get(field_name), 0)
    return total


def build_daily_operational_context(
    jobs: list[ExtractionJob],
    *,
    report_date: date,
    report_name: str,
    report_description: str,
) -> dict[str, Any]:
    payloads: list[dict[str, Any]] = [
        _normalize_operational_payload(job.extracted_data)
        for job in jobs
        if isinstance(job.extracted_data, dict)
    ]

    bang_thong_ke_rows: list[dict[str, Any]] = []
    cnch_rows: list[dict[str, Any]] = []
    vehicle_rows: list[dict[str, Any]] = []
    other_tasks: list[Any] = []

    for payload in payloads:
        bang_thong_ke_rows.extend(_as_list(payload.get("bang_thong_ke")))
        cnch_rows.extend(_as_list(payload.get("danh_sach_cnch")))
        vehicle_rows.extend(_as_list(payload.get("danh_sach_phuong_tien_hu_hong")))
        other_tasks.extend(_as_list(payload.get("danh_sach_cong_tac_khac")))

    merged_bang_thong_ke, stt_totals = _merge_bang_thong_ke_rows(bang_thong_ke_rows)
    merged_cnch = _merge_unique_dict_items(
        cnch_rows,
        fields=["ngay_xay_ra", "thoi_gian", "dia_diem", "noi_dung_tin_bao"],
    )
    merged_vehicles = _merge_unique_dict_items(
        vehicle_rows,
        fields=["bien_so", "tinh_trang"],
    )
    merged_other_tasks = _merge_unique_text_items(other_tasks)

    total_chay = stt_totals.get("2", _sum_nested_field(payloads, "phan_I_va_II_chi_tiet_nghiep_vu", "tong_so_vu_chay"))
    total_no = stt_totals.get("8", _sum_nested_field(payloads, "phan_I_va_II_chi_tiet_nghiep_vu", "tong_so_vu_no"))
    total_cnch = stt_totals.get("14", _sum_nested_field(payloads, "phan_I_va_II_chi_tiet_nghiep_vu", "tong_so_vu_cnch"))

    daily_values: dict[str, Any] = {
        "total_incidents": total_chay + total_no + total_cnch,
        "total_chay_incidents": total_chay,
        "total_no_incidents": total_no,
        "total_cnch_events": total_cnch,
        "total_cnch_listed_events": len(merged_cnch),
        "total_damaged_vehicles": len(merged_vehicles),
        "total_other_tasks": len(merged_other_tasks),
    }

    for stt, value in stt_totals.items():
        if stt.isdigit():
            daily_values[f"stt_{int(stt):02d}"] = value

    for stt_number, field_name in WORD_STT_MAP.items():
        daily_values[field_name] = stt_totals.get(str(stt_number), 0)

    return {
        "report_name": report_name,
        "report_description": report_description,
        "report_date": report_date.isoformat(),
        "generated_at": datetime.utcnow().isoformat(),
        "daily_operational_state": {
            "bang_thong_ke": merged_bang_thong_ke,
            "danh_sach_cnch": merged_cnch,
            "danh_sach_phuong_tien_hu_hong": merged_vehicles,
            "danh_sach_cong_tac_khac": merged_other_tasks,
        },
        "daily_values": daily_values,
        "bang_thong_ke": merged_bang_thong_ke,
        "danh_sach_cnch": merged_cnch,
        "danh_sach_phuong_tien_hu_hong": merged_vehicles,
        "danh_sach_cong_tac_khac": merged_other_tasks,
        **daily_values,
    }


def build_daily_dataset(jobs: list[ExtractionJob]) -> dict[str, Any]:
    """Build a deduplicated dataset summary from extraction jobs.

    Deduplication strategy:
      - For Google Sheet jobs: dedupe by ``source_references.row_hash``
      - For non-sheet jobs: keep every job (dedupe key is ``job.id``)
    """
    selected_jobs: list[ExtractionJob] = []
    seen_keys: set[str] = set()
    duplicates_skipped = 0
    row_status_counts: dict[str, int] = {}

    for job in jobs:
        source_references = job.source_references if isinstance(job.source_references, dict) else {}
        row_hash = str(source_references.get("row_hash") or "").strip()
        if row_hash:
            dedupe_key = f"row_hash:{row_hash}"
        else:
            dedupe_key = f"job_id:{job.id}"

        if dedupe_key in seen_keys:
            duplicates_skipped += 1
            continue

        seen_keys.add(dedupe_key)
        selected_jobs.append(job)

        row_status = str(source_references.get("row_status") or "UNKNOWN").strip().upper()
        row_status_counts[row_status] = row_status_counts.get(row_status, 0) + 1

    partial_rows = row_status_counts.get("PARTIAL", 0)

    return {
        "jobs_total": len(jobs),
        "jobs_selected": len(selected_jobs),
        "duplicates_skipped": duplicates_skipped,
        "partial_rows": partial_rows,
        "row_status_counts": row_status_counts,
        "selected_jobs": selected_jobs,
    }


class DailyReportService:
    """Generate daily report by reusing existing aggregation/export stack."""

    def __init__(self, db: Session):
        self.db = db

    def _load_jobs_for_day(
        self,
        *,
        tenant_id: str,
        template_id: str,
        report_date: date,
        status: str,
    ) -> list[ExtractionJob]:
        start_dt = datetime.combine(report_date, time.min)
        end_dt = start_dt + timedelta(days=1)

        return (
            self.db.query(ExtractionJob)
            .filter(
                ExtractionJob.tenant_id == tenant_id,
                ExtractionJob.template_id == template_id,
                ExtractionJob.status == status,
                ExtractionJob.created_at >= start_dt,
                ExtractionJob.created_at < end_dt,
            )
            .order_by(ExtractionJob.created_at.asc())
            .all()
        )

    def generate_daily_report(
        self,
        *,
        tenant_id: str,
        user_id: str,
        template_id: str,
        report_date: date,
        report_name: str | None = None,
        description: str | None = None,
        status: str = ExtractionJobStatus.APPROVED,
    ) -> dict[str, Any]:
        if status != ExtractionJobStatus.APPROVED:
            raise ProcessingError(
                message="Daily report currently supports status='approved' only"
            )

        jobs = self._load_jobs_for_day(
            tenant_id=tenant_id,
            template_id=template_id,
            report_date=report_date,
            status=status,
        )
        dataset = build_daily_dataset(jobs)

        if dataset["jobs_selected"] == 0:
            return {
                "status": "no_data",
                "report_date": report_date,
                "report_id": None,
                "report_name": report_name or f"Daily report {report_date.isoformat()}",
                "jobs_total": dataset["jobs_total"],
                "jobs_selected": 0,
                "duplicates_skipped": dataset["duplicates_skipped"],
                "partial_rows": dataset["partial_rows"],
                "row_status_counts": dataset["row_status_counts"],
                "output_s3_key": None,
            }

        final_report_name = report_name or f"Daily report {report_date.isoformat()}"
        final_description = description or f"Auto daily report for {report_date.isoformat()}"

        daily_operational_context = build_daily_operational_context(
            dataset["selected_jobs"],
            report_date=report_date,
            report_name=final_report_name,
            report_description=final_description,
        )

        report = AggregationReport(
            tenant_id=tenant_id,
            template_id=template_id,
            name=final_report_name,
            description=final_description,
            job_ids=[job.id for job in dataset["selected_jobs"]],
            aggregated_data=daily_operational_context,
            total_jobs=dataset["jobs_total"],
            approved_jobs=dataset["jobs_selected"],
            created_by=_to_uuid_or_none(user_id),
        )
        self.db.add(report)
        self.db.commit()
        self.db.refresh(report)

        template = TemplateManager(self.db).get_template(template_id, tenant_id)
        if not template.word_template_s3_key:
            raise ProcessingError(
                message="Selected template has no word_template_s3_key; cannot export .docx"
            )

        from app.utils.word_export import render_word_template

        try:
            s3_resp = s3_client.get_object(
                Bucket=settings.S3_BUCKET_NAME,
                Key=template.word_template_s3_key,
            )
            template_bytes = s3_resp["Body"].read()
        except ClientError as exc:
            raise ProcessingError(
                message=(
                    f"Cannot load Word template from storage: key={template.word_template_s3_key}"
                )
            ) from exc

        context = {
            **daily_operational_context,
            "report_name": report.name,
            "report_description": report.description or "",
            "total_jobs": dataset["jobs_total"],
            "approved_jobs": dataset["jobs_selected"],
        }
        rendered_docx = render_word_template(
            template_bytes=template_bytes,
            context_data=context,
        )

        output_key = f"exports/{tenant_id}/daily/{report_date.strftime('%Y%m%d')}/{report.id}.docx"
        s3_client.put_object(
            Bucket=settings.S3_BUCKET_NAME,
            Key=output_key,
            Body=rendered_docx,
            ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

        logger.info(
            "DAILY_REPORT_CREATED | tenant_id=%s template_id=%s date=%s report_id=%s output_key=%s jobs_total=%s jobs_selected=%s duplicates=%s",
            tenant_id,
            template_id,
            report_date.isoformat(),
            report.id,
            output_key,
            dataset["jobs_total"],
            dataset["jobs_selected"],
            dataset["duplicates_skipped"],
        )

        return {
            "status": "created",
            "report_date": report_date,
            "report_id": report.id,
            "report_name": report.name,
            "jobs_total": dataset["jobs_total"],
            "jobs_selected": dataset["jobs_selected"],
            "duplicates_skipped": dataset["duplicates_skipped"],
            "partial_rows": dataset["partial_rows"],
            "row_status_counts": dataset["row_status_counts"],
            "output_s3_key": output_key,
        }
