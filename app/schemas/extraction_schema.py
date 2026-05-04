"""Pydantic schemas for Engine 2: Extraction API."""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# ──────────────────────────────────────────────
# Schema Definition validation helpers
# ──────────────────────────────────────────────

ALLOWED_FIELD_TYPES = {"string", "number", "boolean", "array", "object"}


class FieldDefinition(BaseModel):
    """A single field in a template schema definition.

    When used as `items` inside an array field, `name` is optional
    because it describes the element type, not a named field.
    """

    name: str = Field("", max_length=64)
    type: str = Field(...)
    description: str = Field("", max_length=500)
    required: bool = True
    items: Optional[FieldDefinition] = None  # For type="array"
    fields: Optional[list[FieldDefinition]] = None  # For type="object"

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        # Allow empty name for array items definitions
        if v == "":
            return v
        # Strip whitespace
        v = v.strip()
        # Accept any non-empty string that is a valid identifier
        # (letters, digits, underscores — snake_case preferred but not enforced)
        # Reject only names with spaces or special chars that would break JSON/Python
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", v):
            # Try to auto-fix: replace spaces/hyphens/dots with underscore, lowercase
            fixed = re.sub(r"[^A-Za-z0-9_]", "_", v).strip("_")
            fixed = re.sub(r"_+", "_", fixed)
            if fixed and re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", fixed):
                return fixed
            raise ValueError(
                f"Field name '{v}' contains invalid characters. Use letters, digits, underscores only."
            )
        return v

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in ALLOWED_FIELD_TYPES:
            raise ValueError(f"Field type '{v}' not allowed. Must be one of: {ALLOWED_FIELD_TYPES}")
        return v


class SchemaDefinition(BaseModel):
    """The schema_definition stored in extraction_templates."""

    fields: list[FieldDefinition] = Field(..., min_length=1)

    @field_validator("fields")
    @classmethod
    def validate_unique_names(cls, v: list[FieldDefinition]) -> list[FieldDefinition]:
        # Top-level fields must have names
        for f in v:
            if not f.name:
                raise ValueError("Top-level fields must have a non-empty name")
        names = [f.name for f in v]
        if len(names) != len(set(names)):
            dupes = [n for n in names if names.count(n) > 1]
            raise ValueError(f"Duplicate field names: {set(dupes)}")
        return v


# ──────────────────────────────────────────────
# Aggregation Rules
# ──────────────────────────────────────────────

ALLOWED_AGG_METHODS = {"SUM", "AVG", "MAX", "MIN", "COUNT", "CONCAT", "LAST"}


class AggregationRule(BaseModel):
    """A single aggregation rule."""

    output_field: str = Field(..., min_length=1, max_length=128)
    source_field: str = Field(..., min_length=1, max_length=128)
    method: str = Field(...)
    label: str = Field("", max_length=255)
    round_digits: Optional[int] = None

    @field_validator("method")
    @classmethod
    def validate_method(cls, v: str) -> str:
        v = v.upper()
        if v not in ALLOWED_AGG_METHODS:
            raise ValueError(f"Aggregation method '{v}' not allowed. Must be one of: {ALLOWED_AGG_METHODS}")
        return v


class AggregationRules(BaseModel):
    """aggregation_rules stored in extraction_templates."""

    rules: list[AggregationRule] = Field(default_factory=list)
    group_by: Optional[str] = None
    sort_by: Optional[str] = None


class GoogleSheetWorksheetConfig(BaseModel):
    """Configuration for a single worksheet within a Google Sheet."""

    worksheet: str = Field(..., min_length=1, max_length=200, description="Worksheet name within the Google Sheet.")
    schema_path: str = Field(..., min_length=1, max_length=500, description="Path to YAML schema file for mapping sheet columns.")
    range: Optional[str] = Field(None, max_length=200, description="A1 notation range (e.g., A1:ZZZ). Defaults to A1:ZZZ if omitted.")
    mode: Optional[str] = Field(None, description="Ingestion mode: 'row' (default, one job per data row) or 'single_document' (one job for entire worksheet).")
    header_row: int = Field(0, description="0-indexed row that contains column headers. For KV30 BC NGÀY sheets, this is row 0 (the merged group-header row). For sheets without a header row, set to -1 to use schema field names as column names.")
    data_start_row: int = Field(2, description="0-indexed row where data starts. For KV30 BC NGÀY sheets, data starts at row 2 (rows 0-1 are headers). For sheets with 1 header row, data starts at row 1.")


# ──────────────────────────────────────────────
# Template Schemas
# ──────────────────────────────────────────────

class TemplateCreate(BaseModel):
    """Request: create a new extraction template."""

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    schema_definition: SchemaDefinition
    aggregation_rules: Optional[AggregationRules] = None
    word_template_s3_key: Optional[str] = None
    filename_pattern: Optional[str] = Field(
        None, max_length=500,
        description="Regex pattern to auto-match uploaded filenames to this template.",
    )
    extraction_mode: str = Field(
        "block",
        description="Pipeline to use: block (deterministic+enrichment).",
    )
    google_sheet_id: Optional[str] = Field(
        None, max_length=500,
        description="Google Sheet ID or URL for automated ingestion.",
    )
    google_sheet_worksheet: Optional[str] = Field(
        None, max_length=100,
        description="Worksheet name within the Google Sheet.",
    )
    google_sheet_range: Optional[str] = Field(
        None, max_length=50,
        description="A1 notation range (e.g., A1:ZZZ, Sheet1!A1:C100).",
    )
    google_sheet_schema_path: Optional[str] = Field(
        None, max_length=500,
        description="Path to YAML schema file for mapping sheet columns.",
    )
    google_sheet_configs: Optional[list[GoogleSheetWorksheetConfig]] = Field(
        None,
        description="List of worksheet configurations for multi-worksheet ingestion from a single Google Sheet. If provided, overrides single-field configs (google_sheet_worksheet, google_sheet_schema_path, google_sheet_range).",
    )
    aggregation_group: Optional[str] = Field(
        None, max_length=100,
        description="Aggregation group name for cross-template daily reports.",
    )

    @field_validator("extraction_mode")
    @classmethod
    def validate_extraction_mode(cls, v: str) -> str:
        if v not in ("block",):
            raise ValueError("extraction_mode must be: block")
        return v

    @field_validator("filename_pattern")
    @classmethod
    def validate_filename_pattern(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v.strip() == "":
            return None
        import re as _re
        try:
            _re.compile(v)
        except _re.error as e:
            raise ValueError(f"Invalid regex pattern: {e}")
        return v.strip()


class TemplateUpdate(BaseModel):
    """Request: update an extraction template."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    schema_definition: Optional[SchemaDefinition] = None
    aggregation_rules: Optional[AggregationRules] = None
    is_active: Optional[bool] = None
    filename_pattern: Optional[str] = Field(
        None, max_length=500,
        description="Regex pattern to auto-match uploaded filenames.",
    )
    extraction_mode: Optional[str] = Field(
        None,
        description="Pipeline to use: block.",
    )
    word_template_s3_key: Optional[str] = Field(
        None, max_length=500,
        description="S3 key of the .docx Word template for export.",
    )
    google_sheet_id: Optional[str] = Field(
        None, max_length=500,
        description="Google Sheet ID or URL for automated ingestion.",
    )
    google_sheet_worksheet: Optional[str] = Field(
        None, max_length=100,
        description="Worksheet name within the Google Sheet.",
    )
    google_sheet_range: Optional[str] = Field(
        None, max_length=50,
        description="A1 notation range (e.g., A1:ZZZ, Sheet1!A1:C100).",
    )
    google_sheet_schema_path: Optional[str] = Field(
        None, max_length=500,
        description="Path to YAML schema file for mapping sheet columns.",
    )
    google_sheet_configs: Optional[list[GoogleSheetWorksheetConfig]] = Field(
        None,
        description="List of worksheet configurations for multi-worksheet ingestion from a single Google Sheet. If provided, overrides single-field configs (google_sheet_worksheet, google_sheet_schema_path, google_sheet_range).",
    )
    aggregation_group: Optional[str] = Field(
        None, max_length=100,
        description="Aggregation group name for cross-template daily reports.",
    )

    @field_validator("extraction_mode")
    @classmethod
    def validate_extraction_mode(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("block",):
            raise ValueError("extraction_mode must be: block")
        return v

    @field_validator("filename_pattern")
    @classmethod
    def validate_filename_pattern(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v.strip() == "":
            return None
        import re as _re
        try:
            _re.compile(v)
        except _re.error as e:
            raise ValueError(f"Invalid regex pattern: {e}")
        return v.strip()


class TemplateResponse(BaseModel):
    """Response: extraction template."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    description: Optional[str]
    schema_definition: dict
    aggregation_rules: Optional[dict]
    word_template_s3_key: Optional[str] = None
    filename_pattern: Optional[str] = None
    extraction_mode: str = "standard"
    version: int
    is_active: bool
    created_by: Optional[uuid.UUID]
    created_at: datetime
    updated_at: Optional[datetime]
    # Google Sheets config (optional)
    google_sheet_id: Optional[str] = None
    google_sheet_worksheet: Optional[str] = None
    google_sheet_range: Optional[str] = None
    google_sheet_schema_path: Optional[str] = None
    google_sheet_configs: Optional[list[dict]] = None
    # Aggregation group
    aggregation_group: Optional[str] = None

    model_config = {"from_attributes": True}


class TemplateListResponse(BaseModel):
    """Response: paginated list of templates."""

    items: list[TemplateResponse]
    total: int
    page: int
    per_page: int


# ──────────────────────────────────────────────
# Job Schemas
# ──────────────────────────────────────────────

# Extraction modes
EXTRACTION_MODES = {"standard", "vision", "block"}


class JobCreate(BaseModel):
    """Request: create a single extraction job."""

    template_id: uuid.UUID
    mode: str = Field("standard", pattern=r"^(standard|vision|block)$")


class JobFromDocumentCreate(BaseModel):
    """Request: create job from existing document (no re-upload)."""

    document_id: uuid.UUID
    template_id: uuid.UUID
    mode: str = Field("standard", pattern=r"^(standard|vision|block)$")


class BatchJobCreate(BaseModel):
    """Request: batch job creation (template_id from form field)."""

    template_id: uuid.UUID
    mode: str = Field("standard", pattern=r"^(standard|vision|block)$")


class JobResponse(BaseModel):
    """Response: extraction job details."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    template_id: uuid.UUID
    document_id: uuid.UUID
    file_name: Optional[str] = None
    display_name: Optional[str] = None
    batch_id: Optional[uuid.UUID]
    extraction_mode: str = "standard"
    status: str
    extracted_data: Optional[dict] = Field(default=None, validation_alias="final_data")
    confidence_scores: Optional[dict]
    source_references: Optional[dict]
    reviewed_data: Optional[dict]
    reviewed_by: Optional[uuid.UUID]
    reviewed_at: Optional[datetime]
    review_notes: Optional[str]
    parser_used: Optional[str]
    llm_model: Optional[str]
    llm_tokens_used: int
    processing_time_ms: Optional[int]
    error_message: Optional[str]
    created_by: Optional[uuid.UUID]
    created_at: datetime
    completed_at: Optional[datetime]

    model_config = {"from_attributes": True, "populate_by_name": True}


class JobSummary(BaseModel):
    """Short job info for batch listing."""

    job_id: uuid.UUID
    file_name: str
    status: str


class BatchCreateResponse(BaseModel):
    """Response: batch creation result."""

    batch_id: uuid.UUID
    total_files: int
    jobs: list[JobSummary]


class JobListResponse(BaseModel):
    """Response: paginated job list."""

    items: list[JobResponse]
    total: int
    page: int
    per_page: int


class BatchStatusResponse(BaseModel):
    """Response: batch progress."""

    batch_id: str
    total: int
    pending: int
    processing: int
    extracted: int
    enriching: int = 0
    ready_for_review: int = 0
    approved: int
    rejected: int
    aggregated: int = 0
    failed: int
    progress_percent: float


# ──────────────────────────────────────────────
# Review Schemas
# ──────────────────────────────────────────────

class ReviewApprove(BaseModel):
    """Request: approve extraction result."""

    reviewed_data: Optional[dict] = None
    notes: Optional[str] = None


class ReviewReject(BaseModel):
    """Request: reject extraction result."""

    notes: str = Field(..., min_length=1, max_length=2000)


# ──────────────────────────────────────────────
# Aggregation Schemas
# ──────────────────────────────────────────────

class AggregateRequest(BaseModel):
    """Request: aggregate multiple approved jobs."""

    template_id: uuid.UUID
    job_ids: list[uuid.UUID] = Field(..., min_length=1)
    report_name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None


class AggregateResponse(BaseModel):
    """Response: aggregation report."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    template_id: uuid.UUID
    name: str
    description: Optional[str]
    aggregated_data: dict
    total_jobs: int
    approved_jobs: int
    status: str
    created_at: datetime
    sources_used: list[dict[str, Any]] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class AggregateListResponse(BaseModel):
    """Response: paginated report list."""

    items: list[AggregateResponse]
    total: int
    page: int
    per_page: int


class DailyReportRequest(BaseModel):
    """Request: generate a daily report from extraction jobs."""

    template_id: uuid.UUID
    group_name: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Optional aggregation group name to combine jobs from multiple templates.",
    )
    report_date: date
    report_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    status: str = Field(default="approved", pattern=r"^(approved)$")


class DailyReportResponse(BaseModel):
    """Response: daily report generation result."""

    status: str
    report_date: date
    report_id: Optional[uuid.UUID] = None
    report_name: str
    jobs_total: int
    jobs_selected: int
    duplicates_skipped: int
    partial_rows: int
    row_status_counts: dict[str, int] = Field(default_factory=dict)
    output_s3_key: Optional[str] = None


class AggregateByDateRequest(BaseModel):
    """Request: create aggregation report by calendar date."""

    report_date: date
    template_id: Optional[uuid.UUID] = None
    report_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None


# ──────────────────────────────────────────────
# Deterministic Sheet Ingestion Schemas
# ──────────────────────────────────────────────

class GoogleSheetIngestionRequest(BaseModel):
    """Request payload for deterministic Google Sheet ingestion."""

    template_id: uuid.UUID
    sheet_id: Optional[str] = Field(None, min_length=1, max_length=200, description="Google Sheet ID or URL. Overrides template's google_sheet_id if provided.")
    worksheet: Optional[str] = Field(None, min_length=1, max_length=200, description="Worksheet name. Used only in single-config mode (legacy).")
    worksheet_gid: Optional[str] = Field(None, min_length=1, max_length=50, description="Google Sheet worksheet GID (numeric or alphanumeric). If provided, overrides worksheet name by looking up the actual sheet title from the spreadsheet metadata.")
    schema_path: Optional[str] = Field(None, min_length=1, max_length=500, description="Path to YAML schema. Used only in single-config mode (legacy).")
    source_document_id: Optional[uuid.UUID] = None
    range_a1: Optional[str] = Field(None, max_length=200, description="A1 notation range. Used only in single-config mode (legacy).")
    configs: Optional[list[GoogleSheetWorksheetConfig]] = Field(
        None,
        description="List of worksheet configurations. If provided, overrides single-field configs and template's google_sheet_configs. Enables multi-worksheet ingestion from one Sheet ID."
    )
    mode: Optional[str] = Field("generic", description="Ingestion mode: 'kv30' (hardcoded KV30 daily report) or 'generic' (requires worksheet/schema config).")


class IngestionRowError(BaseModel):
    row_index: int
    status: str | None = None
    errors: list[str]
    row: dict[str, Any]


class GoogleSheetIngestionSummary(BaseModel):
    """Response model for Google Sheet ingestion.

    Used for both row-level and snapshot ingestion modes. Fields may be None
    depending on the ingestion mode.
    """

    status: str
    sheet_id: str
    # Row-level: worksheet name; Snapshot: None (multiple worksheets)
    worksheet: Optional[str] = None
    rows_processed: Optional[int] = None
    rows_failed: Optional[int] = None
    # Row-level: number of rows inserted; Snapshot: unused
    rows_inserted: Optional[int] = None
    # Row-level: duplicate/empty rows; Snapshot: unused
    rows_skipped_idempotent: Optional[int] = None
    # Row-level: schema match rate per row; Snapshot: unused
    schema_match_rate: Optional[float] = None
    # Row-level: validation error rate; Snapshot: unused
    validation_error_rate: Optional[float] = None
    errors: list[IngestionRowError] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)

    # Snapshot-specific fields
    job_id: Optional[str] = None
    report_date: Optional[date] = None
    report_version: Optional[int] = None
    worksheets_processed: Optional[list[str]] = None
    rows_valid: Optional[int] = None
    validation_summary: Optional[dict[str, Any]] = None
    ingestion_mode: Optional[str] = Field(None, description="'row' or 'snapshot'")
    error: Optional[str] = Field(None, description="Error message if status is 'error'")
    resolver_debug: Optional[dict[str, Any]] = Field(None, description="Worksheet resolver debug info")

    # KV30 daily report snapshot summary (date-level aggregation)
    dates_created: Optional[int] = Field(None, description="Number of new date reports created")
    dates_duplicate: Optional[int] = Field(None, description="Number of duplicate date reports skipped")
    dates_skipped_no_data: Optional[int] = Field(None, description="Number of dates skipped due to no meaningful data")
    dates: Optional[list[str]] = Field(None, description="List of date keys processed (YYYY-MM-DD)")
    jobs: Optional[list[dict]] = Field(None, description="List of job creation results per date")


class GoogleSheetIngestionEnqueueResponse(BaseModel):
    """Response payload for async Google Sheet ingestion scheduling."""

    status: str
    batch_id: str
    task_id: str
    poll_url: str


class GoogleSheetIngestionTaskStatus(BaseModel):
    """Polling status for async Google Sheet ingestion task."""

    task_id: str
    state: str
    status: str
    summary: Optional[GoogleSheetIngestionSummary] = None
    error: Optional[str] = None
