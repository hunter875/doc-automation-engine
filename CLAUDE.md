# Engine 2 — AI Data Extraction

## Stack
FastAPI · SQLAlchemy · Celery · PostgreSQL JSONB · Ollama (Instructor + Pydantic) · docxtpl

## Key paths
- Sheet pipeline: app/engines/extraction/sheet_ingestion_service.py, sheet_pipeline.py
- Block pipeline: app/engines/extraction/block_pipeline.py
- Orchestrator: app/engines/extraction/orchestrator.py
- Celery tasks: app/infrastructure/worker/extraction_tasks.py, enrichment_tasks.py
- YAML templates: app/domain/templates/pccc.yaml

## Critical invariants
- GoogleSheetIngestionService MUST NOT call any LLM
- SheetExtractionPipeline MUST NOT fetch Google Sheets API
- extract_document_task phải pass source_type="sheet" + sheet_data khi parser_used == "google_sheets"
- row_hash idempotency scope: (tenant_id, template_id, sheet_id, worksheet)

## DB
PostgreSQL JSONB. Dùng GIN index cho extracted_data, reviewed_data, schema_definition.
KHÔNG migrate thêm column mà không chạy migrate_add_enrichment_columns.py pattern.