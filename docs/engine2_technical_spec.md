# ⚙️ Engine 2 — Hệ thống Bóc tách Dữ liệu Tự động (AI Data Extraction)

> **Phiên bản:** 2.1.0  
> **Cập nhật:** 19/03/2026  
> **Stack:** FastAPI · SQLAlchemy · Celery · PostgreSQL (JSONB) · Ollama (Instructor + Pydantic) · docxtpl  

---

## Mục lục

1. [Tổng quan](#1-tổng-quan)
2. [Kiến trúc Lưu trữ — PostgreSQL Hybrid](#2-kiến-trúc-lưu-trữ--postgresql-hybrid)
3. [Pipeline 4 Bước Khép Kín](#3-pipeline-4-bước-khép-kín)
4. [Bước 1: Bóc tách thô (Hybrid Extraction)](#4-bước-1-bóc-tách-thô-hybrid-extraction)
5. [Bước 2: Rây lọc & Ép kiểu (Validation Layer)](#5-bước-2-rây-lọc--ép-kiểu-validation-layer)
6. [Bước 3: Xào nấu dữ liệu (Aggregation & Map-Reduce)](#6-bước-3-xào-nấu-dữ-liệu-aggregation--map-reduce)
7. [Bước 4: Bơm khuôn Word (Headless Document Export)](#7-bước-4-bơm-khuôn-word-headless-document-export)
8. [Database Schema](#8-database-schema)
9. [API Reference — 23 Endpoints](#9-api-reference--23-endpoints)
10. [Cấu hình (Configuration)](#10-cấu-hình-configuration)
11. [Celery Workers & Background Tasks](#11-celery-workers--background-tasks)
12. [Word Template Scanner](#12-word-template-scanner)
13. [Pydantic Schemas (Request/Response)](#13-pydantic-schemas-requestresponse)
14. [Cấu trúc Source Code](#14-cấu-trúc-source-code)
15. [Ví dụ End-to-End](#15-ví-dụ-end-to-end)

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
| 2 | **Template-driven** | Định nghĩa schema JSON → AI bóc tách đúng format |
| 3 | **Validation Layer** | Ép kiểu, chuẩn hóa ngày, phát hiện lỗi TRƯỚC khi lưu DB |
| 4 | **Human-in-the-loop** | Review (approve/reject/edit) trước khi aggregate |
| 5 | **Aggregation** | SUM, AVG, COUNT, CONCAT → gom N báo cáo thành 1 |
| 6 | **Word Export** | Nhồi dữ liệu vào template Word bằng Jinja2 (docxtpl) |
| 7 | **Word Scanner** | Quét file Word mẫu → auto-generate schema |
| 8 | **Batch processing** | Upload N file cùng lúc (max 20) |
| 9 | **Multi-tenant** | Cách ly hoàn toàn theo `tenant_id` |

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
3. [Bước 1] Worker tải file từ S3 → `run_from_bytes()`
  ├── Parse text + table bằng `pdfplumber`
  ├── Normalize text/bảng theo rule nghiệp vụ
  └── Giữ toàn bộ xử lý trong RAM (không ghi file tạm)
     ↓
4. [Bước 1] Inference qua Ollama + Instructor + Pydantic
  ├── Model mặc định: `settings.OLLAMA_MODEL` (vd: `qwen2.5:7b`)
  ├── Output ép kiểu theo `HybridExtractionOutput`
  └── RuleEngine check logic domain (`stt_14_tong_cnch == len(danh_sach_cnch)`, format ngày...)
     ↓
5. [Bước 2] Retry/Manual-review
  ├── Retry tối đa `HYBRID_MAX_RETRIES`
  ├── Quá số lần retry → ghi metadata manual review
  └── Persist trạng thái vào `extraction_jobs`
       ↓
6. INSERT clean_data → extraction_jobs.extracted_data (JSONB)
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
- `app/services/extraction_orchestrator.py`
- `app/services/hybrid_extraction_pipeline.py`
- `app/services/extractor_strategies.py`
- `app/schemas/hybrid_extraction_schema.py`

### 4.1 Kiến trúc chạy hiện tại

- Router jobs tạo `ExtractionJob` và đẩy Celery task `extract_document_task`
- Worker gọi `ExtractionOrchestrator.run(job_id)`
- Orchestrator tải file từ S3, chạy `pipeline.run_from_bytes(file_bytes, filename)`
- Kết quả được `JobManager.persist_pipeline_result()` lưu về DB

### 4.2 Hybrid pipeline 4 chặng

1. **Ingest:** Parse PDF bằng `pdfplumber` (text + table)
2. **Normalization:** Dọn layout, ghép dòng, ép phẳng bảng thành cặp field/value
3. **Inference:** Gọi extractor strategy (mặc định `OllamaInstructorExtractor`) và ép output theo `HybridExtractionOutput`
4. **Validation/Retry:** RuleEngine kiểm tra logic domain; fail thì retry, quá ngưỡng thì chuyển manual-review metadata

### 4.3 Domain Validation (Tiêm Rule động)

`RuleEngine` là core dùng chung và hỗ trợ tiêm (inject) luật tùy chỉnh theo từng loại tài liệu.

- Ví dụ với nghiệp vụ PCCC: `stt_14_tong_cnch == len(danh_sach_cnch)`
- Ví dụ khác: check format ngày `dd/mm/yyyy`, date range, đối soát count/list theo domain

Mục tiêu là tách phần khung xử lý chung khỏi luật nghiệp vụ riêng, để Engine 2 tái sử dụng cho nhiều domain (PCCC, tài chính, vận hành...).

### 4.4 Trạng thái lưu kết quả

- **Success:** `status=extracted`, `extracted_data=<HybridExtractionOutput model_dump>`
- **Fail sau retries:** `status=failed`, `extracted_data` chứa `_manual_review_path` và `_manual_review_metadata`
- `confidence_scores` lưu `_validation_attempts` + trạng thái pipeline

---

## 5. Bước 2: Rây lọc & Ép kiểu (Validation Layer)

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

## 6. Bước 3: Xào nấu dữ liệu (Aggregation & Map-Reduce)

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

## 7. Bước 4: Bơm khuôn Word (Headless Document Export)

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

## 8. Database Schema

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

### 8.2 extraction_jobs

```sql
CREATE TABLE extraction_jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    template_id     UUID NOT NULL REFERENCES extraction_templates(id) ON DELETE CASCADE,
    document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    batch_id        UUID,                        -- Nhóm batch
    extraction_mode VARCHAR(20) DEFAULT 'standard' NOT NULL,  -- standard|vision|fast

    -- State machine: pending → processing → extracted → approved
    --                                      ↘ failed     ↘ rejected
    status          VARCHAR(20) DEFAULT 'pending' NOT NULL,

    -- AI output (JSONB — đã qua Validation Layer)
    extracted_data     JSONB,
    confidence_scores  JSONB,                    -- Bao gồm _validation_report
    source_references  JSONB,

    -- Human review
    reviewed_data   JSONB,
    reviewed_by     UUID REFERENCES users(id) ON DELETE SET NULL,
    reviewed_at     TIMESTAMP,
    review_notes    TEXT,

    -- Processing metadata
    parser_used        VARCHAR(50),              -- pdfplumber|none
    llm_model          VARCHAR(100),             -- qwen2.5:7b (hoặc model extractor tương ứng)
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
```

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

### 8.4 Job State Machine

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
 approve│   reject│
       ▼     ▼
 ┌──────────┐ ┌──────────┐
 │ APPROVED │ │ REJECTED │◄──── retry_job() resets to PENDING
 └──────────┘ └──────────┘
       │
       │ aggregate()
       ▼
 ┌─────────────────────┐
 │ AggregationReport   │
 │ (draft → finalized) │
 └─────────────────────┘
```

---

## 9. API Reference — 23 Endpoints

**Router prefix:** `/api/v1/extraction`  
**Tags:** `Extraction Templates`, `Extraction Jobs`, `Extraction Reports`

### 9.1 Word Scanner

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

### 9.2 Templates CRUD

| Method | Path | Auth | Status | Description |
|---|---|---|---|---|
| `POST` | `/templates` | `require_admin` | 201 | Tạo template mới |
| `GET` | `/templates` | `require_viewer` | 200 | List templates (paginated) |
| `GET` | `/templates/{template_id}` | `require_viewer` | 200 | Chi tiết template |
| `PATCH` | `/templates/{template_id}` | `require_admin` | 200 | Sửa template (schema change → version++) |
| `DELETE` | `/templates/{template_id}` | `RoleChecker("owner")` | 204 | Soft delete |

### 9.3 Jobs

| Method | Path | Auth | Status | Description |
|---|---|---|---|---|
| `POST` | `/jobs` | `require_admin` | 202 | Upload 1 PDF + tạo job → Celery |
| `POST` | `/jobs/batch` | `require_admin` | 202 | Upload N PDFs (max 20) → N jobs |
| `POST` | `/jobs/from-document` | `require_admin` | 202 | Tạo job từ document đã upload |
| `GET` | `/jobs` | `require_viewer` | 200 | List jobs (filter: status, template_id, batch_id) |
| `GET` | `/jobs/{job_id}` | `require_viewer` | 200 | Polling endpoint |
| `GET` | `/jobs/batch/{batch_id}/status` | `require_viewer` | 200 | Batch progress |
| `POST` | `/jobs/{job_id}/retry` | `require_admin` | 200 | Retry failed/rejected |
| `DELETE` | `/jobs/{job_id}` | `require_admin` | 204 | Xóa job đã hoàn tất |

### 9.4 Review

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/review/{job_id}/approve` | `require_admin` | Approve (+ optional `reviewed_data`) |
| `POST` | `/review/{job_id}/reject` | `require_admin` | Reject (required `notes`) |

### 9.5 Aggregation & Export

| Method | Path | Auth | Status | Description |
|---|---|---|---|---|
| `POST` | `/aggregate` | `require_admin` | 201 | Gom N jobs → 1 report |
| `GET` | `/aggregate` | `require_viewer` | 200 | List reports |
| `GET` | `/aggregate/{report_id}` | `require_viewer` | 200 | Chi tiết report |
| `DELETE` | `/aggregate/{report_id}` | `require_admin` | 204 | Xóa report |
| `GET` | `/aggregate/{report_id}/export` | `require_viewer` | 200 | Export Excel/CSV/JSON (query: `?format=excel`) |
| `POST` | `/aggregate/{report_id}/export-word` | `require_viewer` | 200 | Upload .docx template → render → download |
| `GET` | `/aggregate/{report_id}/export-word-auto` | `require_viewer` | 200 | Dùng template đã lưu trong S3 để render |

---

## 10. Cấu hình (Configuration)

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

## 11. Celery Workers & Background Tasks

**File:** `app/worker/extraction_tasks.py`

### 11.1 extract_document_task

```python
@celery_app.task(
    name="extract_document",
    bind=True,
    max_retries=settings.EXTRACTION_MAX_RETRIES,
)
def extract_document_task(self, job_id: str):
  """Pipeline: load job → S3 download → hybrid run_from_bytes → persist."""
```

- **Queue runtime:** được route vào `extraction` qua `celery_app.conf.task_routes`
- **Retry:** Exponential backoff (2^retry_count × 60s), max 3 lần
- **Failure:** Sau max retries → status = `failed`, `error_message` ghi lại

```python
celery_app.conf.task_routes = {
    "app.worker.extraction_tasks.extract_document_task": {"queue": "extraction"},
}
```

Nếu không route rõ, task có thể rơi vào queue mặc định (`task_default_queue`).

### 11.2 cleanup_stuck_jobs

```python
@celery_app.task(name="cleanup_stuck_extraction_jobs")
def cleanup_stuck_jobs():
    """Periodic: tìm jobs stuck ở 'processing' > 30 phút → mark 'failed'."""
```

- Chạy bởi **Celery Beat** (periodic scheduler)
- Timeout: `settings.EXTRACTION_TIMEOUT_MINUTES` (default 30 phút)

---

## 12. Word Template Scanner

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

## 13. Pydantic Schemas (Request/Response)

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

## 14. Cấu trúc Source Code

```
app/
├── api/v1/
│   ├── extraction_templates.py # Template endpoints + word scan
│   ├── extraction_jobs.py      # Job lifecycle + review
│   ├── extraction_reports.py   # Aggregate + export endpoints
│   └── extraction.py           # Compatibility router (include split routers)
├── models/
│   └── extraction.py           # ExtractionTemplate/Job/AggregationReport
├── schemas/
│   ├── extraction_schema.py    # Request/response schemas
│   └── hybrid_extraction_schema.py # HybridExtractionOutput + CNCHItem
├── services/
│   ├── extraction_orchestrator.py   # Worker orchestration (S3 + pipeline + persistence)
│   ├── hybrid_extraction_pipeline.py # Ingest/normalize/infer/retry
│   ├── extractor_strategies.py      # LLM backend strategies (Ollama/OpenAI/Gemini)
│   ├── template_manager.py          # Template domain service
│   ├── job_manager.py               # Job lifecycle service
│   ├── rule_engine.py               # Domain validation rules
│   ├── extraction_service.py        # Backward-compatible facade
│   ├── aggregation_service.py       # Aggregation + export context DTO
│   ├── word_scanner.py              # Word template scanner
│   └── word_export.py               # Secure docxtpl renderer
└── worker/
  └── extraction_tasks.py          # Celery tasks (hybrid execution + cleanup)

Tổng quan: kiến trúc đã tách router/service theo domain để giảm coupling.
```

---

## 15. Ví dụ End-to-End

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

> **Tài liệu này được cập nhật lần cuối: 19/03/2026**  
> **Tổng source code Engine 2: kiến trúc split-router/service · 23 endpoints · 3 bảng DB · 7 JSONB columns · 3 GIN indexes cốt lõi (+1 optional cho reports)**
