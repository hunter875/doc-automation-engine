"""Quick check: verify enriched_data is saved and final_data merges correctly."""
import sys
sys.path.insert(0, '/app')

import app.domain.models  # noqa: F401 — load all models so SQLAlchemy can map relationships
import app.domain.models.tenant  # noqa: F401 — ensure Tenant is registered
import app.domain.models.document  # noqa: F401 — ensure Document is registered
import app.domain.models.user  # noqa: F401 — ensure User is registered
from app.infrastructure.db.session import SessionLocal
from app.domain.models.extraction_job import ExtractionJob
from app.schemas.extraction_schema import JobResponse

db = SessionLocal()
try:
    jobs = (
        db.query(ExtractionJob)
        .filter(ExtractionJob.enriched_data.isnot(None))
        .order_by(ExtractionJob.created_at.desc())  # type: ignore[attr-defined]
        .limit(3)
        .all()
    )

    if not jobs:
        print("No enriched jobs found in DB.")
        sys.exit(0)

    for job in jobs:
        print(f"\n=== Job {str(job.id)[:8]}  status={job.status} ===")
        enr = job.enriched_data or {}
        enr_cnch = enr.get("danh_sach_cnch", [])
        print(f"  enriched_data.danh_sach_cnch count: {len(enr_cnch)}")
        if enr_cnch:
            inc = enr_cnch[0]
            print(f"  enriched ngay_xay_ra     : {inc.get('ngay_xay_ra')!r}")
            print(f"  enriched noi_dung_tin_bao: {inc.get('noi_dung_tin_bao')!r}")
            print(f"  enriched ket_qua_xu_ly   : {inc.get('ket_qua_xu_ly')!r}")

        # Now check JobResponse (what the API returns)
        resp = JobResponse.model_validate(job)
        resp_cnch = (resp.extracted_data or {}).get("danh_sach_cnch", [])
        print(f"  JobResponse.extracted_data (= final_data) cnch count: {len(resp_cnch)}")
        if resp_cnch:
            inc2 = resp_cnch[0]
            print(f"  API ngay_xay_ra     : {inc2.get('ngay_xay_ra')!r}")
            print(f"  API noi_dung_tin_bao: {inc2.get('noi_dung_tin_bao')!r}")
            print(f"  API ket_qua_xu_ly   : {inc2.get('ket_qua_xu_ly')!r}")
finally:
    db.close()
