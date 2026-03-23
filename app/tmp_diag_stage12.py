from app.db.postgres import SessionLocal
from app.models.document import Document
from app.models.tenant import Tenant, UserTenantRole  # noqa: F401
from app.models.user import User  # noqa: F401
from app.services.doc_service import s3_client
from app.core.config import settings
from app.services.hybrid_extraction_pipeline import HybridExtractionPipeline

JOB_DOC_ID = "4cf2a1ec-6e4d-4b1e-a8d9-4f37cabd6bfd"


def main() -> None:
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == JOB_DOC_ID).first()
        if not doc:
            print("DOC_NOT_FOUND")
            return

        obj = s3_client.get_object(Bucket=settings.S3_BUCKET_NAME, Key=doc.s3_key)
        pdf_bytes = obj["Body"].read()

        pipeline = HybridExtractionPipeline(extraction_mode="standard")
        ing = pipeline.stage1_ingest(pdf_bytes)
        norm = pipeline.stage2_normalize(ing)

        print("FILE:", doc.file_name)
        print("S3_KEY:", doc.s3_key)
        print("TEXT_STREAM_LEN:", len((ing.text_stream or "").strip()))
        print("PAGES:", len(ing.pages))
        print("TABLE_COUNT:", len(ing.table_stream or []))
        print("FLATTENED_TABLE_LINES:", len(norm.flattened_table_lines or []))
        print("CLEAN_TEXT_LEN:", len((norm.cleaned_text or "").strip()))

        sample_text = (norm.cleaned_text or "")[:1200].replace("\n", " ")
        print("CLEAN_TEXT_SAMPLE:", sample_text)

        print("TABLE_LINES_SAMPLE:")
        for i, line in enumerate((norm.flattened_table_lines or [])[:30], start=1):
            print(f"{i:02d}. {line}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
