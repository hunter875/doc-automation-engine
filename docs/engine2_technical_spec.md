# ⚙️ Engine 2 — Hệ thống Bóc tách Dữ liệu Tự động (AI Data Extraction)

> **Phiên bản:** 4.0.0  
> **Cập nhật:** 03/04/2026  
> **Stack:** FastAPI · SQLAlchemy · Celery · PostgreSQL (JSONB) · Ollama (Instructor + Pydantic) · docxtpl · YAML Templates · PipelineMetrics · Two-Stage Block Pipeline  

---

## Mục lục

1. [Tổng quan](#1-tổng-quan)
2. [Kiến trúc Lưu trữ — PostgreSQL Hybrid](#2-kiến-trúc-lưu-trữ--postgresql-hybrid)
3. [Pipeline 4 Bước Khép Kín](#3-pipeline-4-bước-khép-kín)
4. [Bước 1: Bóc tách thô (Hybrid Extraction)](#4-bước-1-bóc-tách-thô-hybrid-extraction)
5. [Block Mode — Two-Stage Pipeline (v4)](#5-block-mode--two-stage-pipeline-v4)
6. [Bước 2: Rây lọc & Ép kiểu (Validation Layer)](#6-bước-2-rây-lọc--ép-kiểu-validation-layer)
7. [Bước 3: Xào nấu dữ liệu (Aggregation & Map-Reduce)](#7-bước-3-xào-nấu-dữ-liệu-aggregation--map-reduce)
8. [Bước 4: Bơm khuôn Word (Headless Document Export)](#8-bước-4-bơm-khuôn-word-headless-document-export)
9. [Database Schema](#9-database-schema)
10. [API Reference — 25 Endpoints](#10-api-reference--25-endpoints)
11. [Cấu hình (Configuration)](#11-cấu-hình-configuration)
12. [Celery Workers & Background Tasks](#12-celery-workers--background-tasks)
13. [Word Template Scanner](#13-word-template-scanner)
14. [Pydantic Schemas (Request/Response)](#14-pydantic-schemas-requestresponse)
15. [Phase 3 — Template-driven · Dynamic Columns · Batch Parallel · Observability](#15-phase-3--template-driven--dynamic-columns--batch-parallel--observability)
16. [Cấu trúc Source Code](#16-cấu-trúc-source-code)
17. [Ví dụ End-to-End](#17-ví-dụ-end-to-end)

---

## 1. Tổng quan

Engine 2 là hệ thống **bóc tách dữ liệu có cấu trúc** từ tài liệu PDF/Word. Khác với Engine 1 (RAG — hỏi đáp tự do), Engine 2 **ra lệnh cho AI trả về JSON đúng schema**, rồi tổng hợp N file thành 1 báo cáo.

### Bài toán giải quyết

```
📄 Báo cáo Ngày 1 (PDF)  ─┐
📄 Báo cáo Ngày 2 (PDF)  ─┤──→ AI bóc tách ──→ Validation ──→ Aggregation ──→ 📊 Báo cáo Tuần (Word)
📄 Báo cáo Ngày 3 (PDF)  ─┘
```

### Tính năng chính

| # | Tính năng | Mô tả |
|---|---|---|
| 1 | **Hybrid extraction mặc định** | Chạy `HybridExtractionPipeline` (pdfplumber + normalize + Ollama + rule validation) từ bytes in-memory |
| 2 | **Block mode two-stage (v4)** | Stage 1 = deterministic (không LLM), Stage 2 = LLM enrichment async độc lập. Document dùng được ngay sau Stage 1 kể cả khi Ollama tắt |
| 3 | **Sheet mode (v4)** | Deterministic extraction từ Google Sheets hoặc Excel. Không LLM, trả về canonical `BlockExtractionOutput`. Dùng chung pipeline và aggregation với PDF |
| 4 | **Template-driven** | Định nghĩa schema JSON → AI bóc tách đúng format |
| 5 | **YAML Template System** | Tất cả regex/pattern/threshold được gửi ngoài vào file YAML (`app/templates/pccc.yaml`), không còn hardcode |
| 6 | **Dynamic Column Detection** | Tự động phát hiện cột STT/Nội dung/Kết quả trong bảng thống kê thay vì giả định cố định |
| 7 | **Validation Layer** | Ép kiểu, chuẩn hóa ngày, phát hiện lỗi TRƯỚC khi lưu DB |
| 8 | **Human-in-the-loop** | Review (approve/reject/edit) trước khi aggregate |
| 9 | **Aggregation** | SUM, AVG, COUNT, CONCAT → gom N báo cáo thành 1 |
| 10 | **Word Export** | Nhồi dữ liệu vào template Word bằng Jinja2 (docxtpl) |
| 11 | **Word Scanner** | Quét file Word mẫu → auto-generate schema |
| 12 | **Batch processing (Celery)** | Upload N file cùng lúc (max 20) → N Celery tasks phân tán |
| 13 | **Batch parallel (in-process)** | `run_batch()` chạy block pipeline song song với `ThreadPoolExecutor` + backpressure |
| 14 | **Observability Metrics** | `PipelineMetrics` (per-run counters/timers) + `GlobalMetrics` (thread-safe aggregator) + API endpoint |
| 15 | **Multi-tenant** | Cách ly hoàn toàn theo `tenant_id` |

---

## 2. Kiến trúc Lưu trữ — PostgreSQL Hybrid

> **Nguyên tắc: Giữ nguyên PostgreSQL, KHÔNG đổi sang NoSQL.**

### 2.1 Tầng Relational (Cột cứng)

Quản lý phân quyền, quan hệ thực thể, đảm bảo ACID:

```
tenants.id ──→ extraction_templates.tenant_id
               extraction_jobs.tenant_id
               aggregation_reports.tenant_id

users.id ──→ extraction_templates.created_by
             extraction_jobs.created_by / reviewed_by

documents.id ──→ extraction_jobs.document_id

extraction_templates.id ──→ extraction_jobs.template_id
                           aggregation_reports.template_id
```

### 2.2 Tầng Document (Linh hoạt) — JSONB

Dữ liệu bóc tách, schema, kết quả tổng hợp → lưu **JSONB** (không phải JSON):

| Bảng | Cột JSONB | Mục đích |
|---|---|---|
| `extraction_templates` | `schema_definition` | Định nghĩa fields cần bóc tách |
| `extraction_templates` | `aggregation_rules` | Rules tổng hợp (SUM, CONCAT...) |
| `extraction_jobs` | `extracted_data` | Dữ liệu AI bóc tách (đã qua Validation) |
| `extraction_jobs` | `confidence_scores` | Điểm tự tin + validation report |
| `extraction_jobs` | `source_references` | Trích dẫn nguồn (trang, quote) |
| `extraction_jobs` | `reviewed_data` | Dữ liệu sau khi human review |
| `aggregation_reports` | `aggregated_data` | Kết quả tổng hợp cuối cùng |

### 2.3 GIN Indexes

3 GIN index cốt lõi cho truy vấn JSONB thường dùng:

```sql
CREATE INDEX idx_extraction_jobs_extracted_data_gin ON extraction_jobs USING GIN (extracted_data);
CREATE INDEX idx_extraction_jobs_reviewed_data_gin  ON extraction_jobs USING GIN (reviewed_data);
CREATE INDEX idx_extraction_templates_schema_gin    ON extraction_templates USING GIN (schema_definition);
```

`aggregation_reports.aggregated_data` chỉ nên thêm GIN index khi có nghiệp vụ search/filter trực tiếp trên report JSON (ví dụ query `@>` theo ngưỡng tổng hợp). Nếu chỉ dùng để export/render thì để tránh write overhead, nên bỏ index này.

**Query ví dụ** — tìm tất cả jobs có `so_vu > 5`:
```sql
SELECT * FROM extraction_jobs
WHERE extracted_data @> '{"so_vu": 5}'::jsonb;
```

### 2.4 Lý do KHÔNG dùng NoSQL

| Tiêu chí | PostgreSQL JSONB | MongoDB |
|---|---|---|
| ACID transactions | ✅ Có | ❌ Hạn chế |
| JOIN với bảng khác | ✅ SQL chuẩn | ❌ Phải $lookup |
| pgvector (Engine 1) | ✅ Cùng DB | ❌ Cần DB riêng |
| GIN index | ✅ Cực nhanh | ✅ Tương đương |
| Schema linh hoạt | ✅ JSONB | ✅ Native |
| Infra complexity | ✅ 1 DB | ❌ +1 DB nữa |

---

## 3. Pipeline 4 Bước Khép Kín

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        ENGINE 2 PIPELINE                                     │
│                                                                              │
│  ┌──────────┐    ┌──────────────┐    ┌──────────────┐    ┌───────────────┐  │
│  │ BƯỚC 1   │    │   BƯỚC 2     │    │   BƯỚC 3     │    │    BƯỚC 4     │  │
│  │ AI       │    │  Validation  │    │ Aggregation  │    │  Word Export  │  │
│  │ Extract  │───→│  Layer       │───→│ Map-Reduce   │───→│  (docxtpl)   │  │
│  │          │    │  (Pydantic)  │    │  (Pandas)    │    │              │  │
│  └──────────┘    └──────────────┘    └──────────────┘    └───────────────┘  │
│       │                │                    │                    │            │
│   Raw JSON         Clean JSON          Aggregated           .docx file      │
│   (có lỗi)        (đã ép kiểu)          JSON              (hoàn chỉnh)     │
│                                                                              │
│                    ┌──────────┐                                              │
│                    │ HUMAN    │                                              │
│                    │ REVIEW   │ ← Approve / Reject / Edit                   │
│                    └──────────┘                                              │
│                    (giữa Bước 2 & 3)                                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Luồng chi tiết

```
1. User upload PDF + chọn Template
       ↓
2. Celery worker nhận task
       ↓
3. [Bước 1] Worker tải file từ S3 → tùy `extraction_mode`:
  **Standard/Vision/Fast:**
  ├── `pipeline.run_from_bytes()` — pdfplumber + normalize + Ollama + rule validation
  └── `persist_pipeline_result()` → job.status = EXTRACTED

  **Block (v4 — two-stage):**
  ├── `pipeline.run_stage1_from_bytes()` — pdfplumber + regex ONLY, no LLM
  ├── `persist_stage1_result()` → job.status = EXTRACTED, enrichment_status = PENDING
  └── `enrich_job_task.apply_async(queue="enrichment")` → fire-and-forget
     ↓
4. [Stage 1 Block] 6 sub-stages (tất cả deterministic):
  ├── layout reconstruction (pdfplumber + restore_vn_spacing)
  ├── block detection (regex anchors từ YAML template)
  ├── header extraction (regex: số báo cáo, ngày, đơn vị)
  ├── narrative extraction (regex: tong_so_vu_*, chi_tiet_cnch)
  ├── table parsing (dynamic column detect + pdfplumber)
  └── business rules engine + sanity checks
     ↓
5. [Stage 2 Block — async, queue enrichment] enrich_job_task:
  ├── Đọc chi_tiet_cnch từ extracted_data
  ├── Gọi CNCHListOutput LLM (120s timeout, model: qwen3:8b)
  ├── Thành công → enriched_data = {"danh_sach_cnch": [...]}
  └── Thất bại → enrichment_status = FAILED, job vẫn dùng được
     ↓
6. INSERT → extraction_jobs.extracted_data (Stage 1) + enriched_data (Stage 2)
       ↓
7. [Human Review] Approve / Reject / Edit → reviewed_data
       ↓
8. [Bước 3] N jobs approved → AggregationService.aggregate()
   ├── pd.json_normalize() đập phẳng nested JSON
   ├── Apply rules: SUM, AVG, COUNT, CONCAT, LAST
   └── Output: aggregated_data + records + _flat_records + _metadata
       ↓
9. [Bước 4] Upload Word template (.docx) + aggregated_data
   ├── docxtpl render Jinja2 placeholders
   ├── Filters: number_vn, date_vn, date_short
   └── Download: file .docx hoàn chỉnh
```

---

## 4. Bước 1: Bóc tách thô (Hybrid Extraction)

**Files chính:**
- `app/engines/extraction/orchestrator.py`
- `app/engines/extraction/hybrid_pipeline.py`
- `app/engines/extraction/block_pipeline.py` *(block mode — xem Section 5)*
- `app/engines/extraction/extractors.py`
- `app/engines/extraction/schemas.py`

### 4.1 Kiến trúc chạy hiện tại

**Hybrid mode (standard/vision/fast):**
- Router tạo `ExtractionJob` và đẩy Celery task `extract_document_task` → queue `extraction`
- Worker gọi `ExtractionOrchestrator.run(job_id)`
- Orchestrator tải file từ S3, chạy `pipeline.run_from_bytes(file_bytes, filename)`
- Kết quả được `JobManager.persist_pipeline_result()` lưu về DB

**Block mode (v4 — two-stage):**
- Orchestrator nhận diện `extraction_mode == "block"` và dùng đường đặc biệt:
  1. Gọi `pipeline.run_stage1_from_bytes()` — không có LLM, trả về ngay
  2. Gọi `persist_stage1_result()` → `job.status = EXTRACTED`, `job.enrichment_status = PENDING`
  3. Dispatch `enrich_job_task.apply_async(queue="enrichment")` → fire-and-forget
- Xem chi tiết tại [Section 5](#5-block-mode--two-stage-pipeline-v4)

### 4.2 Hybrid pipeline 4 chặng

1. **Ingest:** Parse PDF bằng `pdfplumber` (text + table)
2. **Normalization:** Dọn layout, ghép dòng, ép phẳng bảng thành cặp field/value
3. **Inference:** Gọi extractor strategy (mặc định `OllamaInstructorExtractor`) và ép output theo `HybridExtractionOutput`
4. **Validation/Retry:** RuleEngine kiểm tra logic domain; fail thì retry, quá ngưỡng thì chuyển manual-review metadata

### 4.3 Domain Validation (Tiêm Rule động)

`RuleEngine` là core dùng chung và hỗ trợ tiêm (inject) luật tùy chỉnh theo từng loại tài liệu.

- Ví dụ với nghiệp vụ PCCC: `stt_14_tong_cnch == len(danh_sach_cnch)`
- Ví dụ khác: check format ngày `dd/mm/yyyy`, date range, đối soát count/list theo domain

### 4.4 Trạng thái lưu kết quả

- **Success:** `status=extracted`, `extracted_data=<output model_dump>`
- **Fail sau retries:** `status=failed`, `extracted_data` chứa `_manual_review_path` và `_manual_review_metadata`
- `confidence_scores` lưu `_validation_attempts` + trạng thái pipeline

---

## 5. Block Mode — Two-Stage Pipeline (v4)

> **Nguyên tắc cốt lõi:** LLM không bao giờ nằm trên critical path. Document phải dùng được ngay sau Stage 1 kể cả khi Ollama tắt hoàn toàn.

### 5.1 Tại sao cần Two-Stage

| Vấn đề (v3 — một stage) | Giải pháp (v4 — two-stage) |
|---|---|
| LLM timeout 120s → user chờ 120s mới thấy kết quả | User thấy kết quả ngay sau Stage 1 (~vài giây) |
| Ollama chết → toàn bộ job `FAILED`, không có dữ liệu nào | Ollama chết → job vẫn `EXTRACTED`, dùng bình thường |
| 4 extraction workers tất cả chờ LLM | 4 extraction workers chạy tự do; 2 enrichment workers riêng xử lý LLM |
| LLM output lẫn vào `extracted_data` → khó audit | LLM output trong `enriched_data` riêng, `final_data` merge theo priority rõ ràng |

### 5.2 Kiến trúc tổng quan

```
┌────────────────────────────────────────────────────────────────────────────────┐
│                       BLOCK MODE TWO-STAGE PIPELINE (v4)                       │
│                                                                                │
│  ┌──────────────────────────────────┐      ┌──────────────────────────────────┐ │
│  │          STAGE 1                 │      │          STAGE 2                 │ │
│  │    (Deterministic — No LLM)      │      │    (LLM Enrichment — Async)      │ │
│  │                                  │      │                                  │ │
│  │  1. PDF layout reconstruction    │      │  1. Read chi_tiet_cnch from DB   │ │
│  │  2. Block detection              │─────→│  2. Call CNCHListOutput (120s)   │ │
│  │  3. Header extraction (regex)    │ fire │  3. Write enriched_data (JSONB)  │ │
│  │  4. Narrative extraction (regex) │ and  │  4. enrichment_status = ENRICHED │ │
│  │  5. Table parsing (pdfplumber)   │ forget    hoặc FAILED nếu lỗi           │ │
│  │  6. Business rules engine        │      │                                  │ │
│  │  7. Regex CNCH / vehicle / CV    │      └──────────────────────────────────┘ │
│  │                                  │               Queue: enrichment           │
│  │  → job.status = EXTRACTED        │               concurrency = 2             │
│  │  → enrichment_status = PENDING   │                                          │
│  └──────────────────────────────────┘                                          │
│           Queue: extraction                                                     │
│           concurrency = 4                                                       │
└────────────────────────────────────────────────────────────────────────────────┘
```

### 5.3 Sheet Mode — Deterministic Spreadsheet Extraction

> **Sheet mode** là chế độ extraction độc lập, không dùng LLM, không dùng PDF. Nó xử lý **Google Sheets API** và **Excel files** (KV30 format) và trả về chính xác `BlockExtractionOutput` như Block mode.

**Entry point:** `ExtractionOrchestrator.run_sheet_pipeline(sheet_data)`  
**File:** `app/engines/extraction/sheet_pipeline.py`

**Tại sao sheet mode tồn tại riêng?**
- Input format khác biệt hoàn toàn: structured rows (spreadsheet) vs unstructured PDF
- Không cần layout reconstruction, block detection
- Field mapping và normalization là chính
- Không bao giờ cần LLM enrichment (deterministic 100%)

**Kiến trúc:**

```
Google Sheets API / Excel File
         ↓
    SheetExtractionPipeline
         ↓
    normalize() — flatten nested payloads
         ↓
    map_to_schema() — alias resolution + STT mapping
         ↓
    _inject_computed_bang_thong_ke_rows() — STT 32/33/51 auto-compute
         ↓
    _inject_online_rows() — STT 22-25 from online metrics
         ↓
    BlockExtractionOutput (canonical)
```

**Các thành phần chính:**

| Component | File | Mô tả |
|-----------|------|-------|
| `GoogleSheetIngestionService` | `sheet_ingestion_service.py` | Ingest rows từ Google Sheets vào `extraction_jobs` với idempotency |
| `SheetExtractionPipeline` | `sheet_pipeline.py` | Chuyển sheet payload → canonical `BlockExtractionOutput` |
| `GoogleSheetsSource` | `sources/sheets_source.py` | Google Sheets API client (retry logic) |
| `HeaderDetector` | `mapping/header_detector.py` | Tự động phát hiện header row bằng alias overlap |
| `Mapper` | `mapping/mapper.py` | Map row columns → schema fields với alias matching |
| `RowValidator` | `validation/row_validator.py` | Pydantic validation + confidence scoring |
| `JobWriter` | `sheet_job_writer.py` | Persist validated rows với row_hash idempotency |

**Sheet ingestion flow:**

```
HTTP POST /jobs/ingest/google-sheet
    ↓
GoogleSheetIngestionService.ingest()
    ↓
GoogleSheetsSource.fetch_values() [Google API]
    ↓
detect_header_row() [alias scoring]
    ↓
FOR EACH ROW:
    map_row_to_document_data() [alias + normalize]
    validate_row() [Pydantic]
    build_row_hash() [SHA-256]
    writer.is_duplicate() [check in-memory set]
    writer.write_row() [DB commit, set parser_used="google_sheets"]
    ↓
Return ingestion summary
```

**Sheet extraction flow (dùng chung orchestrator):**

```
ExtractionOrchestrator.run(job_id, source_type="sheet", sheet_data=job.extracted_data)
    ↓
run_sheet_pipeline(sheet_data)
    ↓
SheetExtractionPipeline.run()
    ↓
normalize() — hỗ trợ multiple shapes: {"data": {...}}, {"header": {...}}, flat
    ↓
map_to_schema() — load sheet_mapping.yaml, resolve aliases
    ↓
Build BlockExtractionOutput:
    - header: from header dict (so_bao_cao, ngay_bao_cao, thoi_gian_tu_den, don_vi_bao_cao)
    - phan_I_va_II_chi_tiet_nghiep_vu: từ nghiệp_vu fields (tong_so_vu_chay, etc.)
    - bang_thong_ke: list[ChiTieu] từ STT mapping (61 rows)
    - danh_sach_cnch: from danh_sach_cnch array
    - danh_sach_phuong_tien_hu_hong: from array
    - danh_sach_cong_van_tham_muu: from array
    - danh_sach_cong_tac_khac: from array
    ↓
_assert_contract_or_raise() — validate 7 expected top-level keys
    ↓
Return PipelineResult(status="ok", output=BlockExtractionOutput)
```

**Sheet-specific mapping (`sheet_mapping.yaml`):**

- **61 STT rows** với `stt_map` mapping từ STT number → field name
- Ví dụ: `"2": {noi_dung: "1. Tổng số vụ cháy", field: "tong_so_vu_chay"}`
- **Computed STT injection:**
  - STT 32 = STT 31 - STT 33 (kiểm tra định kỳ)
  - STT 33 = STT 31 - STT 32 (kiểm tra đột xuất)
  - STT 51 = STT 52 - STT 53 (PA PC09 residual)
  - STT 25 = STT 22 + STT 23 (tổng online)

**Integration với Block mode:**

- **Cùng database:** extraction_jobs bảng dùng chung
- **Cùng canonical output:** `BlockExtractionOutput` schema
- **Cùng aggregation:** sheet jobs và PDF jobs có thể aggregate chung
- **Khác biệt:** Sheet mode không có Stage 2 enrichment (không cần LLM)

---

## 6. Bước 2: Rây lọc & Ép kiểu (Validation Layer)

**Entry point:** `BlockExtractionPipeline.run_stage1_from_bytes(pdf_bytes, filename)`  
**File:** `app/engines/extraction/block_pipeline.py`

Gồm 6 stage nội bộ, **tất cả đều không gọi LLM**:

| Stage nội bộ | Timer metric | Mô tả |
|---|---|---|
| `stage1_layout` | `stage1_layout` | `pdfplumber` tái tạo text + extract tables. `layout_text` giữ trật tự đọc |
| `stage2_detect` | `stage2_detect` | Phát hiện block: `header`, `phan_nghiep_vu`, `bang_thong_ke` bằng regex anchor từ YAML template |
| `stage3_extract` | `stage3_extract` | `_extract_header()` → regex; `_extract_narrative()` → regex (`_parse_phan_nghiep_vu_fallback`); `_extract_table()` → dynamic column detect + pdfplumber; `_apply_cnch_fallback()` → đối soát với bảng thống kê |
| `stage6_business` | `stage6_business` | `_run_business_rules()` → RuleEngine check tất cả domain logic (counts, date format, sanity) |
| `stage_narrative_arrays` | `stage_narrative_arrays` | `_extract_narrative_arrays(..., chi_tiet_cnch="")` với **chi_tiet_cnch trống** → bỏ qua nhánh LLM. Regex/business-rules trích `pt_hu_hong`, `cong_van`, regex CNCH |
| Sanity check | — | Đối soát `tong_so_vu_chay/no/cnch` với bảng thống kê (`stt_2`, `stt_8`, `stt_14`), ghi đè nếu lệch |

**Output:** `PipelineResult`
```python
@dataclass
class PipelineResult:
    status: str                    # "ok" | "failed"
    attempts: int
    output: BlockExtractionOutput | None
    errors: list[str]
    business_data: dict | None
    metrics: dict | None
    chi_tiet_cnch: str = ""        # ← v4 mới: raw CNCH subsection text cho Stage 2
```

**`BlockExtractionOutput` schema:**
```python
class BlockExtractionOutput(BaseModel):
    header: BlockHeader
    phan_I_va_II_chi_tiet_nghiep_vu: BlockNghiepVu
    bang_thong_ke: list[ChiTieu]
    danh_sach_cnch: list[CNCHItem]                     # regex-only ở Stage 1
    danh_sach_phuong_tien_hu_hong: list[PhuongTienHuHongItem]
    danh_sach_cong_van_tham_muu: list[CongVanItem]
```

**Sub-schemas `BlockNghiepVu`:**
```python
class BlockNghiepVu(BaseModel):
    tong_so_vu_chay: int
    tong_so_vu_no: int
    tong_so_vu_cnch: int
    chi_tiet_cnch: str      # ← raw text của mục 3, Stage 2 dùng để gọi LLM
    quan_so_truc: int
    tong_chi_vien: int
    tong_cong_van: int
    tong_xe_hu_hong: int
```

### 5.4 Stage 2 — LLM Enrichment

**Entry point:** `enrich_job_task(job_id)` — Celery task  
**File:** `app/infrastructure/worker/enrichment_tasks.py`  
**Queue:** `enrichment` | **Concurrency:** 2 | **Soft time limit:** 180s | **Max retries:** 3

LLM method duy nhất trong toàn bộ block pipeline:

```python
def _llm_enrich_cnch(self, chi_tiet_cnch: str) -> list[CNCHItem]:
    """Gọi CNCHListOutput LLM call — PHƯƠNG THỨC DUY NHẤT gọi LLM trong block pipeline."""
    result: CNCHListOutput = self.extractor.extract(
        messages=[
            {"role": "system", "content": cnch_prompt},
            {"role": "user", "content": chi_tiet_cnch},
        ],
        response_model=CNCHListOutput,
        model=self.model,
        temperature=0.0,
        timeout_seconds=120.0,
    )
```

**`CNCHItem` — 8 fields (LLM điền đầy đủ ở Stage 2):**
```python
class CNCHItem(BaseModel):
    stt: int
    ngay_xay_ra: str        # dd/mm/yyyy
    thoi_gian: str          # "HH:MM ngày dd/mm/yyyy" hoặc "HH giờ MM phút ngày dd/mm/yyyy"
    dia_diem: str
    noi_dung_tin_bao: str   # loại sự cố (ví dụ: "người dân nhảy sông")
    luc_luong_tham_gia: str # "01 xe, 06 CBCS"
    ket_qua_xu_ly: str
    thong_tin_nan_nhan: str
    mo_ta: str              # internal — backward compat với business-rules path
```

**Flow của `enrich_job_task`:**
```
1. Load job từ DB
2. Guard: chỉ process khi enrichment_status IN (PENDING, FAILED)
3. Set enrichment_status = RUNNING, enrichment_started_at = now
4. Đọc chi_tiet_cnch từ job.extracted_data["phan_I_va_II_..."]["chi_tiet_cnch"]
5. Gọi BlockExtractionPipeline._llm_enrich_cnch(chi_tiet_cnch)
6. Thành công → job.enriched_data = {"danh_sach_cnch": [...]}, enrichment_status = ENRICHED
   Thất bại → enrichment_status = FAILED, job.extracted_data KHÔNG BỊ ĐỤ VÀO
```

### 5.5 EnrichmentStatus — State machine độc lập

```
           Stage 1 succeeded
                  │
          ┌───────▼────────┐
          │    PENDING     │  enrichment_status = PENDING
          └───────┬────────┘  (enrichment_status = SKIPPED nếu không có chi_tiet_cnch)
                  │ enrich_job_task picked up
          ┌───────▼────────┐
          │    RUNNING     │
          └────┬───────┬───┘
       success │       │ failure
          ┌────▼───┐  ┌▼───────┐
          │ENRICHED│  │ FAILED │ ← job vẫn EXTRACTED, dùng Stage 1 data
          └────────┘  └───┬────┘
                          │ retry (max 3, backoff 60s)
                          └──────→ RUNNING lại
```

`None` = job được tạo trước khi upgrade lên v4 (legacy, không có enrichment)

### 5.6 Merge priority — `final_data` property

```python
@property
def final_data(self) -> dict | None:
    """Merge priority: reviewed_data > (extracted + enriched merged) > extracted"""
    if self.reviewed_data:
        return self.reviewed_data          # Human-edited luôn thắng
    if self.extracted_data and self.enriched_data:
        merged = dict(self.extracted_data)
        merged.update(self.enriched_data)  # LLM fields merge ON TOP nhưng không overwrite
        return merged
    return self.reviewed_data or self.extracted_data
```

**Nguyên tắc:** `enriched_data` chỉ chứa `{"danh_sach_cnch": [...]}`. Stage 1 `extracted_data` chứa tất cả fields còn lại. Hai set này không overlap → không bao giờ ghi đè lẫn nhau.

### 5.7 Persistence — JobManager

**`persist_stage1_result(job, result, llm_model, processing_time_ms)`**
- Ghi `job.extracted_data = result.output.model_dump()` — **canonical nested JSON, 7 top-level keys, không có flat key nào**
- Set `job.status = EXTRACTED`
- Set `job.enrichment_status = PENDING` nếu `result.chi_tiet_cnch` không rỗng, else `SKIPPED`
- **Không đụng vào** `enriched_data`
- **Lưu ý (Plan A):** `flatten_block_output()` **không được gọi** tại đây. Flattening chỉ diễn ra in-memory trong `AggregationService.aggregate()` khi chuẩn bị context cho Word export. `extracted_data` luôn giữ nguyên dạng nested canonical.

**`persist_enrichment_result(job_id, enriched_cnch, error)`** (thực thi bởi `enrich_job_task`)
- Ghi `job.enriched_data = {"danh_sach_cnch": [...]}`
- Set `job.enrichment_status = ENRICHED | FAILED | SKIPPED`
- **Tuyệt đối không đụng vào** `job.extracted_data`

### 5.8 Counters & Timers thêm trong v4

| Metric | Loại | Mô tả |
|---|---|---|
| `llm_calls` | counter | Mỗi lần `_llm_enrich_cnch` được invoke |
| `cnch_llm_extracted` | counter | LLM trả về items > 0 |
| `cnch_llm_fallback` | counter | LLM call ném exception, dùng regex kết quả |
| `stage_narrative_arrays` | timer | Toàn bộ thời gian Stage 1 narrative arrays |

### 5.9 Enrichment settlement gate — Aggregation consistency

> **Vấn đề gốc:** Enrichment là *eventual mutation system* — LLM mutate state document một cách async, nondeterministic, retryable. Nếu aggregate chạy khi job A enriched còn job B chưa, report tuần sẽ inconsistent: một số vụ CNCH có 8 fields đầy đủ, số khác chỉ có regex skeleton.

**Giải pháp — 3 điểm fix đồng thời trong `AggregationService.aggregate()`:**

**1. Settlement gate (block aggregation khi enrichment chưa xong):**

```python
unsettled = [j for j in jobs
             if j.enrichment_status in (EnrichmentStatus.PENDING, EnrichmentStatus.RUNNING)]
if unsettled:
    raise ProcessingError(
        f"{len(unsettled)} job(s) still have enrichment in-flight. "
        "Wait for enrichment to settle before aggregating."
    )
```

Trạng thái settled = `ENRICHED | FAILED | SKIPPED | None(legacy)`. Chỉ cần enrichment dừng lại (dù thành công hay thất bại) thì mới cho aggregate.

**2. Dùng `final_data` thay vì `extracted_data` trực tiếp:**

```python
# Trước (sai — bỏ qua enriched_data hoàn toàn):
row = rd or job.extracted_data

# Sau (đúng — merge theo priority chain):
row = job.final_data   # reviewed > (extracted+enriched) > extracted
```

**3. Per-job enrichment audit trail ghi vào `_metadata`:**

```json
"_metadata": {
  "enrichment_summary": {
    "stage1+stage2": 5,   // ← 5 jobs được LLM enrich đầy đủ
    "stage1_only":   2,   // ← 2 jobs enrichment FAILED, dùng regex
    "reviewed":      0
  },
  "enrichment_partial": false,  // true nếu mix giữa stage1+stage2 và stage1_only
  "enrichment_audit": [
    {"job_id": "abc12345", "enrichment_status": "enriched",  "data_source": "stage1+stage2"},
    {"job_id": "def67890", "enrichment_status": "failed",    "data_source": "stage1_only"},
    ...
  ]
}
```

`enrichment_partial: true` là warning flag — report vẫn được tạo (vì `FAILED` đã settled) nhưng UI có thể hiện cảnh báo "một số vụ CNCH có thể thiếu thông tin chi tiết".

**Kết quả sau fix — các trường hợp xử lý:**

| Trạng thái enrichment lúc aggregate | Hành vi |
|---|---|
| Tất cả `ENRICHED` | Aggregate bình thường, `enrichment_partial=false` |
| Mix `ENRICHED` + `FAILED` | Aggregate bình thường, `enrichment_partial=true`, audit trail đầy đủ |
| Tất cả `FAILED` | Aggregate bình thường, dùng Stage 1 regex data, `enrichment_partial=false` |
| Tất cả `SKIPPED` | Aggregate bình thường (không có CNCH text), `enrichment_partial=false` |
| Bất kỳ job nào `PENDING` hoặc `RUNNING` | **Raise ProcessingError** — yêu cầu caller đợi |

### 5.10 Acceptance criteria (cập nhật)

| Yêu cầu | Cách đáp ứng |
|---|---|
| Document dùng được khi Ollama tắt | `extracted_data` luôn được ghi trong Stage 1 |
| Report không bao giờ inconsistent | Settlement gate block aggregate khi enrichment in-flight |
| Audit trail cho mỗi report | `_metadata.enrichment_audit` ghi nguồn data từng job |
| Throughput không bị ảnh hưởng khi LLM chậm | Stage 1 worker trả về ngay; enrichment pool riêng |
| LLM = optimization layer | `FAILED` settled → aggregate dùng Stage 1 data, `enrichment_partial=true` |

### 5.11 Ghi chú kiến trúc — Two-field vs Single state machine

**Thiết kế hiện tại (two-field model)** được chọn vì lý do bảo thủ: không đụng vào `status` enum hiện tại, tránh break tất cả filter query (`WHERE status='extracted'`) và API response schema. Tuy nhiên nó tạo ra trade-off rõ ràng.

**Thiết kế thay thế (single linear state machine)** sẽ sạch hơn:

```
UPLOAD → EXTRACTED → ENRICHMENT_PENDING
              ↓ (async)
         ENRICHED | ENRICH_FAILED | ENRICH_SKIPPED   (== SETTLED)
              ↓
         READY_FOR_REVIEW
              ↓              ↓
          APPROVED       REJECTED
              ↓
          AGGREGATED
              ↓
          EXPORTED
```

| Tiêu chí | Two-field (v4 hiện tại) | Single state machine |
|---|---|---|
| Query "job sẵn sàng review?" | `status='extracted' AND enrichment_status NOT IN ('pending','running')` | `status='ready_for_review'` |
| Settlement gate trong aggregate() | Manual check `enrichment_status` | `status NOT IN ('enrichment_pending', 'running')` |
| Cross-reference trong UI | Phải đọc 2 field | 1 field |
| Backward compat hybrid mode | `enrichment_status` = NULL → transparent | Hybrid tự chuyển `EXTRACTED → ENRICH_SKIPPED → READY_FOR_REVIEW` |
| `AGGREGATED` / `EXPORTED` tracking | Không có | Explicit, queryable |
| Chi phí refactor | Đã done | Phải đổi enum + tất cả filter query + migration |

**Nếu muốn migrate lên single state machine:** đổi `ExtractionJobStatus` enum, cập nhật tất cả `WHERE status=...` query trong `job_service.py` / `aggregation_service.py` / API endpoints / tests, sau đó xóa `enrichment_status` column (hoặc giữ để backward compat query).

---

## 6. Bước 2: Rây lọc & Ép kiểu (Validation Layer)

**File:** `app/services/data_validator.py`

> **Lưu ý kiến trúc hiện tại:** Hybrid pipeline mặc định đang ép output bằng Pydantic + RuleEngine.
> `DataValidator` vẫn là lớp chuẩn hóa quan trọng cho flow schema-driven/legacy và có thể tái sử dụng ở tầng review.

### 5.1 Class DataValidator

```python
validator = DataValidator(schema_definition)
clean_data, report = validator.validate(raw_llm_output)
```

### 5.2 Ép kiểu (Type Coercion)

#### Số (Number)

| Input (LLM trả về) | Output (sau validate) | Ghi chú |
|---|---|---|
| `"Hai vụ"` | `2` | Vietnamese text → number |
| `"1,500,000"` | `1500000` | US thousand separator |
| `"1.500.000"` | `1500000` | VN/EU thousand separator |
| `"1.500.000,50"` | `1500000.5` | VN decimal format |
| `"12.5%"` | `12.5` | Percentage |
| `"500 VNĐ"` | `500` | Strip currency suffix |
| `"một"` | `1` | Vietnamese word |
| `"triệu"` | `1000000` | Vietnamese word |
| `15` | `15` | Already correct, no change |

**Supported Vietnamese number words:** không(0), một(1), hai(2), ba(3), bốn(4), năm(5), sáu(6), bảy(7), tám(8), chín(9), mười(10), hai mươi(20)...chín mươi(90), trăm(100), nghìn/ngàn(1000), triệu(1M), tỷ(1B)

#### Boolean

| Input | Output |
|---|---|
| `"đúng"`, `"có"`, `"rồi"`, `"x"`, `"✓"`, `"true"`, `"yes"`, `"1"` | `true` |
| `"sai"`, `"không"`, `"chưa"`, `"false"`, `"no"`, `"0"` | `false` |

#### Ngày tháng (Date Normalization)

Tất cả → chuẩn **DD/MM/YYYY**:

| Input | Output |
|---|---|
| `"02-03-2026"` | `"02/03/2026"` |
| `"2026-03-02"` (ISO) | `"02/03/2026"` |
| `"02.03.2026"` | `"02/03/2026"` |
| `"ngày 2 tháng 3 năm 2026"` | `"02/03/2026"` |

**Auto-detect date fields:** Nhận diện field là ngày bằng tên: `ngay_*`, `date_*`, `thoi_gian`, `tu_ngay`, `den_ngay`, `ky_bao_cao`, `period`...

### 5.3 Array-of-Object Validation

Mỗi phần tử trong mảng được coerce riêng theo sub-field type:

```json
// Input (LLM trả ra):
{"danh_sach": [{"loai": "Cháy", "so_nguoi": "ba"}, {"loai": "Nổ", "so_nguoi": "5 người"}]}

// Output (sau validate):
{"danh_sach": [{"loai": "Cháy", "so_nguoi": 3}, {"loai": "Nổ", "so_nguoi": 5}]}
```

### 5.4 Validation Report

```json
{
  "is_valid": true,
  "total_fields": 6,
  "valid_fields": 5,
  "completeness_pct": 83.3,
  "warnings": [],
  "auto_corrections": [
    {
      "field": "so_vu",
      "original": "Hai vụ",
      "coerced": 2,
      "note": "\"Hai vụ\" → 2 (Vietnamese text)"
    },
    {
      "field": "ngay_bao_cao",
      "original": "02-03-2026",
      "coerced": "02/03/2026",
      "note": "\"02-03-2026\" → \"02/03/2026\""
    }
  ],
  "missing_fields": ["dia_chi_cu_the"],
  "extra_fields": ["ghi_chu_them"]
}
```

Report được lưu vào `confidence_scores._validation_report` trong `extraction_jobs`.

### 5.5 Vị trí trong Pipeline

```python
# extraction_service.py → run_extraction() → step 5.5
from app.services.data_validator import DataValidator

validator = DataValidator(template.schema_definition)
clean_data, validation_report = validator.validate(result["extracted_data"])

# Store VALIDATED data (NOT raw LLM output)
job.extracted_data = clean_data
job.confidence_scores["_validation_report"] = validation_report
```

---

## 7. Bước 3: Xào nấu dữ liệu (Aggregation & Map-Reduce)

**File:** `app/services/aggregation_service.py`

### 6.1 Flow

```
N approved jobs → load final_data → pd.json_normalize() → apply rules → AggregationReport
```

### 6.2 Aggregation Methods

| Method | Mô tả | Ví dụ |
|---|---|---|
| `SUM` | Cộng tổng | `so_vu` ngày 1 + ngày 2 + ngày 3 |
| `AVG` | Trung bình | `nhiet_do` trung bình tuần |
| `MAX` | Giá trị lớn nhất | `so_nguoi` cao nhất |
| `MIN` | Giá trị nhỏ nhất | `nhiet_do` thấp nhất |
| `COUNT` | Đếm số bản ghi | Tổng số báo cáo |
| `CONCAT` | Nối mảng | Gộp `danh_sach_su_co` 7 ngày → 1 list |
| `LAST` | Lấy giá trị cuối | `ten_nguoi_ky` lấy bản ghi cuối |

### 6.3 Aggregation Rules Format

```json
{
  "rules": [
    {"output_field": "tong_so_vu", "source_field": "so_vu", "method": "SUM", "label": "Tổng số vụ"},
    {"output_field": "tb_nhiet_do", "source_field": "nhiet_do", "method": "AVG", "round_digits": 1, "label": "Nhiệt độ TB"},
    {"output_field": "tat_ca_su_co", "source_field": "danh_sach_su_co", "method": "CONCAT", "label": "Tổng hợp sự cố"},
    {"output_field": "nguoi_ky", "source_field": "ten_nguoi_ky", "method": "LAST", "label": "Người ký"}
  ],
  "sort_by": "ngay_bao_cao",
  "group_by": null
}
```

### 6.4 Output Structure

```json
{
  "tong_so_vu": 45,
  "tb_nhiet_do": 32.5,
  "tat_ca_su_co": [{"loai": "Cháy", ...}, {"loai": "Nổ", ...}, ...],
  "nguoi_ky": "Nguyễn Văn A",
  "records": [/* summary record phục vụ Word render */],
  "_source_records": [/* raw data từ từng job */],
  "_flat_records": [/* pd.json_normalize flattened */],
  "_metadata": {
    "total_jobs": 7,
    "total_data_rows": 7,
    "generated_at": "2026-03-10T08:00:00",
    "template_name": "Báo cáo PCCC",
    "template_version": 3
  }
}
```

### 6.5 Pandas json_normalize

Nested JSON được đập phẳng tự động:

```python
# Input:
[{"a": 1, "detail": {"x": 10, "y": 20}}, ...]

# pd.json_normalize output:
#   a  detail_x  detail_y
#   1       10        20
```

Kết quả lưu trong `_flat_records` để export dễ dàng.

### 6.6 Export Formats

| Format | Class/Method | Mô tả |
|---|---|---|
| **Excel** | `ExportService.to_excel()` | 3 sheets: Summary, Detail, Metadata |
| **CSV** | `ExportService.to_csv()` | Field/Value format |
| **JSON** | Direct return | Raw aggregated_data |
| **Word** | `build_word_export_context()` + `render_word_template()` | Xem Bước 4 |

---

## 8. Bước 4: Bơm khuôn Word (Headless Document Export)

**File:** `app/services/word_export.py`  
**Thư viện:** `docxtpl` (Jinja2 for .docx)

### 7.1 Flow

```
Word Template (.docx với {{...}})  +  Aggregated JSON  →  docxtpl render  →  File .docx hoàn chỉnh
```

Render context hiện được build ở tầng aggregation qua `build_word_export_context(...)` rồi mới truyền vào renderer.

### 7.2 Cú pháp Template

#### Biến đơn giản

```
Đơn vị báo cáo: {{ten_don_vi}}
Ngày: {{today}}
Tổng số vụ: {{tong_so_vu}}
```

#### Custom Filters

| Filter | Input | Output |
|---|---|---|
| `{{val \| number_vn}}` | `1500000` | `1.500.000` |
| `{{val \| date_vn}}` | `"02/03/2026"` | `"ngày 02 tháng 03 năm 2026"` |
| `{{val \| date_short}}` | `"2026-03-02"` | `"02/03/2026"` |
| `{{val \| default_if_none("N/A")}}` | `None` | `"N/A"` |

#### Loop bảng (trong Word Table)

```
Hàng 1: {% for row in records %}
Hàng 2: {{row.loai_su_co}}  |  {{row.so_nguoi}}  |  {{row.ngay_xay_ra}}
Hàng 3: {% endfor %}
```

#### Điều kiện

```
{% if tong_so_vu > 0 %}Có {{tong_so_vu}} sự cố{% else %}Không có sự cố{% endif %}
```

### 7.3 Biến tự động inject

| Biến | Giá trị | Ghi chú |
|---|---|---|
| `{{today}}` | `"10/03/2026"` | Ngày hiện tại DD/MM/YYYY |
| `{{now}}` | `"10/03/2026 08:30"` | Ngày giờ hiện tại |
| `{{metadata}}` | object | Di chuyển từ `_metadata` lên top-level |
| `{{metadata.template_name}}` | string | Tên template |
| `{{report_name}}` | string | Tên report |
| `{{total_jobs}}` | int | Số job đã aggregate |
| `{{approved_jobs}}` | int | Số job approved |

### 7.4 Hardening & Production safety

- Anti zip-bomb trước khi parse docx:
  - `MAX_TEMPLATE_INPUT_BYTES = 50MB`
  - `MAX_DOCX_MEMBER_UNCOMPRESSED_BYTES = 50MB`
  - `MAX_DOCX_TOTAL_UNCOMPRESSED_BYTES = 120MB`
  - `MAX_DOCX_ENTRIES = 2000`
  - `MAX_DOCX_COMPRESSION_RATIO = 150`
- Tiền xử lý Jinja tag bằng XML parser (`ElementTree`) thay vì regex-only trên raw XML.
- Lỗi render/template được chain nguyên nhân bằng `raise ... from e` để giữ traceback.

**NOTE triển khai:** các giới hạn anti zip-bomb này **không có sẵn** trong `docxtpl`/`python-docx`. Cần có lớp interceptor dùng `zipfile` để duyệt entry và kiểm tra `file_size` (uncompressed), tổng dung lượng giải nén và tỉ lệ nén trước khi chuyển bytes sang `DocxTemplate`.

### 7.5 API Usage

```bash
# Upload .docx template + render với report data
curl -X POST "http://localhost:8000/api/v1/extraction/aggregate/{report_id}/export-word" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -F "file=@bao_cao_mau.docx" \
  --output report_final.docx
```

---

## 9. Database Schema

### 8.1 extraction_templates

```sql
CREATE TABLE extraction_templates (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name            VARCHAR(255) NOT NULL,
    description     TEXT,
    schema_definition  JSONB NOT NULL,          -- Định nghĩa fields
    aggregation_rules  JSONB DEFAULT '{}',       -- Rules tổng hợp
    version         INTEGER DEFAULT 1,           -- Auto-bump khi schema thay đổi
    is_active       BOOLEAN DEFAULT TRUE,
    created_by      UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_extraction_templates_schema_gin ON extraction_templates USING GIN (schema_definition);
```

### 9.2 extraction_jobs

```sql
CREATE TABLE extraction_jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    template_id     UUID NOT NULL REFERENCES extraction_templates(id) ON DELETE CASCADE,
    document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    batch_id        UUID,                        -- Nhóm batch
    extraction_mode VARCHAR(20) DEFAULT 'standard' NOT NULL,  -- standard|vision|fast|block

    -- State machine: pending → processing → extracted → approved
    --                                      ↘ failed     ↘ rejected
    status          VARCHAR(20) DEFAULT 'pending' NOT NULL,

    -- Stage 1 — AI output (deterministic, không có LLM trong block mode)
    extracted_data     JSONB,
    confidence_scores  JSONB,                    -- Bao gồm _validation_report
    source_references  JSONB,
    debug_traces       JSONB,

    -- Stage 2 — LLM enrichment (async, độc lập với Stage 1)
    -- enriched_data KHÔNG BAO GIỜ overwrite extracted_data
    -- final_data property merge: reviewed > (extracted+enriched) > extracted
    enrichment_status    VARCHAR(20),            -- pending|running|enriched|failed|skipped|NULL(legacy)
    enriched_data        JSONB,                  -- {"danh_sach_cnch": [...]} — chỉ chứa LLM-filled fields
    enrichment_error     TEXT,
    enrichment_started_at   TIMESTAMP,
    enrichment_completed_at TIMESTAMP,

    -- Human review
    reviewed_data   JSONB,
    reviewed_by     UUID REFERENCES users(id) ON DELETE SET NULL,
    reviewed_at     TIMESTAMP,
    review_notes    TEXT,

    -- Processing metadata
    parser_used        VARCHAR(50),              -- pdfplumber|none
    llm_model          VARCHAR(100),
    llm_tokens_used    INTEGER DEFAULT 0,
    processing_time_ms INTEGER,
    error_message      TEXT,
    retry_count        INTEGER DEFAULT 0,

    created_by      UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW(),
    completed_at    TIMESTAMP
);

CREATE INDEX idx_extraction_jobs_extracted_data_gin ON extraction_jobs USING GIN (extracted_data);
CREATE INDEX idx_extraction_jobs_reviewed_data_gin  ON extraction_jobs USING GIN (reviewed_data);
-- Index cho enrichment worker polling
CREATE INDEX idx_extraction_jobs_enrichment_status
    ON extraction_jobs (enrichment_status)
    WHERE enrichment_status IS NOT NULL;
```

**Migration cho DB cũ (chạy một lần):**
```bash
python scripts/migrate_add_enrichment_columns.py
```

Script idempotent (`ADD COLUMN IF NOT EXISTS`). Xem `scripts/migrate_add_enrichment_columns.py`.

### 8.3 aggregation_reports

```sql
CREATE TABLE aggregation_reports (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    template_id     UUID NOT NULL REFERENCES extraction_templates(id) ON DELETE CASCADE,
    name            VARCHAR(255) NOT NULL,
    description     TEXT,
    job_ids         UUID[] NOT NULL,             -- Array of job UUIDs
    aggregated_data JSONB NOT NULL,              -- Kết quả tổng hợp
    total_jobs      INTEGER NOT NULL,
    approved_jobs   INTEGER NOT NULL,
    status          VARCHAR(20) DEFAULT 'draft', -- draft|finalized
    created_by      UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at      TIMESTAMP DEFAULT NOW(),
    finalized_at    TIMESTAMP
);
```

  ```sql
  -- Optional (chỉ bật khi có nghiệp vụ query/filter trực tiếp trên aggregated_data)
  -- CREATE INDEX idx_aggregation_reports_data_gin ON aggregation_reports USING GIN (aggregated_data);
  ```

### 9.4 Job State Machine

> **Thiết kế hiện tại (v4): two-field model.**
> `job.status` = trạng thái chính của job lifecycle.
> `job.enrichment_status` = trạng thái riêng của LLM enrichment (block mode only).
>
> **Trade-off so với single state machine:**
> Two-field giữ backward compat với hybrid mode và tránh đổi tất cả query filter hiện tại. Nhược điểm: UI và aggregate gate phải cross-reference 2 field để biết job "sẵn sàng review" chưa. Xem thảo luận kiến trúc tại Section 5.11.

**`job.status` — main lifecycle:**

```
          create_job()
              │
              ▼
        ┌──────────┐
        │ PENDING  │
        └────┬─────┘
             │ Celery picks up
             ▼
        ┌──────────────┐
        │  PROCESSING  │
        └──┬───────┬───┘
           │       │
     success│     error│
           ▼       ▼
    ┌───────────┐ ┌────────┐
    │ EXTRACTED │ │ FAILED │◄──── retry_job() resets to PENDING
    └──┬─────┬──┘ └────────┘     (retry_count++)
       │     │
       │     │  [Block mode: enrichment chạy async — xem job.enrichment_status]
       │     │  [Hybrid mode: không có enrichment, có thể approve ngay]
       │     │
 approve│   reject│
       ▼     ▼
 ┌──────────┐ ┌──────────┐
 │ APPROVED │ │ REJECTED │◄──── retry_job() resets to PENDING
 └──────────┘ └──────────┘
       │
       │ aggregate()
       │ [gate: tất cả enrichment_status phải settled trước khi aggregate]
       ▼
 ┌─────────────────────┐
 │ AggregationReport   │
 │ (draft → finalized) │
 └─────────────────────┘
```

**`job.enrichment_status` — block mode enrichment lifecycle:**

```
  (Stage 1 complete, chi_tiet_cnch có text)   →  PENDING
  (Stage 1 complete, chi_tiet_cnch rỗng)      →  SKIPPED
  (hybrid/non-block mode)                      →  SKIPPED
  enrich_job_task picked up                   →  RUNNING
  LLM call thành công, items > 0              →  ENRICHED
  LLM call thành công, items = []             →  SKIPPED
  LLM call thất bại (sau max 3 retries)       →  FAILED   ← job vẫn EXTRACTED, dùng được
  NULL                                         →  legacy job (pre-v4, không có enrichment)
```

**"Job sẵn sàng cho review" = điều kiện:**
```python
job.status == "extracted"
AND job.enrichment_status NOT IN ("pending", "running")
# (hoặc enrichment_status IS NULL cho legacy jobs)
```

**Enrichment settlement = điều kiện cho phép aggregate:**
```python
# Tất cả jobs phải thỏa:
job.enrichment_status NOT IN ("pending", "running")
# ENRICHED | FAILED | SKIPPED | NULL đều là "settled"
```

---

## 10. API Reference — 25 Endpoints

**Router prefix:** `/api/v1/extraction`  
**Tags:** `Extraction Templates`, `Extraction Jobs`, `Extraction Reports`

### 10.1 Word Scanner

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/templates/scan-word` | `get_current_user` | Upload .docx → auto-infer schema |

**Request:** `multipart/form-data` — `file` (.docx) + `use_llm` (bool, default true)  
**Response 200:**
```json
{
  "variables": [{"name": "so_vu", "type": "number", "description": "...", "occurrences": 3}],
  "schema_definition": {"fields": [...]},
  "aggregation_rules": {"rules": [...]},
  "stats": {"unique_variables": 12, "tables_scanned": 3, "array_with_object_schema": 2}
}
```

### 10.2 Templates CRUD

| Method | Path | Auth | Status | Description |
|---|---|---|---|---|
| `POST` | `/templates` | `require_admin` | 201 | Tạo template mới |
| `GET` | `/templates` | `require_viewer` | 200 | List templates (paginated) |
| `GET` | `/templates/{template_id}` | `require_viewer` | 200 | Chi tiết template |
| `PATCH` | `/templates/{template_id}` | `require_admin` | 200 | Sửa template (schema change → version++) |
| `DELETE` | `/templates/{template_id}` | `RoleChecker("owner")` | 204 | Soft delete |

### 10.3 Jobs

| Method | Path | Auth | Status | Description |
|---|---|---|---|---|
| `POST` | `/jobs` | `require_admin` | 202 | Upload 1 PDF + tạo job → Celery |
| `POST` | `/jobs/batch` | `require_admin` | 202 | Upload N PDFs (max 20) → N Celery jobs phân tán |
| `POST` | `/jobs/batch-block` | `require_admin` | 200 | Batch block-mode in-process parallel (ThreadPoolExecutor) |
| `POST` | `/jobs/from-document` | `require_admin` | 202 | Tạo job từ document đã upload |
| `GET` | `/jobs` | `require_viewer` | 200 | List jobs (filter: status, template_id, batch_id) |
| `GET` | `/jobs/{job_id}` | `require_viewer` | 200 | Polling endpoint |
| `GET` | `/jobs/batch/{batch_id}/status` | `require_viewer` | 200 | Batch progress |
| `GET` | `/metrics` | `require_viewer` | 200 | Global pipeline extraction metrics (counters + timers) |
| `POST` | `/jobs/{job_id}/retry` | `require_admin` | 200 | Retry failed/rejected |
| `DELETE` | `/jobs/{job_id}` | `require_admin` | 204 | Xóa job đã hoàn tất |

### 10.4 Review

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/review/{job_id}/approve` | `require_admin` | Approve (+ optional `reviewed_data`) |
| `POST` | `/review/{job_id}/reject` | `require_admin` | Reject (required `notes`) |

### 10.5 Aggregation & Export

| Method | Path | Auth | Status | Description |
|---|---|---|---|---|
| `POST` | `/aggregate` | `require_admin` | 201 | Gom N jobs → 1 report |
| `GET` | `/aggregate` | `require_viewer` | 200 | List reports |
| `GET` | `/aggregate/{report_id}` | `require_viewer` | 200 | Chi tiết report |
| `DELETE` | `/aggregate/{report_id}` | `require_admin` | 204 | Xóa report |
| `GET` | `/aggregate/{report_id}/export` | `require_viewer` | 200 | Export Excel/CSV/JSON (query: `?format=excel`) |
| `POST` | `/aggregate/{report_id}/export-word` | `require_viewer` | 200 | Upload .docx template → render → download |
| `GET` | `/aggregate/{report_id}/export-word-auto` | `require_viewer` | 200 | Dùng template đã lưu trong S3 để render |

### 10.6 Sheet Ingestion

| Method | Path | Auth | Status | Description |
|---|---|---|---|---|
| `POST` | `/jobs/ingest/google-sheet` | `require_admin` | 202 | Ingest rows từ Google Sheets → extraction_jobs (deterministic, idempotent) |
| `GET` | `/sheets/inspect/by-date` | `require_viewer` | 200 | Per-day job counts & STT coverage grid cho sheet inspection |
| `GET` | `/sheets/inspect/issues` | `require_viewer` | 200 | Missing/zero/mismatch STT fields so sánh Excel vs extracted |
| `GET` | `/sheets/inspect/mapping` | `require_viewer` | 200 | Column → STT mapping table từ sheet_mapping.yaml |
| `GET` | `/sheets/names` | `require_viewer` | 200 | List sheet names từ Excel file trong MinIO |

**Sheet ingestion request body:**
```json
{
  "template_id": "uuid",
  "sheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
  "worksheet": "BC NGÀY",
  "schema_path": "/path/to/schema.yaml",
  "source_document_id": "uuid-optional",
  "range_a1": "A1:ZZ1000-optional"
}
```

**Sheet ingestion response:**
```json
{
  "status": "ok",
  "sheet_id": "...",
  "worksheet": "...",
  "rows_processed": 150,
  "rows_inserted": 148,
  "rows_failed": 2,
  "rows_skipped_idempotent": 0,
  "schema_match_rate": 0.9234,
  "validation_error_rate": 0.0133,
  "errors": [...],
  "metrics": {
    "ingestion_run_id": "uuid",
    "row_status_counts": {
      "VALID": 140,
      "INVALID": 2,
      "PARTIAL": 6,
      "DUPLICATE": 0,
      "SKIPPED": 2
    }
  }
}
```

---

## 11. Cấu hình (Configuration)

**File:** `app/core/config.py` → class `Settings`

| Setting | Type | Default | Env Override | Mô tả |
|---|---|---|---|---|
| `OLLAMA_BASE_URL` | str | `"http://localhost:11434"` | `OLLAMA_BASE_URL` | Endpoint Ollama server |
| `OLLAMA_API_KEY` | str | `"ollama"` | `OLLAMA_API_KEY` | API key (placeholder cho local Ollama) |
| `OLLAMA_MODEL` | str | `"qwen2.5:7b"` | `OLLAMA_MODEL` | Model dùng cho Hybrid pipeline |
| `GEMINI_API_KEY` | str | `""` | `GEMINI_API_KEY` | Dùng cho module khác (Engine 1/optional) |
| `GEMINI_FLASH_MODEL` | str | `"gemini-2.5-flash"` | `GEMINI_FLASH_MODEL` | Cấu hình tương thích legacy |
| `GEMINI_PRO_MODEL` | str | `"gemini-2.5-flash"` | `GEMINI_PRO_MODEL` | Cấu hình tương thích legacy |
| `EXTRACTION_MAX_TOKENS` | int | `65536` | — | Giới hạn token cho flow extraction legacy |
| `EXTRACTION_TEMPERATURE` | float | `0.0` | — | Temperature (deterministic) |
| `DEFAULT_EXTRACTION_MODE` | str | `"standard"` | — | Mode mặc định của API |
| `EXTRACTION_MAX_RETRIES` | int | `3` | — | Celery retry tối đa |
| `EXTRACTION_TIMEOUT_MINUTES` | int | `30` | — | Timeout cho stuck jobs |
| `EXTRACTION_BATCH_MAX_FILES` | int | `20` | — | Max files/batch |
| `HYBRID_MAX_RETRIES` | int | `3` | `HYBRID_MAX_RETRIES` | Retry logic-level trong Hybrid pipeline |
| `HYBRID_MANUAL_REVIEW_DIR` | str | `"Needs_Manual_Review"` | `HYBRID_MANUAL_REVIEW_DIR` | Nơi lưu metadata file cần xử lý tay |
| `CONFIDENCE_HIGH` | float | `0.85` | — | Ngưỡng confidence cao cho UI |
| `CONFIDENCE_MEDIUM` | float | `0.50` | — | Ngưỡng confidence trung bình cho UI |

**Docker Compose defaults (tham khảo):**
```yaml
environment:
  OLLAMA_BASE_URL: ${OLLAMA_BASE_URL:-http://localhost:11434}
  OLLAMA_MODEL: ${OLLAMA_MODEL:-qwen2.5:7b}
```

---

## 12. Celery Workers & Background Tasks

**File:** `app/infrastructure/worker/extraction_tasks.py`

### 12.1 extract_document_task

```python
@shared_task(
    bind=True,
    max_retries=3,
    soft_time_limit=600,
    time_limit=720,
)
def extract_document_task(self, job_id: str):
    """Pipeline: load job → S3 download → orchestrator.run() → persist."""
```

- **Queue:** `extraction` | **Concurrency:** 4 | **Prefetch:** 1
- **Block mode:** gọi `run_stage1_from_bytes()` → `persist_stage1_result()` → dispatch `enrich_job_task`
- **Non-block mode:** gọi `run_from_bytes()` → `persist_pipeline_result()` (unchanged)
- **Retry:** Exponential backoff (30s → 60s → 120s + jitter), max 3 lần, chỉ retry transient errors
- **Failure:** Sau max retries → `status = failed`, `error_message` ghi lại

### 12.2 enrich_job_task *(v4 mới)*

**File:** `app/infrastructure/worker/enrichment_tasks.py`

```python
@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=180,
    time_limit=240,
    queue="enrichment",
)
def enrich_job_task(self, job_id: str):
    """Stage 2: đọc chi_tiet_cnch → gọi LLM → ghi enriched_data."""
```

- **Queue:** `enrichment` | **Concurrency:** 2 | **Soft time limit:** 180s
- Chỉ retry khi transient error (timeout, connection reset). Validation error / empty text → không retry
- Luôn safe-fail: nếu lỗi sau max retries, `enrichment_status = FAILED`, `extracted_data` không bị ảnh hưởng
- Guard: skip nếu `enrichment_status NOT IN (PENDING, FAILED)` — idempotent

### 12.3 cleanup_stuck_jobs

```python
@shared_task(name="cleanup_stuck_extraction_jobs")
def cleanup_stuck_jobs():
    """Periodic: tìm jobs stuck ở 'processing' > 30 phút → mark 'failed'."""
```

- Chạy bởi **Celery Beat** mỗi 30 phút
- Timeout: `settings.EXTRACTION_TIMEOUT_MINUTES` (default 30 phút)

### 12.4 Celery queue routing

```python
task_routes = {
    "app.infrastructure.worker.tasks.process_document_task":       {"queue": "document_processing"},
    "app.infrastructure.worker.tasks.generate_embeddings_task":    {"queue": "embeddings"},
    "app.infrastructure.worker.extraction_tasks.extract_document_task": {"queue": "extraction"},
    "app.infrastructure.worker.enrichment_tasks.enrich_job_task":  {"queue": "enrichment"},
}
```

### 12.5 Docker Compose — Worker services

| Service | Queue | Concurrency | Mục đích |
|---|---|---|---|
| `celery-extraction-worker` | `extraction` | 4 | Stage 1 deterministic, tải PDF, parse |
| `celery-enrichment-worker` | `enrichment` | 2 | Stage 2 LLM enrichment (giới hạn song song Ollama) |
| `celery-worker` | `default`, `document_processing`, `embeddings` | 4 | RAG, embeddings, general tasks |
| `celery-beat` | — | — | Scheduler (cleanup tasks) |

---

## 13. Word Template Scanner

**File:** `app/services/word_scanner.py`

### 12.1 Flow

```
.docx upload → Regex scan {{...}} → Type inference → Table structure → (optional) LLM refine → Output
```

### 12.2 Scan Targets

| Vùng | Phương pháp |
|---|---|
| Paragraphs | Regex `{{variable_name}}` |
| Tables (data rows) | Regex + table header analysis |
| Headers/Footers | Regex |

### 12.3 Type Inference

| Keyword patterns | Inferred type |
|---|---|
| `so_*`, `tong_*`, `amount`, `total`, `price`, `qty`, `count` | `number` |
| `danh_sach*`, `list_*`, `bang_*`, `table_*`, `chi_tiet*` | `array` |
| `is_*`, `has_*`, `co_*`, `da_*`, `approved`, `active` | `boolean` |
| Mặc định | `string` |

### 12.4 Table-aware Detection

Khi placeholder nằm TRONG bảng Word:
1. Đọc header row → extract column names
2. Chuyển thành array-of-object schema
3. Infer sub-field types bằng prefix matching (`so_*` → number, `ten_*` → string)
4. (Optional) Gọi Gemini Flash refine types

### 12.5 Aggregation Rules Auto-generate

| Field type | Auto-generated rule |
|---|---|
| `number` | `SUM` |
| `array` | `CONCAT` |

---

## 14. Pydantic Schemas (Request/Response)

**File:** `app/schemas/extraction_schema.py`

### 13.1 Schema Validation

| Model | Mô tả |
|---|---|
| `FieldDefinition` | 1 field: `name` (snake_case), `type` (string\|number\|boolean\|array\|object), `description`, `items` (cho array), `fields` (cho object) |
| `SchemaDefinition` | `{"fields": [FieldDefinition...]}` — requires unique names |
| `AggregationRule` | `output_field`, `source_field`, `method` (SUM\|AVG\|MAX\|MIN\|COUNT\|CONCAT\|LAST), `round_digits` |
| `AggregationRules` | `{"rules": [AggregationRule...], "sort_by": str, "group_by": str}` |

### 13.2 Request Models

| Model | Endpoint | Fields |
|---|---|---|
| `TemplateCreate` | POST /templates | name, description, schema_definition, aggregation_rules |
| `TemplateUpdate` | PATCH /templates/{id} | All optional |
| `JobCreate` | POST /jobs | template_id, mode |
| `JobFromDocumentCreate` | POST /jobs/from-document | document_id, template_id, mode |
| `ReviewApprove` | POST /review/{id}/approve | reviewed_data (optional), notes |
| `ReviewReject` | POST /review/{id}/reject | notes (required) |
| `AggregateRequest` | POST /aggregate | template_id, job_ids, report_name, description |

### 13.3 Response Models

| Model | Fields chính |
|---|---|
| `TemplateResponse` | id, name, schema_definition, aggregation_rules, version, is_active |
| `JobResponse` | id, status, extraction_mode, extracted_data, confidence_scores, reviewed_data, llm_model, processing_time_ms |
| `BatchCreateResponse` | batch_id, total_files, jobs[] |
| `BatchStatusResponse` | total, pending, processing, extracted, approved, failed, progress_percent |
| `AggregateResponse` | id, name, aggregated_data, total_jobs, approved_jobs, status |

---

## 15. Phase 3 — Template-driven · Dynamic Columns · Batch Parallel · Observability

### 14.1 YAML Template System

> **Nguyên tắc: Zero hardcode — mọi regex, keyword, threshold đều nằm trong file YAML.**

**Files:**
- `app/templates/pccc.yaml` — template PCCC (55+ patterns)
- `app/business/template_loader.py` — `DocumentTemplate` wrapper + registry

#### Kiến trúc

```
app/templates/
└── pccc.yaml           ← file YAML chứa toàn bộ pattern nghiệp vụ

app/business/
└── template_loader.py  ← DocumentTemplate (typed wrapper) + load_template() + lru_cache
```

#### DocumentTemplate class

`DocumentTemplate` bọc dict YAML thành typed properties:

```python
tpl = load_template("pccc")

tpl.template_id          # "pccc"
tpl.narrative_start_re   # re.Pattern — compiled regex
tpl.date_long_form_re    # re.Pattern
tpl.date_period_markers  # list[str]
tpl.unit_patterns        # list[str]
tpl.incident_row_patterns_spaced   # list[re.Pattern]
tpl.incident_row_patterns_compact  # list[re.Pattern]
tpl.year_range           # (int, int)
tpl.max_ket_qua          # int
tpl.non_negative_fields  # list[str]
tpl.extraction_prompt("header")    # str — system prompt cho block
# ... 40+ properties tổng cộng
```

#### YAML Structure (pccc.yaml)

```yaml
id: pccc
name: "Báo cáo PCCC ngày"
version: 1

block_detection:
  narrative_start_pattern: "..."
  table_anchor_pattern: "..."

prompts:
  header: "Trích xuất header..."
  phan_nghiep_vu: "..."

header:
  date:
    long_form: "..."
    short_form: "..."
    period_markers: [...]
  report_number:
    primary: "..."
  unit_patterns: [...]

narrative:
  counts:
    tong_so_vu_chay: { pattern: "...", group: 1 }
    # ...
  detail_keywords: [...]

table:
  header_skip_keywords: [...]
  column_detection: { stt: [...], noi_dung: [...], ket_qua: [...] }
  incident_row_patterns: { spaced: [...], compact: [...] }

validation:
  year_range: [2020, 2030]
  max_ket_qua: 10000
  non_negative_fields: [...]
```

#### Consumers

Tất cả module sau đều nhận `tpl: DocumentTemplate | None`:

| Module | Hàm | Trước | Sau |
|---|---|---|---|
| `block_extraction_pipeline.py` | `__init__()` | Hardcode 55+ regex | `self.tpl.*` |
| `extractors.py` | `extract_metadata_from_header()` | Hardcode regex | `tpl.report_number_primary_re` |
| `validators.py` | `validate_business()` | Hardcode constants | `tpl.year_range`, `tpl.max_ket_qua` |
| `engine.py` | `run_business_rules()` | Không có tpl | Truyền `tpl=` xuống tất cả extractors/validators |
| `block_business_workflow.py` | `__init__()` | Không có template | `self.tpl` → pipeline + payload |

### 14.2 Dynamic Column Detection

Thay vì giả định cột cố định `[0]=STT, [1]=Nội dung, [2]=Kết quả`, pipeline parser giờ **quét header row** để xác định column index:

```python
# Trong _parse_bang_thong_ke_from_tables()
for idx, cell in enumerate(header_row):
    upper = cell.upper()
    if any(kw in upper for kw in ["STT", "SỐ TT"]):
        col_stt = idx
    elif any(kw in upper for kw in ["KẾT QUẢ", "SỐ LIỆU", "THỰC HIỆN"]):
        col_kq = idx
    elif any(kw in upper for kw in ["NỘI DUNG", "CHỈ TIÊU"]):
        col_nd = idx
```

Keywords được load từ `tpl.column_detection_keywords("stt" | "noi_dung" | "ket_qua")`.

Khi detect thành công → `metrics.inc("dynamic_col_detected")`.

### 14.3 Batch Parallel Pipeline

**File:** `app/services/batch_extraction.py`

Chạy block pipeline song song trên N PDF files **in-process** (không qua Celery):

```python
from app.services.batch_extraction import BatchItem, run_batch

items = [BatchItem("file1.pdf", bytes1), BatchItem("file2.pdf", bytes2), ...]
result = run_batch(items, max_workers=2)

result.total        # 5
result.succeeded    # 4
result.failed       # 1
result.results      # list[dict] — payload mỗi file
result.errors       # list[{"filename": ..., "error": ...}]
result.metrics      # batch-level counters/timers
```

#### Tính năng

| Tính năng | Mô tả |
|---|---|
| **ThreadPoolExecutor** | Song song N files, mặc định `EXTRACTION_BATCH_MAX_FILES // 2` (cap 4) |
| **Backpressure** | Items vượt `EXTRACTION_BATCH_MAX_FILES` bị reject ngay với error `"backpressure: queue full"` |
| **Per-item metrics** | Mỗi item có `batch_item` timer |
| **Batch counters** | `batch_total`, `batch_succeeded`, `batch_failed` |
| **Directory mode** | `run_batch_from_directory("/path/to/pdfs/")` — quét tất cả `*.pdf` |

#### API Endpoint

```bash
# POST /api/v1/extraction/jobs/batch-block
curl -X POST "http://localhost:8000/api/v1/extraction/jobs/batch-block" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -F "files=@file1.pdf" \
  -F "files=@file2.pdf" \
  -F "max_workers=2"

# Response 200:
{
  "total": 2, "succeeded": 2, "failed": 0,
  "results": [{...}, {...}],
  "errors": [],
  "metrics": {"counters": {"batch_total": 2, ...}, "timers_ms": {...}}
}
```

### 14.4 Observability Metrics

**File:** `app/core/metrics.py`

#### PipelineMetrics (per-run)

Mỗi lần chạy pipeline tạo 1 instance `PipelineMetrics`:

```python
metrics = PipelineMetrics()

metrics.inc("llm_calls")                    # counter += 1
metrics.inc("llm_calls", 3)                 # counter += 3

with metrics.timer("stage1_layout"):        # context manager — tự tính elapsed_ms
    do_layout_stuff()

metrics.to_dict()
# {"counters": {"llm_calls": 4, ...}, "timers_ms": {"stage1_layout": 1234.5, ...}}
```

#### Counters được track

| Counter | Khi nào tăng |
|---|---|
| `llm_calls` | Mỗi lần gọi LLM (extract block) |
| `llm_extract_fallback` | LLM trả rỗng → dùng fallback |
| `schema_enforcer_reask` | Schema enforcer phải hỏi lại LLM |
| `narrative_fallback` | Regex fallback cho phần nghiệp vụ |
| `dynamic_col_detected` | Dynamic column detection thành công |
| `pipeline_success` | Pipeline kết thúc thành công |
| `pipeline_failure` | Pipeline kết thúc thất bại |

#### Timers được track

| Timer | Đo cái gì |
|---|---|
| `stage1_layout` | PDF → reconstructed text + tables |
| `stage2_detect` | Block detection |
| `stage3_extract` | LLM extraction + schema enforcement |
| `stage3_header_llm` | Header LLM call riêng |
| `stage6_business` | Business rules engine |

#### GlobalMetrics (thread-safe aggregator)

```python
from app.core.metrics import global_metrics

# Mỗi pipeline run tự merge vào global:
global_metrics.merge(per_run_metrics)

# API endpoint trả về tổng hợp:
# GET /api/v1/extraction/metrics
global_metrics.to_dict()
# {"counters": {"llm_calls": 150, "pipeline_success": 42, ...}, "timers_ms": {...}}

global_metrics.reset()  # Reset khi cần
```

---

## 16. Cấu trúc Source Code

```
app/
├── api/v1/
│   ├── document.py
│   ├── extraction.py
│   ├── templates.py
│   ├── jobs.py
│   ├── aggregation.py
│   ├── ingestion.py            # ★ Google Sheets ingestion endpoint
│   ├── sheets.py               # ★ Sheet Inspector endpoints (by-date, issues, mapping)
│   ├── rag.py
│   ├── auth.py
│   └── tenant.py
├── application/
│   ├── aggregation_service.py   # flatten_block_output + build_word_export_context
│   ├── auth_service.py
│   ├── doc_service.py
│   ├── extraction_service.py    # Backward-compat facade
│   ├── job_service.py           # ★ JobManager: persist_stage1_result, persist_enrichment_result (v4)
│   ├── review_service.py
│   └── template_service.py
├── core/
│   ├── config.py
│   ├── constants.py
│   ├── exceptions.py
│   ├── logger.py
│   ├── logging.py
│   ├── security.py
│   └── tracing.py
├── domain/
│   ├── models/
│   │   ├── document.py
│   │   ├── extraction_job.py  # ★ ExtractionJob, ExtractionJobStatus, EnrichmentStatus (v4)
│   │   ├── tenant.py
│   │   └── user.py
│   ├── rules/
│   │   ├── engine.py          # run_business_rules() — RuleEngine domain checks
│   │   ├── extractors.py      # Regex-based deterministic extractors (accepts tpl)
│   │   └── normalizers.py     # Vietnamese word spacing + date normalization
│   └── templates/
│       └── template_loader.py # DocumentTemplate wrapper + YAML registry + lru_cache
├── engines/
│   └── extraction/
│       ├── block_pipeline.py      # ★ BlockExtractionPipeline (PDF two-stage)
│       │                          #    - run_stage1_from_bytes() — no LLM (v4)
│       │                          #    - run_from_bytes()        — legacy, full pipeline
│       │                          #    - _llm_enrich_cnch()      — LLM method duy nhất (v4)
│       ├── sheet_pipeline.py      # ★ SheetExtractionPipeline (Google Sheets/Excel → canonical)
│       ├── sheet_ingestion_service.py  # ★ GoogleSheetIngestionService — row-level ingestion with idempotency
│       ├── sources/
│       │   └── sheets_source.py   # ★ GoogleSheetsSource — API client with retry
│       ├── mapping/
│       │   ├── header_detector.py # ★ Header row auto-detection by alias overlap
│       │   ├── mapper.py          # ★ Row-to-schema field mapping with aliases
│       │   ├── normalizer.py      # ★ Value normalization (int/float/bool/date/VN formats)
│       │   └── schema_loader.py   # ★ YAML schema loader for ingestion
│       ├── validation/
│       │   └── row_validator.py   # ★ Pydantic row validation + confidence scoring
│       ├── sheet_job_writer.py    # ★ JobWriter — persist sheet rows with row_hash idempotency
│       ├── extractors.py          # OllamaInstructorExtractor, GeminiExtractor...
│       ├── hybrid_pipeline.py    # HybridExtractionPipeline + PipelineResult (chi_tiet_cnch v4)
│       ├── orchestrator.py        # ★ ExtractionOrchestrator.run() — two-stage dispatch (v4)
│       ├── schemas.py             # BlockExtractionOutput, CNCHItem (8 fields), CNCHListOutput...
│       └── rag/                   # Engine 1 RAG pipeline
├── infrastructure/
│   ├── db/
│   │   └── session.py
│   ├── llm/
│   ├── storage/
│   └── worker/
│       ├── celery_app.py       # ★ Queue routing: extraction + enrichment (v4)
│       ├── enrichment_tasks.py # ★ enrich_job_task — Stage 2 LLM (v4, file mới)
│       ├── extraction_tasks.py # extract_document_task — Stage 1 dispatch
│       └── tasks.py            # RAG + general tasks
├── schemas/
│   ├── auth_schema.py
│   ├── doc_schema.py
│   ├── extraction_schema.py
│   └── rag_schema.py
└── utils/
    ├── debug_trace.py
    ├── file_utils.py
    ├── metrics.py             # ★ PipelineMetrics + GlobalMetrics (thread-safe)
    ├── pdf_utils.py
    ├── word_export.py         # Secure docxtpl renderer (anti zip-bomb)
    └── word_scanner.py        # Word template scanner → auto-generate schema

scripts/
├── migrate_add_enrichment_columns.py  # ★ Idempotent SQL migration cho 5 enrichment columns (v4)
└── ...

app/domain/templates/
└── pccc.yaml                  # YAML extraction template (55+ externalized patterns)

★ = thêm hoặc thay đổi lớn trong v4
```

---

## 17. Ví dụ End-to-End

### Scenario: 7 Báo cáo PCCC Ngày → 1 Báo cáo Tuần Word

#### Step 1: Quét file Word mẫu → tạo Template

```bash
# Upload Word template mẫu có {{so_vu_chay}}, {{ngay_bao_cao}}, bảng {{danh_sach_su_co}}
curl -X POST "http://localhost:8000/api/v1/extraction/templates/scan-word" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@bao_cao_pccc_mau.docx" \
  -F "use_llm=true"

# Response: schema_definition + aggregation_rules (auto-generated)
```

```bash
# Tạo template từ kết quả scan
curl -X POST "http://localhost:8000/api/v1/extraction/templates" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Báo cáo PCCC Ngày",
    "schema_definition": { "fields": [...] },
    "aggregation_rules": { "rules": [...] }
  }'
# → template_id
```

#### Step 2: Upload 7 PDF báo cáo ngày

```bash
curl -X POST "http://localhost:8000/api/v1/extraction/jobs/batch" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -F "template_id=$TEMPLATE_ID" \
  -F "mode=standard" \
  -F "files=@ngay1.pdf" \
  -F "files=@ngay2.pdf" \
  ... \
  -F "files=@ngay7.pdf"
# → batch_id + 7 job_ids
```

#### Step 3: Poll status

```bash
curl "http://localhost:8000/api/v1/extraction/jobs/batch/$BATCH_ID/status" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID"
# → {"total": 7, "extracted": 7, "progress_percent": 100.0}
```

#### Step 4: Review (xem extracted payload + approve)

```bash
# Xem kết quả extraction
curl "http://localhost:8000/api/v1/extraction/jobs/$JOB_ID" ...
# → extracted_data, confidence_scores (status + attempts)

# Approve từng job
curl -X POST "http://localhost:8000/api/v1/extraction/review/$JOB_ID/approve" \
  -d '{"notes": "OK"}' ...
```

#### Step 5: Aggregate (Bước 3)

```bash
curl -X POST "http://localhost:8000/api/v1/extraction/aggregate" \
  -H "Content-Type: application/json" \
  -d '{
    "template_id": "'$TEMPLATE_ID'",
    "job_ids": ["job1", "job2", ..., "job7"],
    "report_name": "PCCC Tuần 10"
  }' ...
# → report_id + aggregated_data (SUM, CONCAT applied)
```

#### Step 6: Export Word (Bước 4)

```bash
# Upload Word template tuần + render
curl -X POST "http://localhost:8000/api/v1/extraction/aggregate/$REPORT_ID/export-word" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -F "file=@bao_cao_tuan_template.docx" \
  --output bao_cao_tuan_10.docx

# → File Word hoàn chỉnh, viền bảng nét căng 100% như bản gốc
```

#### Kết quả

```
📄 bao_cao_tuan_10.docx
├── {{ten_don_vi}}     → "Phòng PCCC Quận 1"
├── {{tong_so_vu}}     → 45 (SUM 7 ngày)
├── {{ngay_bao_cao}}   → "ngày 10 tháng 03 năm 2026"
├── Bảng sự cố         → 45 hàng (CONCAT 7 ngày)
└── {{nguoi_ky}}       → "Đại tá Nguyễn Văn A" (LAST)
```

---

> **Tài liệu này được cập nhật lần cuối: 03/04/2026**  
> **Phiên bản 4.0 — Two-Stage Block Pipeline:** Stage 1 deterministic (no LLM) + Stage 2 LLM enrichment async · EnrichmentStatus state machine · enriched_data column tách biệt · enrich_job_task trên queue riêng · celery-enrichment-worker (concurrency=2) · migrate_add_enrichment_columns.py  
> **Tổng source code Engine 2:** kiến trúc split-router/application/domain · 25 endpoints · 3 bảng DB · 12 JSONB columns (7 gốc + 5 enrichment) · 3 GIN indexes cốt lõi (+1 enrichment_status partial index) · YAML template system · PipelineMetrics + GlobalMetrics · Batch parallel pipeline
