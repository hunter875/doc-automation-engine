"""Backward-compatible facade for Engine 2 services.

This module preserves `ExtractionService` API while delegating responsibilities
to:
- `TemplateManager`
- `JobManager`
- `ExtractionOrchestrator`
"""

from sqlalchemy.orm import Session

from app.engines.extraction.orchestrator import ExtractionOrchestrator
from app.application.job_service import JobManager
from app.application.template_service import TemplateManager

class ExtractionService:
    """Compatibility layer mapping old method names to new service modules."""

    def __init__(self, db: Session):
        self.db = db
        self.templates = TemplateManager(db)
        self.jobs = JobManager(db)
        self.orchestrator = ExtractionOrchestrator(db, job_manager=self.jobs)

    def create_template(self, *args, **kwargs):
        return self.templates.create_template(*args, **kwargs)

    def get_template(self, *args, **kwargs):
        return self.templates.get_template(*args, **kwargs)

    def list_templates(self, *args, **kwargs):
        return self.templates.list_templates(*args, **kwargs)

    def update_template(self, *args, **kwargs):
        return self.templates.update_template(*args, **kwargs)

    def delete_template(self, *args, **kwargs):
        return self.templates.delete_template(*args, **kwargs)

    def create_job(self, *args, **kwargs):
        return self.jobs.create_job(*args, **kwargs)

    def get_job(self, *args, **kwargs):
        return self.jobs.get_job(*args, **kwargs)

    def list_jobs(self, *args, **kwargs):
        return self.jobs.list_jobs(*args, **kwargs)

    def get_batch_status(self, *args, **kwargs):
        return self.jobs.get_batch_status(*args, **kwargs)

    def update_job_status(self, *args, **kwargs):
        return self.jobs.update_job_status(*args, **kwargs)

    def approve_job(self, *args, **kwargs):
        return self.jobs.approve_job(*args, **kwargs)

    def reject_job(self, *args, **kwargs):
        return self.jobs.reject_job(*args, **kwargs)

    def retry_job(self, *args, **kwargs):
        return self.jobs.retry_job(*args, **kwargs)

    def delete_job(self, *args, **kwargs):
        return self.jobs.delete_job(*args, **kwargs)

    def run_extraction(self, job_id: str):
        return self.orchestrator.run(job_id)
