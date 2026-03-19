"""Template management for Engine 2 extraction schemas."""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.exceptions import ProcessingError
from app.models.extraction import ExtractionTemplate

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
    ) -> ExtractionTemplate:
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
        logger.info("Created template '%s' (id=%s) for tenant %s", name, template.id, tenant_id)
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

        template.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(template)
        return template

    def delete_template(self, template_id: str, tenant_id: str) -> None:
        template = self.get_template(template_id, tenant_id)
        template.is_active = False
        template.updated_at = datetime.utcnow()
        self.db.commit()
