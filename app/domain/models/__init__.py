"""SQLAlchemy model package.

Import all model modules so their tables register on Base.metadata.
"""

from app.domain.models.daily_report_edit import DailyReportEdit
from app.domain.models.daily_report_review import DailyReportReview
from app.domain.models.document import Document, DocumentStatus
from app.domain.models.extraction_job import (
    AggregationReport,
    EnrichmentStatus,
    ExtractionJob,
    ExtractionJobStatus,
    ExtractionTemplate,
    WeeklyReport,
)
from app.domain.models.tenant import Tenant, TenantUsageLog, UserTenantRole
from app.domain.models.user import User

__all__ = [
    "AggregationReport",
    "DailyReportEdit",
    "DailyReportReview",
    "Document",
    "DocumentStatus",
    "EnrichmentStatus",
    "ExtractionJob",
    "ExtractionJobStatus",
    "ExtractionTemplate",
    "Tenant",
    "TenantUsageLog",
    "User",
    "UserTenantRole",
    "WeeklyReport",
]
