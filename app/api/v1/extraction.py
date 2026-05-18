"""Compatibility router for Engine 2 extraction endpoints.

The active implementation is split across focused routers:
- templates
- jobs
- aggregation/reports

Importing `app.api.v1.extraction.router` still works for legacy callers, but
the disabled monolithic router body has been removed to avoid stale endpoints
and dead standard/vision mode references.
"""

from fastapi import APIRouter

from app.api.v1.aggregation import router as reports_router
from app.api.v1.jobs import router as jobs_router
from app.api.v1.templates import router as templates_router

router = APIRouter(prefix="/extraction", tags=["Extraction (Engine 2)"])
router.include_router(templates_router)
router.include_router(jobs_router)
router.include_router(reports_router)
