"""Core extraction service for Engine 2.

Handles: schema building, LLM extraction (3 modes), template CRUD, job management.

Extraction Modes:
  standard — Docling (GPU) → Gemini Flash (text)
  vision   — Bypass parser → Gemini Pro (native PDF vision)
  fast     — pdfplumber (CPU) → Gemini Flash (text)
"""

import io
import json
import logging
import time
import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ProcessingError
from app.models.document import Document
from app.models.extraction import (
    AggregationReport,
    ExtractionJob,
    ExtractionJobStatus,
    ExtractionTemplate,
)
from app.services.document_parser import ParseResult, get_parser

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Schema Builder
# ──────────────────────────────────────────────

class SchemaBuilder:
    """Convert template schema_definition → OpenAI-compatible JSON Schema."""

    TYPE_MAP = {
        "string": "string",
        "number": "number",
        "boolean": "boolean",
        "array": "array",
        "object": "object",
    }

    @classmethod
    def build_json_schema(cls, schema_definition: dict) -> dict:
        """Build a JSON Schema from our internal schema_definition format.

        Automatically adds _confidence and _source meta-fields for each field.

        Args:
            schema_definition: Internal format {"fields": [...]}

        Returns:
            OpenAI-compatible JSON Schema dict
        """
        properties = {}
        required = []

        for field_def in schema_definition.get("fields", []):
            name = field_def["name"]
            field_type = field_def.get("type", "string")
            description = field_def.get("description", "")

            # Main field
            prop = cls._build_property(field_def)
            properties[name] = prop
            required.append(name)

            # Confidence meta-field
            conf_key = f"_{name}_confidence"
            properties[conf_key] = {
                "type": "number",
                "description": f"Confidence score (0.0-1.0) for '{name}'",
            }
            required.append(conf_key)

            # Source reference meta-field
            src_key = f"_{name}_source"
            properties[src_key] = {
                "type": "object",
                "properties": {
                    "page": {"type": "integer", "description": "Page number (1-indexed)"},
                    "quote": {"type": "string", "description": "Exact quote from document"},
                },
                "required": ["page", "quote"],
                "additionalProperties": False,
            }
            required.append(src_key)

        return {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }

    @classmethod
    def _build_property(cls, field_def: dict) -> dict:
        """Build a single JSON Schema property from a field definition."""
        field_type = field_def.get("type", "string")
        description = field_def.get("description", "")

        if field_type == "array":
            items_def = field_def.get("items", {})
            if items_def.get("type") == "object":
                item_schema = cls._build_object_schema(items_def)
            else:
                item_schema = {"type": cls.TYPE_MAP.get(items_def.get("type", "string"), "string")}

            return {
                "type": "array",
                "description": description,
                "items": item_schema,
            }

        elif field_type == "object":
            obj_schema = cls._build_object_schema(field_def)
            obj_schema["description"] = description
            return obj_schema

        else:
            prop: dict[str, Any] = {
                "type": cls.TYPE_MAP.get(field_type, "string"),
            }
            if description:
                prop["description"] = description
            return prop

    @classmethod
    def _build_object_schema(cls, obj_def: dict) -> dict:
        """Build JSON Schema for a nested object."""
        properties = {}
        required = []

        for sub_field in obj_def.get("fields", []):
            sub_name = sub_field["name"]
            properties[sub_name] = cls._build_property(sub_field)
            if sub_field.get("required", True):
                required.append(sub_name)

        return {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }


# ──────────────────────────────────────────────
# LLM Extractors (Gemini-based)
# ──────────────────────────────────────────────

EXTRACTION_SYSTEM_PROMPT = """You are a precise data extraction assistant.
Extract ONLY the requested fields from the provided document.

For EVERY field in the schema, you MUST also provide:
1. _{field_name}_confidence: a float between 0.0 and 1.0
   - 1.0 = exact match found in text
   - 0.7-0.9 = high confidence, minor interpretation needed
   - 0.4-0.6 = moderate confidence, some ambiguity
   - 0.0-0.3 = low confidence or value not found
2. _{field_name}_source: an object with "page" (integer, 1-indexed) and "quote" (exact text from document)

RULES:
- Extract data EXACTLY as it appears. Do NOT calculate, compute, or infer values.
- For monetary values, preserve original formatting (e.g. "$1,234.56", "1.200.000 VNĐ").
- For tables/arrays, extract ALL rows visible in the document.
- If a field is genuinely not present, set its value to null and confidence to 0.0.
- For source.quote, copy the exact text from the document (up to 200 chars).
- Page numbers in source references correspond to the "--- Page N ---" markers in the document.
- Return ONLY valid JSON matching the schema. No extra text before or after.

CRITICAL — Vietnamese text handling:
- The input text may have encoding corruption (mojibake) from non-Unicode PDF fonts.
  Common patterns: digits replacing diacritics (e.g. "ch6y"="cháy", "Kh6ng"="Không",
  "DAm b6o"="Đảm bảo", "d6m"="đàm/đảm", "phong ch6y"="phòng cháy").
- You MUST output ALL text values in CORRECT Vietnamese Unicode (NFC), with proper
  diacritics (ă, â, ê, ô, ơ, ư, đ, etc.) even if the input text is garbled.
- Use context and your knowledge of Vietnamese language to reconstruct the correct text.
- If you cannot determine the correct Vietnamese text, output what you can read."""


def _parse_llm_response(raw_text: str) -> dict:
    """Parse LLM response text into JSON, stripping markdown fences if present.

    Handles truncated responses (max_output_tokens hit) by attempting to
    auto-close the JSON object before raising an error.
    """
    text = raw_text.strip()
    # Strip ```json ... ``` wrapping
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Attempt to recover truncated JSON by closing open structures
        recovered = _try_recover_truncated_json(text)
        if recovered is not None:
            logger.warning("LLM response was truncated — recovered partial JSON (some fields may be missing)")
            return recovered
        raise ProcessingError(
            message="LLM returned invalid JSON (truncated output — consider increasing EXTRACTION_MAX_TOKENS)",
            reason="json_parse_error",
        )


def _try_recover_truncated_json(text: str) -> dict | None:
    """Try to salvage a truncated JSON object by closing open brackets/strings."""
    import re as _re
    # Walk the text char by char and track depth to find the last complete field
    # Simple approach: strip to last complete key-value pair before truncation
    # by progressively trimming from the end until json.loads succeeds
    t = text.rstrip()
    # Remove trailing incomplete value / key
    # Strategy: truncate at last comma or closing brace
    for _ in range(500):  # max 500 trims
        try:
            return json.loads(t + "}" * t.count("{") - t.count("}"))
        except Exception:
            pass
        # Remove last character and retry
        t = t.rstrip(",\n\r \t")
        # Find last safe cut point (comma after a complete value)
        last_comma = t.rfind(",")
        if last_comma < 2:
            break
        t = t[:last_comma]
        try:
            # Try closing the object
            opens = t.count("{") - t.count("}")
            candidate = t + "}" * max(opens, 1)
            result = json.loads(candidate)
            if isinstance(result, dict) and result:
                return result
        except Exception:
            continue
    return None


def _separate_extraction_result(data: dict) -> dict:
    """Separate raw LLM output into extracted_data, confidence_scores, source_references."""
    extracted_data = {}
    confidence_scores = {}
    source_references = {}

    for key, value in data.items():
        if key.startswith("_") and key.endswith("_confidence"):
            field_name = key[1:-11]  # strip _ prefix and _confidence suffix
            confidence_scores[field_name] = value
        elif key.startswith("_") and key.endswith("_source"):
            field_name = key[1:-7]  # strip _ prefix and _source suffix
            source_references[field_name] = value
        else:
            extracted_data[key] = value

    return {
        "extracted_data": extracted_data,
        "confidence_scores": confidence_scores,
        "source_references": source_references,
    }


class GeminiFlashExtractor:
    """Text-based extraction using Gemini 1.5 Flash via google-genai SDK.

    Used by: standard mode (after Docling parse) and fast mode (after pdfplumber parse).
    """

    def extract(
        self,
        markdown_text: str,
        json_schema: dict,
    ) -> dict:
        """Call Gemini Flash with text content.

        Args:
            markdown_text: Document content as Markdown text
            json_schema: JSON Schema describing expected output

        Returns:
            Dict with: extracted_data, confidence_scores, source_references,
                       tokens_used, model, processing_time_ms
        """
        from google import genai
        from google.genai import types

        start_time = time.time()

        client = genai.Client(api_key=settings.GEMINI_API_KEY)

        schema_instruction = json.dumps(json_schema, indent=2, ensure_ascii=False)
        user_content = (
            f"=== DOCUMENT START ===\n\n{markdown_text}\n\n=== DOCUMENT END ===\n\n"
            f"Extract all fields according to this JSON schema:\n```json\n{schema_instruction}\n```\n\n"
            f"Return ONLY a JSON object matching the schema."
        )

        try:
            response = client.models.generate_content(
                model=settings.GEMINI_FLASH_MODEL,
                contents=[user_content],
                config=types.GenerateContentConfig(
                    system_instruction=EXTRACTION_SYSTEM_PROMPT,
                    temperature=settings.EXTRACTION_TEMPERATURE,
                    max_output_tokens=settings.EXTRACTION_MAX_TOKENS,
                    response_mime_type="application/json",
                ),
            )
        except Exception as e:
            logger.error(f"Gemini Flash extraction failed: {e}")
            raise ProcessingError(
                message=f"LLM extraction failed: {str(e)}",
                reason="llm_error",
            )

        data = _parse_llm_response(response.text)
        result = _separate_extraction_result(data)

        elapsed_ms = int((time.time() - start_time) * 1000)
        tokens_used = 0
        if response.usage_metadata:
            tokens_used = (
                getattr(response.usage_metadata, "total_token_count", 0)
                or getattr(response.usage_metadata, "candidates_token_count", 0)
            )

        return {
            **result,
            "tokens_used": tokens_used,
            "model": settings.GEMINI_FLASH_MODEL,
            "processing_time_ms": elapsed_ms,
        }


class GeminiProVisionExtractor:
    """Native PDF vision extraction using Gemini 1.5 Pro.

    Used by: vision mode — uploads raw PDF bytes directly to Gemini,
    bypassing any text parser. Best for scanned/blurry/rotated documents.

    Note: Rate limited to ~2 req/min on free tier.
    """

    def extract(
        self,
        file_bytes: bytes,
        filename: str,
        json_schema: dict,
    ) -> dict:
        """Call Gemini Pro with PDF file directly (vision mode).

        Args:
            file_bytes: Raw PDF bytes
            filename: Original filename (for logging)
            json_schema: JSON Schema describing expected output

        Returns:
            Dict with: extracted_data, confidence_scores, source_references,
                       tokens_used, model, processing_time_ms
        """
        from google import genai
        from google.genai import types

        start_time = time.time()

        client = genai.Client(api_key=settings.GEMINI_API_KEY)

        # Upload file via Google File API
        logger.info(f"[Vision] Uploading {filename} to Google File API")
        try:
            uploaded_file = client.files.upload(
                file=io.BytesIO(file_bytes),
                config=types.UploadFileConfig(
                    display_name=filename,
                    mime_type="application/pdf",
                ),
            )
        except Exception as e:
            logger.error(f"[Vision] File upload failed: {e}")
            raise ProcessingError(
                message=f"Vision mode file upload failed: {str(e)}",
                reason="file_upload_error",
            )

        schema_instruction = json.dumps(json_schema, indent=2, ensure_ascii=False)
        user_content = (
            f"Analyze this PDF document and extract all fields according to this JSON schema:\n"
            f"```json\n{schema_instruction}\n```\n\n"
            f"Return ONLY a JSON object matching the schema."
        )

        try:
            response = client.models.generate_content(
                model=settings.GEMINI_PRO_MODEL,
                contents=[
                    types.Content(
                        parts=[
                            types.Part.from_uri(
                                file_uri=uploaded_file.uri,
                                mime_type="application/pdf",
                            ),
                            types.Part.from_text(text=user_content),
                        ],
                    ),
                ],
                config=types.GenerateContentConfig(
                    system_instruction=EXTRACTION_SYSTEM_PROMPT,
                    temperature=settings.EXTRACTION_TEMPERATURE,
                    max_output_tokens=settings.EXTRACTION_MAX_TOKENS,
                    response_mime_type="application/json",
                ),
            )
        except Exception as e:
            logger.error(f"[Vision] Gemini Pro extraction failed: {e}")
            raise ProcessingError(
                message=f"Vision extraction failed: {str(e)}",
                reason="llm_error",
            )
        finally:
            # Clean up uploaded file
            try:
                client.files.delete(name=uploaded_file.name)
                logger.debug(f"[Vision] Cleaned up uploaded file {uploaded_file.name}")
            except Exception:
                pass

        data = _parse_llm_response(response.text)
        result = _separate_extraction_result(data)

        elapsed_ms = int((time.time() - start_time) * 1000)
        tokens_used = 0
        if response.usage_metadata:
            tokens_used = (
                getattr(response.usage_metadata, "total_token_count", 0)
                or getattr(response.usage_metadata, "candidates_token_count", 0)
            )

        return {
            **result,
            "tokens_used": tokens_used,
            "model": settings.GEMINI_PRO_MODEL,
            "processing_time_ms": elapsed_ms,
        }


# ──────────────────────────────────────────────
# Extraction Service (orchestrator)
# ──────────────────────────────────────────────

class ExtractionService:
    """High-level service orchestrating template CRUD and extraction logic."""

    def __init__(self, db: Session):
        self.db = db

    # ── Template CRUD ─────────────────────────

    def create_template(
        self,
        tenant_id: str,
        user_id: str,
        name: str,
        schema_definition: dict,
        description: str = None,
        aggregation_rules: dict = None,
        word_template_s3_key: str = None,
    ) -> ExtractionTemplate:
        """Create a new extraction template."""
        template = ExtractionTemplate(
            tenant_id=tenant_id,
            name=name,
            description=description,
            schema_definition=schema_definition,
            aggregation_rules=aggregation_rules or {},
            word_template_s3_key=word_template_s3_key,
            created_by=user_id,
        )
        self.db.add(template)
        self.db.commit()
        self.db.refresh(template)
        logger.info(f"Created template '{name}' (id={template.id}) for tenant {tenant_id}")
        return template

    def get_template(self, template_id: str, tenant_id: str) -> ExtractionTemplate:
        """Get template by ID within tenant scope."""
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
        return template

    def list_templates(
        self,
        tenant_id: str,
        page: int = 1,
        per_page: int = 20,
        is_active: bool = True,
    ) -> tuple[list[ExtractionTemplate], int]:
        """List templates for a tenant."""
        query = self.db.query(ExtractionTemplate).filter(
            ExtractionTemplate.tenant_id == tenant_id,
            ExtractionTemplate.is_active == is_active,
        )
        total = query.count()
        items = (
            query.order_by(ExtractionTemplate.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )
        return items, total

    def update_template(
        self,
        template_id: str,
        tenant_id: str,
        **kwargs,
    ) -> ExtractionTemplate:
        """Update a template. If schema_definition changes, bump version."""
        template = self.get_template(template_id, tenant_id)

        if "schema_definition" in kwargs and kwargs["schema_definition"] is not None:
            template.version += 1

        for key, value in kwargs.items():
            if value is not None and hasattr(template, key):
                setattr(template, key, value)

        template.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(template)
        return template

    def delete_template(self, template_id: str, tenant_id: str) -> None:
        """Soft-delete a template (set is_active=False)."""
        template = self.get_template(template_id, tenant_id)
        template.is_active = False
        template.updated_at = datetime.utcnow()
        self.db.commit()

    # ── Job CRUD ──────────────────────────────

    def create_job(
        self,
        tenant_id: str,
        template_id: str,
        document_id: str,
        user_id: str,
        batch_id: str = None,
        mode: str = "standard",
    ) -> ExtractionJob:
        """Create a new extraction job."""
        # Map mode to parser for metadata
        parser_map = {"standard": "docling", "fast": "pdfplumber", "vision": "none"}
        job = ExtractionJob(
            tenant_id=tenant_id,
            template_id=template_id,
            document_id=document_id,
            batch_id=batch_id,
            extraction_mode=mode,
            parser_used=parser_map.get(mode, "pdfplumber"),
            created_by=user_id,
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def get_job(self, job_id: str, tenant_id: str) -> ExtractionJob:
        """Get job by ID within tenant scope."""
        job = (
            self.db.query(ExtractionJob)
            .filter(
                ExtractionJob.id == job_id,
                ExtractionJob.tenant_id == tenant_id,
            )
            .first()
        )
        if not job:
            raise ProcessingError(message=f"Extraction job {job_id} not found")
        return job

    def list_jobs(
        self,
        tenant_id: str,
        page: int = 1,
        per_page: int = 50,
        status: str = None,
        template_id: str = None,
        batch_id: str = None,
    ) -> tuple[list[ExtractionJob], int]:
        """List jobs for a tenant with optional filters."""
        query = self.db.query(ExtractionJob).filter(
            ExtractionJob.tenant_id == tenant_id,
        )
        if status:
            query = query.filter(ExtractionJob.status == status)
        if template_id:
            query = query.filter(ExtractionJob.template_id == template_id)
        if batch_id:
            query = query.filter(ExtractionJob.batch_id == batch_id)

        total = query.count()
        items = (
            query.order_by(ExtractionJob.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )
        return items, total

    def get_batch_status(self, batch_id: str, tenant_id: str) -> dict:
        """Get aggregated status for a batch."""
        jobs = (
            self.db.query(ExtractionJob.status, func.count(ExtractionJob.id))
            .filter(
                ExtractionJob.batch_id == batch_id,
                ExtractionJob.tenant_id == tenant_id,
            )
            .group_by(ExtractionJob.status)
            .all()
        )

        counts = {s: 0 for s in ExtractionJobStatus.ALL}
        total = 0
        for status_val, count in jobs:
            counts[status_val] = count
            total += count

        done = counts["extracted"] + counts["approved"] + counts["rejected"] + counts["failed"]
        progress = (done / total * 100) if total > 0 else 0.0

        return {
            "batch_id": batch_id,
            "total": total,
            "pending": counts["pending"],
            "processing": counts["processing"],
            "extracted": counts["extracted"],
            "approved": counts["approved"],
            "rejected": counts["rejected"],
            "failed": counts["failed"],
            "progress_percent": round(progress, 1),
        }

    def update_job_status(
        self,
        job_id: str,
        status: str,
        **kwargs,
    ) -> None:
        """Update job status and optional fields."""
        job = self.db.query(ExtractionJob).filter(ExtractionJob.id == job_id).first()
        if not job:
            return

        job.status = status
        job.updated_at = datetime.utcnow()

        for key, value in kwargs.items():
            if hasattr(job, key):
                setattr(job, key, value)

        if status in (ExtractionJobStatus.EXTRACTED, ExtractionJobStatus.FAILED):
            job.completed_at = datetime.utcnow()

        self.db.commit()

    # ── Review ────────────────────────────────

    def approve_job(
        self,
        job_id: str,
        tenant_id: str,
        reviewer_id: str,
        reviewed_data: dict = None,
        notes: str = None,
    ) -> ExtractionJob:
        """Approve an extracted job."""
        job = self.get_job(job_id, tenant_id)

        if job.status != ExtractionJobStatus.EXTRACTED:
            raise ProcessingError(
                message=f"Cannot approve job with status '{job.status}'. Must be 'extracted'."
            )

        job.status = ExtractionJobStatus.APPROVED
        job.reviewed_data = reviewed_data or job.extracted_data
        job.reviewed_by = reviewer_id
        job.reviewed_at = datetime.utcnow()
        job.review_notes = notes
        job.updated_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(job)
        return job

    def reject_job(
        self,
        job_id: str,
        tenant_id: str,
        reviewer_id: str,
        notes: str,
    ) -> ExtractionJob:
        """Reject an extracted job."""
        job = self.get_job(job_id, tenant_id)

        if job.status != ExtractionJobStatus.EXTRACTED:
            raise ProcessingError(
                message=f"Cannot reject job with status '{job.status}'. Must be 'extracted'."
            )

        job.status = ExtractionJobStatus.REJECTED
        job.reviewed_by = reviewer_id
        job.reviewed_at = datetime.utcnow()
        job.review_notes = notes
        job.updated_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(job)
        return job

    def retry_job(self, job_id: str, tenant_id: str) -> ExtractionJob:
        """Reset a failed/rejected job back to pending."""
        job = self.get_job(job_id, tenant_id)

        if job.status not in (ExtractionJobStatus.FAILED, ExtractionJobStatus.REJECTED):
            raise ProcessingError(
                message=f"Cannot retry job with status '{job.status}'. Must be 'failed' or 'rejected'."
            )

        job.status = ExtractionJobStatus.PENDING
        job.error_message = None
        job.extracted_data = None
        job.confidence_scores = None
        job.source_references = None
        job.reviewed_data = None
        job.reviewed_by = None
        job.reviewed_at = None
        job.review_notes = None
        job.completed_at = None
        job.retry_count += 1
        job.updated_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(job)
        return job

    # ── Run extraction pipeline ───────────────

    def run_extraction(
        self,
        job_id: str,
    ) -> ExtractionJob:
        """Run the full extraction pipeline for a single job.

        Routes to the correct processing path based on extraction_mode:
          standard → Docling (GPU) → Gemini Flash (text)
          vision   → Bypass parser → Gemini Pro (native PDF vision)
          fast     → pdfplumber (CPU) → Gemini Flash (text)

        Called by Celery worker.

        Args:
            job_id: ExtractionJob UUID

        Returns:
            Updated ExtractionJob
        """
        from app.services.doc_service import s3_client

        job = self.db.query(ExtractionJob).filter(ExtractionJob.id == job_id).first()
        if not job:
            raise ProcessingError(message=f"Job {job_id} not found")

        mode = job.extraction_mode or "standard"

        # 1. Update status
        job.status = ExtractionJobStatus.PROCESSING
        job.updated_at = datetime.utcnow()
        self.db.commit()

        try:
            # 2. Load related objects
            template = (
                self.db.query(ExtractionTemplate)
                .filter(ExtractionTemplate.id == job.template_id)
                .first()
            )
            document = (
                self.db.query(Document)
                .filter(Document.id == job.document_id)
                .first()
            )

            if not template or not document:
                raise ProcessingError(message="Template or document not found")

            # 3. Download PDF from S3
            logger.info(f"Downloading document {document.s3_key} from S3")
            response = s3_client.get_object(
                Bucket=settings.S3_BUCKET_NAME,
                Key=document.s3_key,
            )
            file_bytes = response["Body"].read()

            # 4. Build JSON Schema
            json_schema = SchemaBuilder.build_json_schema(template.schema_definition)

            # 5. Route by extraction mode
            if mode == "vision":
                result = self._run_vision_mode(file_bytes, document.file_name, json_schema)
            elif mode == "fast":
                result = self._run_text_mode(file_bytes, document.file_name, json_schema, parser_type="pdfplumber")
            else:  # standard
                result = self._run_text_mode(file_bytes, document.file_name, json_schema, parser_type="docling")

            # 5.5. VALIDATION LAYER — "Chốt kiểm dịch"
            # Raw LLM JSON must pass through DataValidator before DB INSERT
            from app.services.data_validator import DataValidator

            validator = DataValidator(template.schema_definition)
            clean_data, validation_report = validator.validate(result["extracted_data"])

            logger.info(
                f"Validation report for job {job_id}: "
                f"{validation_report['valid_fields']}/{validation_report['total_fields']} fields valid, "
                f"{len(validation_report['auto_corrections'])} auto-corrections, "
                f"{len(validation_report['missing_fields'])} missing"
            )

            # 6. Store VALIDATED results (clean data, not raw LLM output)
            job.extracted_data = clean_data
            job.confidence_scores = result["confidence_scores"]
            job.source_references = result["source_references"]
            # Store validation report alongside confidence scores
            if job.confidence_scores is None:
                job.confidence_scores = {}
            job.confidence_scores["_validation_report"] = validation_report
            job.llm_tokens_used = result["tokens_used"]
            job.llm_model = result["model"]
            job.processing_time_ms = result["processing_time_ms"]
            job.status = ExtractionJobStatus.EXTRACTED
            job.completed_at = datetime.utcnow()
            job.updated_at = datetime.utcnow()

            self.db.commit()
            self.db.refresh(job)

            logger.info(
                f"Extraction complete for job {job_id} (mode={mode}): "
                f"{len(clean_data)} fields, "
                f"{result['tokens_used']} tokens, "
                f"{result['processing_time_ms']}ms, "
                f"completeness={validation_report['completeness_pct']}%"
            )

            return job

        except Exception as e:
            logger.error(f"Extraction failed for job {job_id} (mode={mode}): {e}")
            job.status = ExtractionJobStatus.FAILED
            job.error_message = str(e)[:2000]
            job.completed_at = datetime.utcnow()
            job.updated_at = datetime.utcnow()
            self.db.commit()
            raise

    def _run_text_mode(
        self,
        file_bytes: bytes,
        filename: str,
        json_schema: dict,
        parser_type: str,
    ) -> dict:
        """Standard / Fast path: Parse PDF → Markdown → Gemini Flash.

        Auto-fallback: If parsed text has Vietnamese mojibake (font encoding
        issues common in Vietnamese government PDFs), automatically switches
        to vision mode (Gemini reads the PDF directly).

        Args:
            file_bytes: Raw PDF bytes
            filename: Original filename
            json_schema: JSON Schema for extraction
            parser_type: "docling" for standard, "pdfplumber" for fast
        """
        parser = get_parser(parser_type)
        logger.info(f"Parsing document with {parser.__class__.__name__} (text mode)")
        parse_result: ParseResult = parser.parse(file_bytes, filename)

        # ── Mojibake auto-fallback ────────────────────────────
        mojibake_detected = parse_result.metadata.get("mojibake_detected", False)
        if mojibake_detected:
            mojibake_conf = parse_result.metadata.get("mojibake_confidence", 0)
            logger.warning(
                f"Vietnamese mojibake detected in '{filename}' "
                f"(confidence={mojibake_conf:.2f}). "
                f"Auto-falling back to VISION mode for accurate extraction."
            )
            try:
                return self._run_vision_mode(file_bytes, filename, json_schema)
            except Exception as vision_err:
                logger.warning(
                    f"Vision mode fallback failed: {vision_err}. "
                    f"Continuing with corrupted text (best effort)."
                )
                # Fall through to text mode as last resort

        logger.info(f"Calling Gemini Flash for text extraction ({settings.GEMINI_FLASH_MODEL})")
        extractor = GeminiFlashExtractor()
        return extractor.extract(
            markdown_text=parse_result.markdown,
            json_schema=json_schema,
        )

    def _run_vision_mode(
        self,
        file_bytes: bytes,
        filename: str,
        json_schema: dict,
    ) -> dict:
        """Vision path: Upload raw PDF → Gemini Pro (native vision).

        No text parser involved. Best for scanned/blurry documents.
        """
        logger.info(f"Calling Gemini Pro Vision for extraction ({settings.GEMINI_PRO_MODEL})")
        extractor = GeminiProVisionExtractor()
        return extractor.extract(
            file_bytes=file_bytes,
            filename=filename,
            json_schema=json_schema,
        )
