from __future__ import annotations

from typing import Any

from app.business.template_loader import DocumentTemplate, get_default_template
from app.schemas.hybrid_extraction_schema import BlockExtractionOutput
from app.services.block_extraction_pipeline import BlockExtractionPipeline


class BlockBusinessWorkflow:
    """Thin orchestrator: runs block pipeline (which now includes business rules internally)."""

    def __init__(
        self,
        model: str | None = None,
        temperature: float = 0.0,
        template: DocumentTemplate | None = None,
    ) -> None:
        self.tpl = template or get_default_template()
        self.pipeline = BlockExtractionPipeline(
            model=model, temperature=temperature, template=self.tpl,
        )

    def run_from_bytes(self, pdf_bytes: bytes, filename: str) -> dict[str, Any]:
        result = self.pipeline.run_from_bytes(pdf_bytes, filename)

        return {
            "status": result.status,
            "attempts": result.attempts,
            "errors": result.errors,
            "output": result.output,
            "business_data": result.business_data or {},
            "metrics": result.metrics,
        }

    def build_final_payload(self, filename: str, workflow_result: dict[str, Any]) -> dict[str, Any]:
        output = workflow_result.get("output")
        bang_thong_ke = [item.dict() for item in output.bang_thong_ke] if output else []
        narrative = output.phan_I_va_II_chi_tiet_nghiep_vu.dict() if output else {}

        # Fallback: if LLM missed tong_so_vu_cnch, derive it from the statistical table
        if not narrative.get("tong_so_vu_cnch"):
            import re, unicodedata
            cnch_patterns = tuple(self.tpl.cnch_fallback_patterns)
            for row in bang_thong_ke:
                nd = row.get("noi_dung", "")
                nd_norm = unicodedata.normalize("NFD", nd.upper())
                nd_norm = re.sub(r"[^\w]", "", "".join(
                    ch for ch in nd_norm if unicodedata.category(ch) != "Mn"
                ))
                if any(pat in nd_norm for pat in cnch_patterns) and row.get("ket_qua", 0):
                    narrative["tong_so_vu_cnch"] = row["ket_qua"]
                    break

        return {
            "file": filename,
            "mode": "block",
            "template": self.tpl.template_id,
            "status": workflow_result.get("status"),
            "attempts": workflow_result.get("attempts"),
            "errors": workflow_result.get("errors"),
            "metrics": workflow_result.get("metrics"),
            "business_data": workflow_result.get("business_data"),
            "header": output.header.dict() if output else {},
            "narrative": narrative,
            "bang_thong_ke": bang_thong_ke,
        }
