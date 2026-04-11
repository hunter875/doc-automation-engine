"""Template management for Engine 2 extraction schemas."""

from __future__ import annotations

import logging
import re
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.exceptions import ProcessingError
from app.domain.models.extraction_job import ExtractionTemplate

logger = logging.getLogger(__name__)


class TemplateManager:
    """DB-only manager for extraction templates."""

    def __init__(self, db: Session):
        self.db = db

    def create_template(
        self,
        tenant_id: str,
        user_id: str,
        name: str,
        schema_definition: dict,
        description: str | None = None,
        aggregation_rules: dict | None = None,
        word_template_s3_key: str | None = None,
        filename_pattern: str | None = None,
        extraction_mode: str = "standard",
    ) -> ExtractionTemplate:
        template = ExtractionTemplate(
            tenant_id=tenant_id,
            name=name,
            description=description,
            schema_definition=schema_definition,
            aggregation_rules=aggregation_rules or {},
            word_template_s3_key=word_template_s3_key,
            filename_pattern=filename_pattern,
            extraction_mode=extraction_mode,
            created_by=user_id,
        )
        self.db.add(template)
        self.db.commit()
        self.db.refresh(template)
        logger.info("Created template '%s' (id=%s) for tenant %s", name, template.id, tenant_id)
        if not template.word_template_s3_key:
            logger.warning(
                "TEMPLATE_INVALID_STATE | template_id=%s tenant_id=%s "
                "word_template_s3_key=NULL — Word export will fail until a .docx is attached.",
                template.id, tenant_id,
            )
        return template

    def get_template(self, template_id: str, tenant_id: str) -> ExtractionTemplate:
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
        template = self.get_template(template_id, tenant_id)

        if "schema_definition" in kwargs and kwargs["schema_definition"] is not None:
            template.version += 1

        for key, value in kwargs.items():
            if value is not None and hasattr(template, key):
                setattr(template, key, value)

        # Warn when a template is active but has no Word template — Word export
        # will 400 for this template. This is not an error (extraction still works),
        # but it appears in operator logs so the state is visible.
        if template.is_active and not template.word_template_s3_key:
            logger.warning(
                "TEMPLATE_INVALID_STATE | template_id=%s tenant_id=%s "
                "is_active=True word_template_s3_key=NULL — Word export will fail.",
                template.id, template.tenant_id,
            )

        template.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(template)
        logger.info(
            "TEMPLATE_UPDATED | template_id=%s tenant_id=%s is_active=%s word_template_s3_key=%s",
            template.id, template.tenant_id, template.is_active, template.word_template_s3_key,
        )
        return template

    def delete_template(self, template_id: str, tenant_id: str) -> None:
        template = self.get_template(template_id, tenant_id)
        template.is_active = False
        template.updated_at = datetime.utcnow()
        self.db.commit()

    # ── Auto-detection ────────────────────────────────────────────────────────

    def detect_template(
        self,
        tenant_id: str,
        filename: str,
        first_page_text: str | None = None,
    ) -> ExtractionTemplate | None:
        """Auto-match a file to a template.

        Strategy (priority order):
        1. filename_pattern regex match against the filename.
        2. Field coverage: count how many template field names appear in
           first_page_text, pick the template with highest coverage ≥ 70%.
        3. If only one active template exists, return it (single-template tenant).

        Returns None if no confident match.
        """
        templates = (
            self.db.query(ExtractionTemplate)
            .filter(
                ExtractionTemplate.tenant_id == tenant_id,
                ExtractionTemplate.is_active.is_(True),
            )
            .all()
        )
        if not templates:
            return None

        # Strategy 1: filename_pattern regex
        for tpl in templates:
            pattern = tpl.filename_pattern
            if pattern:
                try:
                    if re.search(pattern, filename, re.IGNORECASE):
                        logger.info(
                            "Auto-matched '%s' to template '%s' via filename_pattern",
                            filename, tpl.name,
                        )
                        return tpl
                except re.error:
                    pass  # skip invalid pattern silently

        # Strategy 2: field coverage from first page text
        if first_page_text and len(first_page_text) > 20:
            text_lower = first_page_text.lower()
            best_tpl = None
            best_score = 0.0
            for tpl in templates:
                schema = tpl.schema_definition or {}
                fields = schema.get("fields", []) if isinstance(schema, dict) else []
                if not fields:
                    continue
                field_names = [f.get("name", "") for f in fields if f.get("name")]
                if not field_names:
                    continue
                # Count how many field names appear as substrings in the text
                hits = sum(1 for fn in field_names if fn.lower() in text_lower)
                coverage = hits / len(field_names)
                if coverage > best_score:
                    best_score = coverage
                    best_tpl = tpl
            if best_tpl and best_score >= 0.7:
                logger.info(
                    "Auto-matched '%s' to template '%s' via field coverage (%.0f%%)",
                    filename, best_tpl.name, best_score * 100,
                )
                return best_tpl

        # Strategy 3: single template fallback
        if len(templates) == 1:
            logger.info(
                "Auto-matched '%s' to the only active template '%s'",
                filename, templates[0].name,
            )
            return templates[0]

        return None
