# âš™ï¸ Engine 2 â€” Há»‡ thá»‘ng BÃ³c tÃ¡ch Dá»¯ liá»‡u Tá»± Ä‘á»™ng (AI Data Extraction)

> **PhiÃªn báº£n:** 4.0.0
> **Cáº­p nháº­t:** 03/04/2026
> **Stack:** FastAPI Â· SQLAlchemy Â· Celery Â· PostgreSQL (JSONB) Â· Ollama (Instructor + Pydantic) Â· docxtpl Â· YAML Templates Â· PipelineMetrics Â· Two-Stage Block Pipeline

---

## Má»¥c lá»¥c

1. [Tá»•ng quan](#1-tá»•ng-quan)
2. [Kiáº¿n trÃºc LÆ°u trá»¯ â€” PostgreSQL Hybrid](#2-kiáº¿n-trÃºc-lÆ°u-trá»¯--postgresql-hybrid)
3. [Pipeline 4 BÆ°á»›c KhÃ©p KÃ­n](#3-pipeline-4-bÆ°á»›c-khÃ©p-kÃ­n)
4. [BÆ°á»›c 1: BÃ³c tÃ¡ch thÃ´ (Hybrid Extraction)](#4-bÆ°á»›c-1-bÃ³c-tÃ¡ch-thÃ´-hybrid-extraction)
5. [Block Mode â€” Two-Stage Pipeline (v4)](#5-block-mode--two-stage-pipeline-v4)
6. [BÆ°á»›c 2: RÃ¢y lá»c & Ã‰p kiá»ƒu (Validation Layer)](#6-bÆ°á»›c-2-rÃ¢y-lá»c--Ã©p-kiá»ƒu-validation-layer)
7. [BÆ°á»›c 3: XÃ o náº¥u dá»¯ liá»‡u (Aggregation & Map-Reduce)](#7-bÆ°á»›c-3-xÃ o-náº¥u-dá»¯-liá»‡u-aggregation--map-reduce)
8. [BÆ°á»›c 4: BÆ¡m khuÃ´n Word (Headless Document Export)](#8-bÆ°á»›c-4-bÆ¡m-khuÃ´n-word-headless-document-export)
9. [Database Schema](#9-database-schema)
10. [API Reference â€” 25 Endpoints](#10-api-reference--25-endpoints)
11. [Cáº¥u hÃ¬nh (Configuration)](#11-cáº¥u-hÃ¬nh-configuration)
12. [Celery Workers & Background Tasks](#12-celery-workers--background-tasks)
13. [Word Template Scanner](#13-word-template-scanner)
14. [Pydantic Schemas (Request/Response)](#14-pydantic-schemas-requestresponse)
15. [Phase 3 â€” Template-driven Â· Dynamic Columns Â· Batch Parallel Â· Observability](#15-phase-3--template-driven--dynamic-columns--batch-parallel--observability)
16. [Cáº¥u trÃºc Source Code](#16-cáº¥u-trÃºc-source-code)
17. [VÃ­ dá»¥ End-to-End](#17-vÃ­-dá»¥-end-to-end)

---

## 1. Tá»•ng quan

Engine 2 lÃ  há»‡ thá»‘ng **bÃ³c tÃ¡ch dá»¯ liá»‡u cÃ³ cáº¥u trÃºc** tá»« tÃ i liá»‡u PDF/Word. KhÃ¡c vá»›i Engine 1 (RAG â€” há»i Ä‘Ã¡p tá»± do), Engine 2 **ra lá»‡nh cho AI tráº£ vá» JSON Ä‘Ãºng schema**, rá»“i tá»•ng há»£p N file thÃ nh 1 bÃ¡o cÃ¡o.

### BÃ i toÃ¡n giáº£i quyáº¿t

```
ðŸ“„ BÃ¡o cÃ¡o NgÃ y 1 (PDF)  â”€â”
ðŸ“„ BÃ¡o cÃ¡o NgÃ y 2 (PDF)  â”€â”¤â”€â”€â†’ AI bÃ³c tÃ¡ch â”€â”€â†’ Validation â”€â”€â†’ Aggregation â”€â”€â†’ ðŸ“Š BÃ¡o cÃ¡o Tuáº§n (Word)
ðŸ“„ BÃ¡o cÃ¡o NgÃ y 3 (PDF)  â”€â”˜
```

### TÃ­nh nÄƒng chÃ­nh

| # | TÃ­nh nÄƒng | MÃ´ táº£ |
|---|---|---|
| 1 | **Hybrid extraction máº·c Ä‘á»‹nh** | Cháº¡y `HybridExtractionPipeline` (pdfplumber + normalize + Ollama + rule validation) tá»« bytes in-memory |
| 2 | **Block mode two-stage (v4)** | Stage 1 = deterministic (khÃ´ng LLM), Stage 2 = LLM enrichment async Ä‘á»™c láº­p. Document dÃ¹ng Ä‘Æ°á»£c ngay sau Stage 1 ká»ƒ cáº£ khi Ollama táº¯t |
| 4 | **Template-driven** | Äá»‹nh nghÄ©a schema JSON â†’ AI bÃ³c tÃ¡ch Ä‘Ãºng format |
| 5 | **YAML Template System** | Táº¥t cáº£ regex/pattern/threshold Ä‘Æ°á»£c gá»­i ngoÃ i vÃ o file YAML (`app/templates/pccc.yaml`), khÃ´ng cÃ²n hardcode |
| 6 | **Dynamic Column Detection** | Tá»± Ä‘á»™ng phÃ¡t hiá»‡n cá»™t STT/Ná»™i dung/Káº¿t quáº£ trong báº£ng thá»‘ng kÃª thay vÃ¬ giáº£ Ä‘á»‹nh cá»‘ Ä‘á»‹nh |
| 7 | **Validation Layer** | Ã‰p kiá»ƒu, chuáº©n hÃ³a ngÃ y, phÃ¡t hiá»‡n lá»—i TRÆ¯á»šC khi lÆ°u DB |
| 8 | **Human-in-the-loop** | Review (approve/reject/edit) trÆ°á»›c khi aggregate |
| 9 | **Aggregation** | SUM, AVG, COUNT, CONCAT â†’ gom N bÃ¡o cÃ¡o thÃ nh 1 |
| 10 | **Word Export** | Nhá»“i dá»¯ liá»‡u vÃ o template Word báº±ng Jinja2 (docxtpl) |
| 11 | **Word Scanner** | QuÃ©t file Word máº«u â†’ auto-generate schema |
| 12 | **Batch processing (Celery)** | Upload N file cÃ¹ng lÃºc (max 20) â†’ N Celery tasks phÃ¢n tÃ¡n |
| 13 | **Batch parallel (in-process)** | `run_batch()` cháº¡y block pipeline song song vá»›i `ThreadPoolExecutor` + backpressure |
| 14 | **Observability Metrics** | `PipelineMetrics` (per-run counters/timers) + `GlobalMetrics` (thread-safe aggregator) + API endpoint |
| 15 | **Multi-tenant** | CÃ¡ch ly hoÃ n toÃ n theo `tenant_id` |

---

## 2. Kiáº¿n trÃºc LÆ°u trá»¯ â€” PostgreSQL Hybrid

> **NguyÃªn táº¯c: Giá»¯ nguyÃªn PostgreSQL, KHÃ”NG Ä‘á»•i sang NoSQL.**

### 2.1 Táº§ng Relational (Cá»™t cá»©ng)

Quáº£n lÃ½ phÃ¢n quyá»n, quan há»‡ thá»±c thá»ƒ, Ä‘áº£m báº£o ACID:

```
tenants.id â”€â”€â†’ extraction_templates.tenant_id
               extraction_jobs.tenant_id
               aggregation_reports.tenant_id

users.id â”€â”€â†’ extraction_templates.created_by
             extraction_jobs.created_by / reviewed_by

documents.id â”€â”€â†’ extraction_jobs.document_id

extraction_templates.id â”€â”€â†’ extraction_jobs.template_id
                           aggregation_reports.template_id
```

### 2.2 Táº§ng Document (Linh hoáº¡t) â€” JSONB

Dá»¯ liá»‡u bÃ³c tÃ¡ch, schema, káº¿t quáº£ tá»•ng há»£p â†’ lÆ°u **JSONB** (khÃ´ng pháº£i JSON):

| Báº£ng | Cá»™t JSONB | Má»¥c Ä‘Ã­ch |
|---|---|---|
| `extraction_templates` | `schema_definition` | Äá»‹nh nghÄ©a fields cáº§n bÃ³c tÃ¡ch |
| `extraction_templates` | `aggregation_rules` | Rules tá»•ng há»£p (SUM, CONCAT...) |
| `extraction_jobs` | `extracted_data` | Dá»¯ liá»‡u AI bÃ³c tÃ¡ch (Ä‘Ã£ qua Validation) |
| `extraction_jobs` | `confidence_scores` | Äiá»ƒm tá»± tin + validation report |
| `extraction_jobs` | `source_references` | TrÃ­ch dáº«n nguá»“n (trang, quote) |
| `extraction_jobs` | `reviewed_data` | Dá»¯ liá»‡u sau khi human review |
| `aggregation_reports` | `aggregated_data` | Káº¿t quáº£ tá»•ng há»£p cuá»‘i cÃ¹ng |

### 2.3 GIN Indexes

3 GIN index cá»‘t lÃµi cho truy váº¥n JSONB thÆ°á»ng dÃ¹ng:

```sql
CREATE INDEX idx_extraction_jobs_extracted_data_gin ON extraction_jobs USING GIN (extracted_data);
CREATE INDEX idx_extraction_jobs_reviewed_data_gin  ON extraction_jobs USING GIN (reviewed_data);
CREATE INDEX idx_extraction_templates_schema_gin    ON extraction_templates USING GIN (schema_definition);
```

`aggregation_reports.aggregated_data` chá»‰ nÃªn thÃªm GIN index khi cÃ³ nghiá»‡p vá»¥ search/filter trá»±c tiáº¿p trÃªn report JSON (vÃ­ dá»¥ query `@>` theo ngÆ°á»¡ng tá»•ng há»£p). Náº¿u chá»‰ dÃ¹ng Ä‘á»ƒ export/render thÃ¬ Ä‘á»ƒ trÃ¡nh write overhead, nÃªn bá» index nÃ y.

**Query vÃ­ dá»¥** â€” tÃ¬m táº¥t cáº£ jobs cÃ³ `so_vu > 5`:
```sql
SELECT * FROM extraction_jobs
WHERE extracted_data @> '{"so_vu": 5}'::jsonb;
```

### 2.4 LÃ½ do KHÃ”NG dÃ¹ng NoSQL

| TiÃªu chÃ­ | PostgreSQL JSONB | MongoDB |
|---|---|---|
| ACID transactions | âœ… CÃ³ | âŒ Háº¡n cháº¿ |
| JOIN vá»›i báº£ng khÃ¡c | âœ… SQL chuáº©n | âŒ Pháº£i $lookup |
| pgvector (Engine 1) | âœ… CÃ¹ng DB | âŒ Cáº§n DB riÃªng |
| GIN index | âœ… Cá»±c nhanh | âœ… TÆ°Æ¡ng Ä‘Æ°Æ¡ng |
| Schema linh hoáº¡t | âœ… JSONB | âœ… Native |
| Infra complexity | âœ… 1 DB | âŒ +1 DB ná»¯a |

---

## 3. Pipeline 4 BÆ°á»›c KhÃ©p KÃ­n

```
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚                        ENGINE 2 PIPELINE                                     â”‚
â”‚                                                                              â”‚
â”‚  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”    â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”    â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”    â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”  â”‚
â”‚  â”‚ BÆ¯á»šC 1   â”‚    â”‚   BÆ¯á»šC 2     â”‚    â”‚   BÆ¯á»šC 3     â”‚    â”‚    BÆ¯á»šC 4     â”‚  â”‚
â”‚  â”‚ AI       â”‚    â”‚  Validation  â”‚    â”‚ Aggregation  â”‚    â”‚  Word Export  â”‚  â”‚
â”‚  â”‚ Extract  â”‚â”€â”€â”€â†’â”‚  Layer       â”‚â”€â”€â”€â†’â”‚ Map-Reduce   â”‚â”€â”€â”€â†’â”‚  (docxtpl)   â”‚  â”‚
â”‚  â”‚          â”‚    â”‚  (Pydantic)  â”‚    â”‚  (Pandas)    â”‚    â”‚              â”‚  â”‚
â”‚  â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜    â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜    â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜    â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜  â”‚
â”‚       â”‚                â”‚                    â”‚                    â”‚            â”‚
â”‚   Raw JSON         Clean JSON          Aggregated           .docx file      â”‚
â”‚   (cÃ³ lá»—i)        (Ä‘Ã£ Ã©p kiá»ƒu)          JSON              (hoÃ n chá»‰nh)     â”‚
â”‚                                                                              â”‚
â”‚                    â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”                                              â”‚
â”‚                    â”‚ HUMAN    â”‚                                              â”‚
â”‚                    â”‚ REVIEW   â”‚ â† Approve / Reject / Edit                   â”‚
â”‚                    â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜                                              â”‚
â”‚                    (giá»¯a BÆ°á»›c 2 & 3)                                        â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

### Luá»“ng chi tiáº¿t

```
1. User upload PDF + chá»n Template
       â†“
2. Celery worker nháº­n task
       â†“
3. [BÆ°á»›c 1] Worker táº£i file tá»« S3 â†’ tÃ¹y `extraction_mode`:
  **Standard/Vision/Fast:**
  â”œâ”€â”€ `pipeline.run_from_bytes()` â€” pdfplumber + normalize + Ollama + rule validation
  â””â”€â”€ `persist_pipeline_result()` â†’ job.status = EXTRACTED

  **Block (v4 â€” two-stage):**
  â”œâ”€â”€ `pipeline.run_stage1_from_bytes()` â€” pdfplumber + regex ONLY, no LLM
  â”œâ”€â”€ `persist_stage1_result()` â†’ job.status = EXTRACTED, enrichment_status = PENDING
  â””â”€â”€ `enrich_job_task.apply_async(queue="enrichment")` â†’ fire-and-forget
     â†“
4. [Stage 1 Block] 6 sub-stages (táº¥t cáº£ deterministic):
  â”œâ”€â”€ layout reconstruction (pdfplumber + restore_vn_spacing)
  â”œâ”€â”€ block detection (regex anchors tá»« YAML template)
  â”œâ”€â”€ header extraction (regex: sá»‘ bÃ¡o cÃ¡o, ngÃ y, Ä‘Æ¡n vá»‹)
  â”œâ”€â”€ narrative extraction (regex: tong_so_vu_*, chi_tiet_cnch)
  â”œâ”€â”€ table parsing (dynamic column detect + pdfplumber)
  â””â”€â”€ business rules engine + sanity checks
     â†“
5. [Stage 2 Block â€” async, queue enrichment] enrich_job_task:
  â”œâ”€â”€ Äá»c chi_tiet_cnch tá»« extracted_data
  â”œâ”€â”€ Gá»i CNCHListOutput LLM (120s timeout, model: qwen3:8b)
  â”œâ”€â”€ ThÃ nh cÃ´ng â†’ enriched_data = {"danh_sach_cnch": [...]}
  â””â”€â”€ Tháº¥t báº¡i â†’ enrichment_status = FAILED, job váº«n dÃ¹ng Ä‘Æ°á»£c
     â†“
6. INSERT â†’ extraction_jobs.extracted_data (Stage 1) + enriched_data (Stage 2)
       â†“
7. [Human Review] Approve / Reject / Edit â†’ reviewed_data
       â†“
8. [BÆ°á»›c 3] N jobs approved â†’ AggregationService.aggregate()
   â”œâ”€â”€ pd.json_normalize() Ä‘áº­p pháº³ng nested JSON
   â”œâ”€â”€ Apply rules: SUM, AVG, COUNT, CONCAT, LAST
   â””â”€â”€ Output: aggregated_data + records + _flat_records + _metadata
       â†“
9. [BÆ°á»›c 4] Upload Word template (.docx) + aggregated_data
   â”œâ”€â”€ docxtpl render Jinja2 placeholders
   â”œâ”€â”€ Filters: number_vn, date_vn, date_short
   â””â”€â”€ Download: file .docx hoÃ n chá»‰nh
```

---

## 4. BÆ°á»›c 1: BÃ³c tÃ¡ch thÃ´ (Hybrid Extraction)

**Files chÃ­nh:**
- `app/engines/extraction/orchestrator.py`
- `app/engines/extraction/hybrid_pipeline.py`
- `app/engines/extraction/block_pipeline.py` *(block mode â€” xem Section 5)*
- `app/engines/extraction/extractors.py`
- `app/engines/extraction/schemas.py`

### 4.1 Kiáº¿n trÃºc cháº¡y hiá»‡n táº¡i

**Hybrid mode (standard/vision/fast):**
- Router táº¡o `ExtractionJob` vÃ  Ä‘áº©y Celery task `extract_document_task` â†’ queue `extraction`
- Worker gá»i `ExtractionOrchestrator.run(job_id)`
- Orchestrator táº£i file tá»« S3, cháº¡y `pipeline.run_from_bytes(file_bytes, filename)`
- Káº¿t quáº£ Ä‘Æ°á»£c `JobManager.persist_pipeline_result()` lÆ°u vá» DB

**Block mode (v4 â€” two-stage):**
- Orchestrator nháº­n diá»‡n `extraction_mode == "block"` vÃ  dÃ¹ng Ä‘Æ°á»ng Ä‘áº·c biá»‡t:
  1. Gá»i `pipeline.run_stage1_from_bytes()` â€” khÃ´ng cÃ³ LLM, tráº£ vá» ngay
  2. Gá»i `persist_stage1_result()` â†’ `job.status = EXTRACTED`, `job.enrichment_status = PENDING`
  3. Dispatch `enrich_job_task.apply_async(queue="enrichment")` â†’ fire-and-forget
- Xem chi tiáº¿t táº¡i [Section 5](#5-block-mode--two-stage-pipeline-v4)

### 4.2 Hybrid pipeline 4 cháº·ng

1. **Ingest:** Parse PDF báº±ng `pdfplumber` (text + table)
2. **Normalization:** Dá»n layout, ghÃ©p dÃ²ng, Ã©p pháº³ng báº£ng thÃ nh cáº·p field/value
3. **Inference:** Gá»i extractor strategy (máº·c Ä‘á»‹nh `OllamaInstructorExtractor`) vÃ  Ã©p output theo `HybridExtractionOutput`
4. **Validation/Retry:** RuleEngine kiá»ƒm tra logic domain; fail thÃ¬ retry, quÃ¡ ngÆ°á»¡ng thÃ¬ chuyá»ƒn manual-review metadata

### 4.3 Domain Validation (TiÃªm Rule Ä‘á»™ng)

`RuleEngine` lÃ  core dÃ¹ng chung vÃ  há»— trá»£ tiÃªm (inject) luáº­t tÃ¹y chá»‰nh theo tá»«ng loáº¡i tÃ i liá»‡u.

- VÃ­ dá»¥ vá»›i nghiá»‡p vá»¥ PCCC: `stt_14_tong_cnch == len(danh_sach_cnch)`
- VÃ­ dá»¥ khÃ¡c: check format ngÃ y `dd/mm/yyyy`, date range, Ä‘á»‘i soÃ¡t count/list theo domain

### 4.4 Tráº¡ng thÃ¡i lÆ°u káº¿t quáº£

- **Success:** `status=extracted`, `extracted_data=<output model_dump>`
- **Fail sau retries:** `status=failed`, `extracted_data` chá»©a `_manual_review_path` vÃ  `_manual_review_metadata`
- `confidence_scores` lÆ°u `_validation_attempts` + tráº¡ng thÃ¡i pipeline

---

## 5. Block Mode â€” Two-Stage Pipeline (v4)

> **NguyÃªn táº¯c cá»‘t lÃµi:** LLM khÃ´ng bao giá» náº±m trÃªn critical path. Document pháº£i dÃ¹ng Ä‘Æ°á»£c ngay sau Stage 1 ká»ƒ cáº£ khi Ollama táº¯t hoÃ n toÃ n.

### 5.1 Táº¡i sao cáº§n Two-Stage

| Váº¥n Ä‘á» (v3 â€” má»™t stage) | Giáº£i phÃ¡p (v4 â€” two-stage) |
|---|---|
| LLM timeout 120s â†’ user chá» 120s má»›i tháº¥y káº¿t quáº£ | User tháº¥y káº¿t quáº£ ngay sau Stage 1 (~vÃ i giÃ¢y) |
| Ollama cháº¿t â†’ toÃ n bá»™ job `FAILED`, khÃ´ng cÃ³ dá»¯ liá»‡u nÃ o | Ollama cháº¿t â†’ job váº«n `EXTRACTED`, dÃ¹ng bÃ¬nh thÆ°á»ng |
| 4 extraction workers táº¥t cáº£ chá» LLM | 4 extraction workers cháº¡y tá»± do; 2 enrichment workers riÃªng xá»­ lÃ½ LLM |
| LLM output láº«n vÃ o `extracted_data` â†’ khÃ³ audit | LLM output trong `enriched_data` riÃªng, `final_data` merge theo priority rÃµ rÃ ng |

### 5.2 Kiáº¿n trÃºc tá»•ng quan

```
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚                       BLOCK MODE TWO-STAGE PIPELINE (v4)                       â”‚
â”‚                                                                                â”‚
â”‚  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”      â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â” â”‚
â”‚  â”‚          STAGE 1                 â”‚      â”‚          STAGE 2                 â”‚ â”‚
â”‚  â”‚    (Deterministic â€” No LLM)      â”‚      â”‚    (LLM Enrichment â€” Async)      â”‚ â”‚
â”‚  â”‚                                  â”‚      â”‚                                  â”‚ â”‚
â”‚  â”‚  1. PDF layout reconstruction    â”‚      â”‚  1. Read chi_tiet_cnch from DB   â”‚ â”‚
â”‚  â”‚  2. Block detection              â”‚â”€â”€â”€â”€â”€â†’â”‚  2. Call CNCHListOutput (120s)   â”‚ â”‚
â”‚  â”‚  3. Header extraction (regex)    â”‚ fire â”‚  3. Write enriched_data (JSONB)  â”‚ â”‚
â”‚  â”‚  4. Narrative extraction (regex) â”‚ and  â”‚  4. enrichment_status = ENRICHED â”‚ â”‚
â”‚  â”‚  5. Table parsing (pdfplumber)   â”‚ forget    hoáº·c FAILED náº¿u lá»—i           â”‚ â”‚
â”‚  â”‚  6. Business rules engine        â”‚      â”‚                                  â”‚ â”‚
â”‚  â”‚  7. Regex CNCH / vehicle / CV    â”‚      â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜ â”‚
â”‚  â”‚                                  â”‚               Queue: enrichment           â”‚
â”‚  â”‚  â†’ job.status = EXTRACTED        â”‚               concurrency = 2             â”‚
â”‚  â”‚  â†’ enrichment_status = PENDING   â”‚                                          â”‚
â”‚  â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜                                          â”‚
â”‚           Queue: extraction                                                     â”‚
â”‚           concurrency = 4                                                       â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

## 6. BÆ°á»›c 2: RÃ¢y lá»c & Ã‰p kiá»ƒu (Validation Layer)

**Entry point:** `BlockExtractionPipeline.run_stage1_from_bytes(pdf_bytes, filename)`
**File:** `app/engines/extraction/block_pipeline.py`

Gá»“m 6 stage ná»™i bá»™, **táº¥t cáº£ Ä‘á»u khÃ´ng gá»i LLM**:

| Stage ná»™i bá»™ | Timer metric | MÃ´ táº£ |
|---|---|---|
| `stage1_layout` | `stage1_layout` | `pdfplumber` tÃ¡i táº¡o text + extract tables. `layout_text` giá»¯ tráº­t tá»± Ä‘á»c |
| `stage2_detect` | `stage2_detect` | PhÃ¡t hiá»‡n block: `header`, `phan_nghiep_vu`, `bang_thong_ke` báº±ng regex anchor tá»« YAML template |
| `stage3_extract` | `stage3_extract` | `_extract_header()` â†’ regex; `_extract_narrative()` â†’ regex (`_parse_phan_nghiep_vu_fallback`); `_extract_table()` â†’ dynamic column detect + pdfplumber; `_apply_cnch_fallback()` â†’ Ä‘á»‘i soÃ¡t vá»›i báº£ng thá»‘ng kÃª |
| `stage6_business` | `stage6_business` | `_run_business_rules()` â†’ RuleEngine check táº¥t cáº£ domain logic (counts, date format, sanity) |
| `stage_narrative_arrays` | `stage_narrative_arrays` | `_extract_narrative_arrays(..., chi_tiet_cnch="")` vá»›i **chi_tiet_cnch trá»‘ng** â†’ bá» qua nhÃ¡nh LLM. Regex/business-rules trÃ­ch `pt_hu_hong`, `cong_van`, regex CNCH |
| Sanity check | â€” | Äá»‘i soÃ¡t `tong_so_vu_chay/no/cnch` vá»›i báº£ng thá»‘ng kÃª (`stt_2`, `stt_8`, `stt_14`), ghi Ä‘Ã¨ náº¿u lá»‡ch |

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
    chi_tiet_cnch: str = ""        # â† v4 má»›i: raw CNCH subsection text cho Stage 2
```

**`BlockExtractionOutput` schema:**
```python
class BlockExtractionOutput(BaseModel):
    header: BlockHeader
    phan_I_va_II_chi_tiet_nghiep_vu: BlockNghiepVu
    bang_thong_ke: list[ChiTieu]
    danh_sach_cnch: list[CNCHItem]                     # regex-only á»Ÿ Stage 1
    danh_sach_phuong_tien_hu_hong: list[PhuongTienHuHongItem]
    danh_sach_cong_van_tham_muu: list[CongVanItem]
```

**Sub-schemas `BlockNghiepVu`:**
```python
class BlockNghiepVu(BaseModel):
    tong_so_vu_chay: int
    tong_so_vu_no: int
    tong_so_vu_cnch: int
    chi_tiet_cnch: str      # â† raw text cá»§a má»¥c 3, Stage 2 dÃ¹ng Ä‘á»ƒ gá»i LLM
    quan_so_truc: int
    tong_chi_vien: int
    tong_cong_van: int
    tong_xe_hu_hong: int
```

### 5.4 Stage 2 â€” LLM Enrichment

**Entry point:** `enrich_job_task(job_id)` â€” Celery task
**File:** `app/infrastructure/worker/enrichment_tasks.py`
**Queue:** `enrichment` | **Concurrency:** 2 | **Soft time limit:** 180s | **Max retries:** 3

LLM method duy nháº¥t trong toÃ n bá»™ block pipeline:

```python
def _llm_enrich_cnch(self, chi_tiet_cnch: str) -> list[CNCHItem]:
    """Gá»i CNCHListOutput LLM call â€” PHÆ¯Æ NG THá»¨C DUY NHáº¤T gá»i LLM trong block pipeline."""
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

**`CNCHItem` â€” 8 fields (LLM Ä‘iá»n Ä‘áº§y Ä‘á»§ á»Ÿ Stage 2):**
```python
class CNCHItem(BaseModel):
    stt: int
    ngay_xay_ra: str        # dd/mm/yyyy
    thoi_gian: str          # "HH:MM ngÃ y dd/mm/yyyy" hoáº·c "HH giá» MM phÃºt ngÃ y dd/mm/yyyy"
    dia_diem: str
    noi_dung_tin_bao: str   # loáº¡i sá»± cá»‘ (vÃ­ dá»¥: "ngÆ°á»i dÃ¢n nháº£y sÃ´ng")
    luc_luong_tham_gia: str # "01 xe, 06 CBCS"
    ket_qua_xu_ly: str
    thong_tin_nan_nhan: str
    mo_ta: str              # internal â€” backward compat vá»›i business-rules path
```

**Flow cá»§a `enrich_job_task`:**
```
1. Load job tá»« DB
2. Guard: chá»‰ process khi enrichment_status IN (PENDING, FAILED)
3. Set enrichment_status = RUNNING, enrichment_started_at = now
4. Äá»c chi_tiet_cnch tá»« job.extracted_data["phan_I_va_II_..."]["chi_tiet_cnch"]
5. Gá»i BlockExtractionPipeline._llm_enrich_cnch(chi_tiet_cnch)
6. ThÃ nh cÃ´ng â†’ job.enriched_data = {"danh_sach_cnch": [...]}, enrichment_status = ENRICHED
   Tháº¥t báº¡i â†’ enrichment_status = FAILED, job.extracted_data KHÃ”NG Bá»Š Äá»¤ VÃ€O
```

### 5.5 EnrichmentStatus â€” State machine Ä‘á»™c láº­p

```
           Stage 1 succeeded
                  â”‚
          â”Œâ”€â”€â”€â”€â”€â”€â”€â–¼â”€â”€â”€â”€â”€â”€â”€â”€â”
          â”‚    PENDING     â”‚  enrichment_status = PENDING
          â””â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”˜  (enrichment_status = SKIPPED náº¿u khÃ´ng cÃ³ chi_tiet_cnch)
                  â”‚ enrich_job_task picked up
          â”Œâ”€â”€â”€â”€â”€â”€â”€â–¼â”€â”€â”€â”€â”€â”€â”€â”€â”
          â”‚    RUNNING     â”‚
          â””â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”˜
       success â”‚       â”‚ failure
          â”Œâ”€â”€â”€â”€â–¼â”€â”€â”€â”  â”Œâ–¼â”€â”€â”€â”€â”€â”€â”€â”
          â”‚ENRICHEDâ”‚  â”‚ FAILED â”‚ â† job váº«n EXTRACTED, dÃ¹ng Stage 1 data
          â””â”€â”€â”€â”€â”€â”€â”€â”€â”˜  â””â”€â”€â”€â”¬â”€â”€â”€â”€â”˜
                          â”‚ retry (max 3, backoff 60s)
                          â””â”€â”€â”€â”€â”€â”€â†’ RUNNING láº¡i
```

`None` = job Ä‘Æ°á»£c táº¡o trÆ°á»›c khi upgrade lÃªn v4 (legacy, khÃ´ng cÃ³ enrichment)

### 5.6 Merge priority â€” `final_data` property

```python
@property
def final_data(self) -> dict | None:
    """Merge priority: reviewed_data > (extracted + enriched merged) > extracted"""
    if self.reviewed_data:
        return self.reviewed_data          # Human-edited luÃ´n tháº¯ng
    if self.extracted_data and self.enriched_data:
        merged = dict(self.extracted_data)
        merged.update(self.enriched_data)  # LLM fields merge ON TOP nhÆ°ng khÃ´ng overwrite
        return merged
    return self.reviewed_data or self.extracted_data
```

**NguyÃªn táº¯c:** `enriched_data` chá»‰ chá»©a `{"danh_sach_cnch": [...]}`. Stage 1 `extracted_data` chá»©a táº¥t cáº£ fields cÃ²n láº¡i. Hai set nÃ y khÃ´ng overlap â†’ khÃ´ng bao giá» ghi Ä‘Ã¨ láº«n nhau.

### 5.7 Persistence â€” JobManager

**`persist_stage1_result(job, result, llm_model, processing_time_ms)`**
- Ghi `job.extracted_data = result.output.model_dump()` â€” **canonical nested JSON, 7 top-level keys, khÃ´ng cÃ³ flat key nÃ o**
- Set `job.status = EXTRACTED`
- Set `job.enrichment_status = PENDING` náº¿u `result.chi_tiet_cnch` khÃ´ng rá»—ng, else `SKIPPED`
- **KhÃ´ng Ä‘á»¥ng vÃ o** `enriched_data`
- **LÆ°u Ã½ (Plan A):** `flatten_block_output()` **khÃ´ng Ä‘Æ°á»£c gá»i** táº¡i Ä‘Ã¢y. Flattening chá»‰ diá»…n ra in-memory trong `AggregationService.aggregate()` khi chuáº©n bá»‹ context cho Word export. `extracted_data` luÃ´n giá»¯ nguyÃªn dáº¡ng nested canonical.

**`persist_enrichment_result(job_id, enriched_cnch, error)`** (thá»±c thi bá»Ÿi `enrich_job_task`)
- Ghi `job.enriched_data = {"danh_sach_cnch": [...]}`
- Set `job.enrichment_status = ENRICHED | FAILED | SKIPPED`
- **Tuyá»‡t Ä‘á»‘i khÃ´ng Ä‘á»¥ng vÃ o** `job.extracted_data`

### 5.8 Counters & Timers thÃªm trong v4

| Metric | Loáº¡i | MÃ´ táº£ |
|---|---|---|
| `llm_calls` | counter | Má»—i láº§n `_llm_enrich_cnch` Ä‘Æ°á»£c invoke |
| `cnch_llm_extracted` | counter | LLM tráº£ vá» items > 0 |
| `cnch_llm_fallback` | counter | LLM call nÃ©m exception, dÃ¹ng regex káº¿t quáº£ |
| `stage_narrative_arrays` | timer | ToÃ n bá»™ thá»i gian Stage 1 narrative arrays |

### 5.9 Enrichment settlement gate â€” Aggregation consistency

> **Váº¥n Ä‘á» gá»‘c:** Enrichment lÃ  *eventual mutation system* â€” LLM mutate state document má»™t cÃ¡ch async, nondeterministic, retryable. Náº¿u aggregate cháº¡y khi job A enriched cÃ²n job B chÆ°a, report tuáº§n sáº½ inconsistent: má»™t sá»‘ vá»¥ CNCH cÃ³ 8 fields Ä‘áº§y Ä‘á»§, sá»‘ khÃ¡c chá»‰ cÃ³ regex skeleton.

**Giáº£i phÃ¡p â€” 3 Ä‘iá»ƒm fix Ä‘á»“ng thá»i trong `AggregationService.aggregate()`:**

**1. Settlement gate (block aggregation khi enrichment chÆ°a xong):**

```python
unsettled = [j for j in jobs
             if j.enrichment_status in (EnrichmentStatus.PENDING, EnrichmentStatus.RUNNING)]
if unsettled:
    raise ProcessingError(
        f"{len(unsettled)} job(s) still have enrichment in-flight. "
        "Wait for enrichment to settle before aggregating."
    )
```

Tráº¡ng thÃ¡i settled = `ENRICHED | FAILED | SKIPPED | None(legacy)`. Chá»‰ cáº§n enrichment dá»«ng láº¡i (dÃ¹ thÃ nh cÃ´ng hay tháº¥t báº¡i) thÃ¬ má»›i cho aggregate.

**2. DÃ¹ng `final_data` thay vÃ¬ `extracted_data` trá»±c tiáº¿p:**

```python
# TrÆ°á»›c (sai â€” bá» qua enriched_data hoÃ n toÃ n):
row = rd or job.extracted_data

# Sau (Ä‘Ãºng â€” merge theo priority chain):
row = job.final_data   # reviewed > (extracted+enriched) > extracted
```

**3. Per-job enrichment audit trail ghi vÃ o `_metadata`:**

```json
"_metadata": {
  "enrichment_summary": {
    "stage1+stage2": 5,   // â† 5 jobs Ä‘Æ°á»£c LLM enrich Ä‘áº§y Ä‘á»§
    "stage1_only":   2,   // â† 2 jobs enrichment FAILED, dÃ¹ng regex
    "reviewed":      0
  },
  "enrichment_partial": false,  // true náº¿u mix giá»¯a stage1+stage2 vÃ  stage1_only
  "enrichment_audit": [
    {"job_id": "abc12345", "enrichment_status": "enriched",  "data_source": "stage1+stage2"},
    {"job_id": "def67890", "enrichment_status": "failed",    "data_source": "stage1_only"},
    ...
  ]
}
```

`enrichment_partial: true` lÃ  warning flag â€” report váº«n Ä‘Æ°á»£c táº¡o (vÃ¬ `FAILED` Ä‘Ã£ settled) nhÆ°ng UI cÃ³ thá»ƒ hiá»‡n cáº£nh bÃ¡o "má»™t sá»‘ vá»¥ CNCH cÃ³ thá»ƒ thiáº¿u thÃ´ng tin chi tiáº¿t".

**Káº¿t quáº£ sau fix â€” cÃ¡c trÆ°á»ng há»£p xá»­ lÃ½:**

| Tráº¡ng thÃ¡i enrichment lÃºc aggregate | HÃ nh vi |
|---|---|
| Táº¥t cáº£ `ENRICHED` | Aggregate bÃ¬nh thÆ°á»ng, `enrichment_partial=false` |
| Mix `ENRICHED` + `FAILED` | Aggregate bÃ¬nh thÆ°á»ng, `enrichment_partial=true`, audit trail Ä‘áº§y Ä‘á»§ |
| Táº¥t cáº£ `FAILED` | Aggregate bÃ¬nh thÆ°á»ng, dÃ¹ng Stage 1 regex data, `enrichment_partial=false` |
| Táº¥t cáº£ `SKIPPED` | Aggregate bÃ¬nh thÆ°á»ng (khÃ´ng cÃ³ CNCH text), `enrichment_partial=false` |
| Báº¥t ká»³ job nÃ o `PENDING` hoáº·c `RUNNING` | **Raise ProcessingError** â€” yÃªu cáº§u caller Ä‘á»£i |

### 5.10 Acceptance criteria (cáº­p nháº­t)

| YÃªu cáº§u | CÃ¡ch Ä‘Ã¡p á»©ng |
|---|---|
| Document dÃ¹ng Ä‘Æ°á»£c khi Ollama táº¯t | `extracted_data` luÃ´n Ä‘Æ°á»£c ghi trong Stage 1 |
| Report khÃ´ng bao giá» inconsistent | Settlement gate block aggregate khi enrichment in-flight |
| Audit trail cho má»—i report | `_metadata.enrichment_audit` ghi nguá»“n data tá»«ng job |
| Throughput khÃ´ng bá»‹ áº£nh hÆ°á»Ÿng khi LLM cháº­m | Stage 1 worker tráº£ vá» ngay; enrichment pool riÃªng |
| LLM = optimization layer | `FAILED` settled â†’ aggregate dÃ¹ng Stage 1 data, `enrichment_partial=true` |

### 5.11 Ghi chÃº kiáº¿n trÃºc â€” Two-field vs Single state machine

**Thiáº¿t káº¿ hiá»‡n táº¡i (two-field model)** Ä‘Æ°á»£c chá»n vÃ¬ lÃ½ do báº£o thá»§: khÃ´ng Ä‘á»¥ng vÃ o `status` enum hiá»‡n táº¡i, trÃ¡nh break táº¥t cáº£ filter query (`WHERE status='extracted'`) vÃ  API response schema. Tuy nhiÃªn nÃ³ táº¡o ra trade-off rÃµ rÃ ng.

**Thiáº¿t káº¿ thay tháº¿ (single linear state machine)** sáº½ sáº¡ch hÆ¡n:

```
UPLOAD â†’ EXTRACTED â†’ ENRICHMENT_PENDING
              â†“ (async)
         ENRICHED | ENRICH_FAILED | ENRICH_SKIPPED   (== SETTLED)
              â†“
         READY_FOR_REVIEW
              â†“              â†“
          APPROVED       REJECTED
              â†“
          AGGREGATED
              â†“
          EXPORTED
```

| TiÃªu chÃ­ | Two-field (v4 hiá»‡n táº¡i) | Single state machine |
|---|---|---|
| Query "job sáºµn sÃ ng review?" | `status='extracted' AND enrichment_status NOT IN ('pending','running')` | `status='ready_for_review'` |
| Settlement gate trong aggregate() | Manual check `enrichment_status` | `status NOT IN ('enrichment_pending', 'running')` |
| Cross-reference trong UI | Pháº£i Ä‘á»c 2 field | 1 field |
| Backward compat hybrid mode | `enrichment_status` = NULL â†’ transparent | Hybrid tá»± chuyá»ƒn `EXTRACTED â†’ ENRICH_SKIPPED â†’ READY_FOR_REVIEW` |
| `AGGREGATED` / `EXPORTED` tracking | KhÃ´ng cÃ³ | Explicit, queryable |
| Chi phÃ­ refactor | ÄÃ£ done | Pháº£i Ä‘á»•i enum + táº¥t cáº£ filter query + migration |

**Náº¿u muá»‘n migrate lÃªn single state machine:** Ä‘á»•i `ExtractionJobStatus` enum, cáº­p nháº­t táº¥t cáº£ `WHERE status=...` query trong `job_service.py` / `aggregation_service.py` / API endpoints / tests, sau Ä‘Ã³ xÃ³a `enrichment_status` column (hoáº·c giá»¯ Ä‘á»ƒ backward compat query).

---

## 6. BÆ°á»›c 2: RÃ¢y lá»c & Ã‰p kiá»ƒu (Validation Layer)

**File:** `app/services/data_validator.py`

> **LÆ°u Ã½ kiáº¿n trÃºc hiá»‡n táº¡i:** Hybrid pipeline máº·c Ä‘á»‹nh Ä‘ang Ã©p output báº±ng Pydantic + RuleEngine.
> `DataValidator` váº«n lÃ  lá»›p chuáº©n hÃ³a quan trá»ng cho flow schema-driven/legacy vÃ  cÃ³ thá»ƒ tÃ¡i sá»­ dá»¥ng á»Ÿ táº§ng review.

### 5.1 Class DataValidator

```python
validator = DataValidator(schema_definition)
clean_data, report = validator.validate(raw_llm_output)
```

### 5.2 Ã‰p kiá»ƒu (Type Coercion)

#### Sá»‘ (Number)

| Input (LLM tráº£ vá») | Output (sau validate) | Ghi chÃº |
|---|---|---|
| `"Hai vá»¥"` | `2` | Vietnamese text â†’ number |
| `"1,500,000"` | `1500000` | US thousand separator |
| `"1.500.000"` | `1500000` | VN/EU thousand separator |
| `"1.500.000,50"` | `1500000.5` | VN decimal format |
| `"12.5%"` | `12.5` | Percentage |
| `"500 VNÄ"` | `500` | Strip currency suffix |
| `"má»™t"` | `1` | Vietnamese word |
| `"triá»‡u"` | `1000000` | Vietnamese word |
| `15` | `15` | Already correct, no change |

**Supported Vietnamese number words:** khÃ´ng(0), má»™t(1), hai(2), ba(3), bá»‘n(4), nÄƒm(5), sÃ¡u(6), báº£y(7), tÃ¡m(8), chÃ­n(9), mÆ°á»i(10), hai mÆ°Æ¡i(20)...chÃ­n mÆ°Æ¡i(90), trÄƒm(100), nghÃ¬n/ngÃ n(1000), triá»‡u(1M), tá»·(1B)

#### Boolean

| Input | Output |
|---|---|
| `"Ä‘Ãºng"`, `"cÃ³"`, `"rá»“i"`, `"x"`, `"âœ“"`, `"true"`, `"yes"`, `"1"` | `true` |
| `"sai"`, `"khÃ´ng"`, `"chÆ°a"`, `"false"`, `"no"`, `"0"` | `false` |

#### NgÃ y thÃ¡ng (Date Normalization)

Táº¥t cáº£ â†’ chuáº©n **DD/MM/YYYY**:

| Input | Output |
|---|---|
| `"02-03-2026"` | `"02/03/2026"` |
| `"2026-03-02"` (ISO) | `"02/03/2026"` |
| `"02.03.2026"` | `"02/03/2026"` |
| `"ngÃ y 2 thÃ¡ng 3 nÄƒm 2026"` | `"02/03/2026"` |

**Auto-detect date fields:** Nháº­n diá»‡n field lÃ  ngÃ y báº±ng tÃªn: `ngay_*`, `date_*`, `thoi_gian`, `tu_ngay`, `den_ngay`, `ky_bao_cao`, `period`...

### 5.3 Array-of-Object Validation

Má»—i pháº§n tá»­ trong máº£ng Ä‘Æ°á»£c coerce riÃªng theo sub-field type:

```json
// Input (LLM tráº£ ra):
{"danh_sach": [{"loai": "ChÃ¡y", "so_nguoi": "ba"}, {"loai": "Ná»•", "so_nguoi": "5 ngÆ°á»i"}]}

// Output (sau validate):
{"danh_sach": [{"loai": "ChÃ¡y", "so_nguoi": 3}, {"loai": "Ná»•", "so_nguoi": 5}]}
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
      "original": "Hai vá»¥",
      "coerced": 2,
      "note": "\"Hai vá»¥\" â†’ 2 (Vietnamese text)"
    },
    {
      "field": "ngay_bao_cao",
      "original": "02-03-2026",
      "coerced": "02/03/2026",
      "note": "\"02-03-2026\" â†’ \"02/03/2026\""
    }
  ],
  "missing_fields": ["dia_chi_cu_the"],
  "extra_fields": ["ghi_chu_them"]
}
```

Report Ä‘Æ°á»£c lÆ°u vÃ o `confidence_scores._validation_report` trong `extraction_jobs`.

### 5.5 Vá»‹ trÃ­ trong Pipeline

```python
# extraction_service.py â†’ run_extraction() â†’ step 5.5
from app.services.data_validator import DataValidator

validator = DataValidator(template.schema_definition)
clean_data, validation_report = validator.validate(result["extracted_data"])

# Store VALIDATED data (NOT raw LLM output)
job.extracted_data = clean_data
job.confidence_scores["_validation_report"] = validation_report
```

---

## 7. BÆ°á»›c 3: XÃ o náº¥u dá»¯ liá»‡u (Aggregation & Map-Reduce)

**File:** `app/services/aggregation_service.py`

### 6.1 Flow

```
N approved jobs â†’ load final_data â†’ pd.json_normalize() â†’ apply rules â†’ AggregationReport
```

### 6.2 Aggregation Methods

| Method | MÃ´ táº£ | VÃ­ dá»¥ |
|---|---|---|
| `SUM` | Cá»™ng tá»•ng | `so_vu` ngÃ y 1 + ngÃ y 2 + ngÃ y 3 |
| `AVG` | Trung bÃ¬nh | `nhiet_do` trung bÃ¬nh tuáº§n |
| `MAX` | GiÃ¡ trá»‹ lá»›n nháº¥t | `so_nguoi` cao nháº¥t |
| `MIN` | GiÃ¡ trá»‹ nhá» nháº¥t | `nhiet_do` tháº¥p nháº¥t |
| `COUNT` | Äáº¿m sá»‘ báº£n ghi | Tá»•ng sá»‘ bÃ¡o cÃ¡o |
| `CONCAT` | Ná»‘i máº£ng | Gá»™p `danh_sach_su_co` 7 ngÃ y â†’ 1 list |
| `LAST` | Láº¥y giÃ¡ trá»‹ cuá»‘i | `ten_nguoi_ky` láº¥y báº£n ghi cuá»‘i |

### 6.3 Aggregation Rules Format

```json
{
  "rules": [
    {"output_field": "tong_so_vu", "source_field": "so_vu", "method": "SUM", "label": "Tá»•ng sá»‘ vá»¥"},
    {"output_field": "tb_nhiet_do", "source_field": "nhiet_do", "method": "AVG", "round_digits": 1, "label": "Nhiá»‡t Ä‘á»™ TB"},
    {"output_field": "tat_ca_su_co", "source_field": "danh_sach_su_co", "method": "CONCAT", "label": "Tá»•ng há»£p sá»± cá»‘"},
    {"output_field": "nguoi_ky", "source_field": "ten_nguoi_ky", "method": "LAST", "label": "NgÆ°á»i kÃ½"}
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
  "tat_ca_su_co": [{"loai": "ChÃ¡y", ...}, {"loai": "Ná»•", ...}, ...],
  "nguoi_ky": "Nguyá»…n VÄƒn A",
  "records": [/* summary record phá»¥c vá»¥ Word render */],
  "_source_records": [/* raw data tá»« tá»«ng job */],
  "_flat_records": [/* pd.json_normalize flattened */],
  "_metadata": {
    "total_jobs": 7,
    "total_data_rows": 7,
    "generated_at": "2026-03-10T08:00:00",
    "template_name": "BÃ¡o cÃ¡o PCCC",
    "template_version": 3
  }
}
```

### 6.5 Pandas json_normalize

Nested JSON Ä‘Æ°á»£c Ä‘áº­p pháº³ng tá»± Ä‘á»™ng:

```python
# Input:
[{"a": 1, "detail": {"x": 10, "y": 20}}, ...]

# pd.json_normalize output:
#   a  detail_x  detail_y
#   1       10        20
```

Káº¿t quáº£ lÆ°u trong `_flat_records` Ä‘á»ƒ export dá»… dÃ ng.

### 6.6 Export Formats

| Format | Class/Method | MÃ´ táº£ |
|---|---|---|
| **Excel** | `ExportService.to_excel()` | 3 sheets: Summary, Detail, Metadata |
| **CSV** | `ExportService.to_csv()` | Field/Value format |
| **JSON** | Direct return | Raw aggregated_data |
| **Word** | `build_word_export_context()` + `render_word_template()` | Xem BÆ°á»›c 4 |

---

## 8. BÆ°á»›c 4: BÆ¡m khuÃ´n Word (Headless Document Export)

**File:** `app/services/word_export.py`
**ThÆ° viá»‡n:** `docxtpl` (Jinja2 for .docx)

### 7.1 Flow

```
Word Template (.docx vá»›i {{...}})  +  Aggregated JSON  â†’  docxtpl render  â†’  File .docx hoÃ n chá»‰nh
```

Render context hiá»‡n Ä‘Æ°á»£c build á»Ÿ táº§ng aggregation qua `build_word_export_context(...)` rá»“i má»›i truyá»n vÃ o renderer.

### 7.2 CÃº phÃ¡p Template

#### Biáº¿n Ä‘Æ¡n giáº£n

```
ÄÆ¡n vá»‹ bÃ¡o cÃ¡o: {{ten_don_vi}}
NgÃ y: {{today}}
Tá»•ng sá»‘ vá»¥: {{tong_so_vu}}
```

#### Custom Filters

| Filter | Input | Output |
|---|---|---|
| `{{val \| number_vn}}` | `1500000` | `1.500.000` |
| `{{val \| date_vn}}` | `"02/03/2026"` | `"ngÃ y 02 thÃ¡ng 03 nÄƒm 2026"` |
| `{{val \| date_short}}` | `"2026-03-02"` | `"02/03/2026"` |
| `{{val \| default_if_none("N/A")}}` | `None` | `"N/A"` |

#### Loop báº£ng (trong Word Table)

```
HÃ ng 1: {% for row in records %}
HÃ ng 2: {{row.loai_su_co}}  |  {{row.so_nguoi}}  |  {{row.ngay_xay_ra}}
HÃ ng 3: {% endfor %}
```

#### Äiá»u kiá»‡n

```
{% if tong_so_vu > 0 %}CÃ³ {{tong_so_vu}} sá»± cá»‘{% else %}KhÃ´ng cÃ³ sá»± cá»‘{% endif %}
```

### 7.3 Biáº¿n tá»± Ä‘á»™ng inject

| Biáº¿n | GiÃ¡ trá»‹ | Ghi chÃº |
|---|---|---|
| `{{today}}` | `"10/03/2026"` | NgÃ y hiá»‡n táº¡i DD/MM/YYYY |
| `{{now}}` | `"10/03/2026 08:30"` | NgÃ y giá» hiá»‡n táº¡i |
| `{{metadata}}` | object | Di chuyá»ƒn tá»« `_metadata` lÃªn top-level |
| `{{metadata.template_name}}` | string | TÃªn template |
| `{{report_name}}` | string | TÃªn report |
| `{{total_jobs}}` | int | Sá»‘ job Ä‘Ã£ aggregate |
| `{{approved_jobs}}` | int | Sá»‘ job approved |

### 7.4 Hardening & Production safety

- Anti zip-bomb trÆ°á»›c khi parse docx:
  - `MAX_TEMPLATE_INPUT_BYTES = 50MB`
  - `MAX_DOCX_MEMBER_UNCOMPRESSED_BYTES = 50MB`
  - `MAX_DOCX_TOTAL_UNCOMPRESSED_BYTES = 120MB`
  - `MAX_DOCX_ENTRIES = 2000`
  - `MAX_DOCX_COMPRESSION_RATIO = 150`
- Tiá»n xá»­ lÃ½ Jinja tag báº±ng XML parser (`ElementTree`) thay vÃ¬ regex-only trÃªn raw XML.
- Lá»—i render/template Ä‘Æ°á»£c chain nguyÃªn nhÃ¢n báº±ng `raise ... from e` Ä‘á»ƒ giá»¯ traceback.

**NOTE triá»ƒn khai:** cÃ¡c giá»›i háº¡n anti zip-bomb nÃ y **khÃ´ng cÃ³ sáºµn** trong `docxtpl`/`python-docx`. Cáº§n cÃ³ lá»›p interceptor dÃ¹ng `zipfile` Ä‘á»ƒ duyá»‡t entry vÃ  kiá»ƒm tra `file_size` (uncompressed), tá»•ng dung lÆ°á»£ng giáº£i nÃ©n vÃ  tá»‰ lá»‡ nÃ©n trÆ°á»›c khi chuyá»ƒn bytes sang `DocxTemplate`.

### 7.5 API Usage

```bash
# Upload .docx template + render vá»›i report data
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
    schema_definition  JSONB NOT NULL,          -- Äá»‹nh nghÄ©a fields
    aggregation_rules  JSONB DEFAULT '{}',       -- Rules tá»•ng há»£p
    version         INTEGER DEFAULT 1,           -- Auto-bump khi schema thay Ä‘á»•i
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
    batch_id        UUID,                        -- NhÃ³m batch
    extraction_mode VARCHAR(20) DEFAULT 'standard' NOT NULL,  -- standard|vision|fast|block

    -- State machine: pending â†’ processing â†’ extracted â†’ approved
    --                                      â†˜ failed     â†˜ rejected
    status          VARCHAR(20) DEFAULT 'pending' NOT NULL,

    -- Stage 1 â€” AI output (deterministic, khÃ´ng cÃ³ LLM trong block mode)
    extracted_data     JSONB,
    confidence_scores  JSONB,                    -- Bao gá»“m _validation_report
    source_references  JSONB,
    debug_traces       JSONB,

    -- Stage 2 â€” LLM enrichment (async, Ä‘á»™c láº­p vá»›i Stage 1)
    -- enriched_data KHÃ”NG BAO GIá»œ overwrite extracted_data
    -- final_data property merge: reviewed > (extracted+enriched) > extracted
    enrichment_status    VARCHAR(20),            -- pending|running|enriched|failed|skipped|NULL(legacy)
    enriched_data        JSONB,                  -- {"danh_sach_cnch": [...]} â€” chá»‰ chá»©a LLM-filled fields
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

**Migration cho DB cÅ© (cháº¡y má»™t láº§n):**
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
    aggregated_data JSONB NOT NULL,              -- Káº¿t quáº£ tá»•ng há»£p
    total_jobs      INTEGER NOT NULL,
    approved_jobs   INTEGER NOT NULL,
    status          VARCHAR(20) DEFAULT 'draft', -- draft|finalized
    created_by      UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at      TIMESTAMP DEFAULT NOW(),
    finalized_at    TIMESTAMP
);
```

  ```sql
  -- Optional (chá»‰ báº­t khi cÃ³ nghiá»‡p vá»¥ query/filter trá»±c tiáº¿p trÃªn aggregated_data)
  -- CREATE INDEX idx_aggregation_reports_data_gin ON aggregation_reports USING GIN (aggregated_data);
  ```

### 9.4 Job State Machine

> **Thiáº¿t káº¿ hiá»‡n táº¡i (v4): two-field model.**
> `job.status` = tráº¡ng thÃ¡i chÃ­nh cá»§a job lifecycle.
> `job.enrichment_status` = tráº¡ng thÃ¡i riÃªng cá»§a LLM enrichment (block mode only).
>
> **Trade-off so vá»›i single state machine:**
> Two-field giá»¯ backward compat vá»›i hybrid mode vÃ  trÃ¡nh Ä‘á»•i táº¥t cáº£ query filter hiá»‡n táº¡i. NhÆ°á»£c Ä‘iá»ƒm: UI vÃ  aggregate gate pháº£i cross-reference 2 field Ä‘á»ƒ biáº¿t job "sáºµn sÃ ng review" chÆ°a. Xem tháº£o luáº­n kiáº¿n trÃºc táº¡i Section 5.11.

**`job.status` â€” main lifecycle:**

```
          create_job()
              â”‚
              â–¼
        â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
        â”‚ PENDING  â”‚
        â””â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”˜
             â”‚ Celery picks up
             â–¼
        â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
        â”‚  PROCESSING  â”‚
        â””â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”˜
           â”‚       â”‚
     successâ”‚     errorâ”‚
           â–¼       â–¼
    â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â” â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”
    â”‚ EXTRACTED â”‚ â”‚ FAILED â”‚â—„â”€â”€â”€â”€ retry_job() resets to PENDING
    â””â”€â”€â”¬â”€â”€â”€â”€â”€â”¬â”€â”€â”˜ â””â”€â”€â”€â”€â”€â”€â”€â”€â”˜     (retry_count++)
       â”‚     â”‚
       â”‚     â”‚  [Block mode: enrichment cháº¡y async â€” xem job.enrichment_status]
       â”‚     â”‚  [Hybrid mode: khÃ´ng cÃ³ enrichment, cÃ³ thá»ƒ approve ngay]
       â”‚     â”‚
 approveâ”‚   rejectâ”‚
       â–¼     â–¼
 â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â” â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
 â”‚ APPROVED â”‚ â”‚ REJECTED â”‚â—„â”€â”€â”€â”€ retry_job() resets to PENDING
 â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜ â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
       â”‚
       â”‚ aggregate()
       â”‚ [gate: táº¥t cáº£ enrichment_status pháº£i settled trÆ°á»›c khi aggregate]
       â–¼
 â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
 â”‚ AggregationReport   â”‚
 â”‚ (draft â†’ finalized) â”‚
 â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

**`job.enrichment_status` â€” block mode enrichment lifecycle:**

```
  (Stage 1 complete, chi_tiet_cnch cÃ³ text)   â†’  PENDING
  (Stage 1 complete, chi_tiet_cnch rá»—ng)      â†’  SKIPPED
  (hybrid/non-block mode)                      â†’  SKIPPED
  enrich_job_task picked up                   â†’  RUNNING
  LLM call thÃ nh cÃ´ng, items > 0              â†’  ENRICHED
  LLM call thÃ nh cÃ´ng, items = []             â†’  SKIPPED
  LLM call tháº¥t báº¡i (sau max 3 retries)       â†’  FAILED   â† job váº«n EXTRACTED, dÃ¹ng Ä‘Æ°á»£c
  NULL                                         â†’  legacy job (pre-v4, khÃ´ng cÃ³ enrichment)
```

**"Job sáºµn sÃ ng cho review" = Ä‘iá»u kiá»‡n:**
```python
job.status == "extracted"
AND job.enrichment_status NOT IN ("pending", "running")
# (hoáº·c enrichment_status IS NULL cho legacy jobs)
```

**Enrichment settlement = Ä‘iá»u kiá»‡n cho phÃ©p aggregate:**
```python
# Táº¥t cáº£ jobs pháº£i thá»a:
job.enrichment_status NOT IN ("pending", "running")
# ENRICHED | FAILED | SKIPPED | NULL Ä‘á»u lÃ  "settled"
```

---

## 10. API Reference â€” 25 Endpoints

**Router prefix:** `/api/v1/extraction`
**Tags:** `Extraction Templates`, `Extraction Jobs`, `Extraction Reports`

### 10.1 Word Scanner

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/templates/scan-word` | `get_current_user` | Upload .docx â†’ auto-infer schema |

**Request:** `multipart/form-data` â€” `file` (.docx) + `use_llm` (bool, default true)
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
| `POST` | `/templates` | `require_admin` | 201 | Táº¡o template má»›i |
| `GET` | `/templates` | `require_viewer` | 200 | List templates (paginated) |
| `GET` | `/templates/{template_id}` | `require_viewer` | 200 | Chi tiáº¿t template |
| `PATCH` | `/templates/{template_id}` | `require_admin` | 200 | Sá»­a template (schema change â†’ version++) |
| `DELETE` | `/templates/{template_id}` | `RoleChecker("owner")` | 204 | Soft delete |

### 10.3 Jobs

| Method | Path | Auth | Status | Description |
|---|---|---|---|---|
| `POST` | `/jobs` | `require_admin` | 202 | Upload 1 PDF + táº¡o job â†’ Celery |
| `POST` | `/jobs/batch` | `require_admin` | 202 | Upload N PDFs (max 20) â†’ N Celery jobs phÃ¢n tÃ¡n |
| `POST` | `/jobs/batch-block` | `require_admin` | 200 | Batch block-mode in-process parallel (ThreadPoolExecutor) |
| `POST` | `/jobs/from-document` | `require_admin` | 202 | Táº¡o job tá»« document Ä‘Ã£ upload |
| `GET` | `/jobs` | `require_viewer` | 200 | List jobs (filter: status, template_id, batch_id) |
| `GET` | `/jobs/{job_id}` | `require_viewer` | 200 | Polling endpoint |
| `GET` | `/jobs/batch/{batch_id}/status` | `require_viewer` | 200 | Batch progress |
| `GET` | `/metrics` | `require_viewer` | 200 | Global pipeline extraction metrics (counters + timers) |
| `POST` | `/jobs/{job_id}/retry` | `require_admin` | 200 | Retry failed/rejected |
| `DELETE` | `/jobs/{job_id}` | `require_admin` | 204 | XÃ³a job Ä‘Ã£ hoÃ n táº¥t |

### 10.4 Review

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/review/{job_id}/approve` | `require_admin` | Approve (+ optional `reviewed_data`) |
| `POST` | `/review/{job_id}/reject` | `require_admin` | Reject (required `notes`) |

### 10.5 Aggregation & Export

| Method | Path | Auth | Status | Description |
|---|---|---|---|---|
| `POST` | `/aggregate` | `require_admin` | 201 | Gom N jobs â†’ 1 report |
| `GET` | `/aggregate` | `require_viewer` | 200 | List reports |
| `GET` | `/aggregate/{report_id}` | `require_viewer` | 200 | Chi tiáº¿t report |
| `DELETE` | `/aggregate/{report_id}` | `require_admin` | 204 | XÃ³a report |
| `GET` | `/aggregate/{report_id}/export` | `require_viewer` | 200 | Export Excel/CSV/JSON (query: `?format=excel`) |
| `POST` | `/aggregate/{report_id}/export-word` | `require_viewer` | 200 | Upload .docx template â†’ render â†’ download |
| `GET` | `/aggregate/{report_id}/export-word-auto` | `require_viewer` | 200 | DÃ¹ng template Ä‘Ã£ lÆ°u trong S3 Ä‘á»ƒ render |

## 11. Cáº¥u hÃ¬nh (Configuration)

**File:** `app/core/config.py` â†’ class `Settings`

| Setting | Type | Default | Env Override | MÃ´ táº£ |
|---|---|---|---|---|
| `OLLAMA_BASE_URL` | str | `"http://localhost:11434"` | `OLLAMA_BASE_URL` | Endpoint Ollama server |
| `OLLAMA_API_KEY` | str | `"ollama"` | `OLLAMA_API_KEY` | API key (placeholder cho local Ollama) |
| `OLLAMA_MODEL` | str | `"qwen2.5:7b"` | `OLLAMA_MODEL` | Model dÃ¹ng cho Hybrid pipeline |
| `GEMINI_API_KEY` | str | `""` | `GEMINI_API_KEY` | DÃ¹ng cho module khÃ¡c (Engine 1/optional) |
| `GEMINI_FLASH_MODEL` | str | `"gemini-2.5-flash"` | `GEMINI_FLASH_MODEL` | Cáº¥u hÃ¬nh tÆ°Æ¡ng thÃ­ch legacy |
| `GEMINI_PRO_MODEL` | str | `"gemini-2.5-flash"` | `GEMINI_PRO_MODEL` | Cáº¥u hÃ¬nh tÆ°Æ¡ng thÃ­ch legacy |
| `EXTRACTION_MAX_TOKENS` | int | `65536` | â€” | Giá»›i háº¡n token cho flow extraction legacy |
| `EXTRACTION_TEMPERATURE` | float | `0.0` | â€” | Temperature (deterministic) |
| `DEFAULT_EXTRACTION_MODE` | str | `"standard"` | â€” | Mode máº·c Ä‘á»‹nh cá»§a API |
| `EXTRACTION_MAX_RETRIES` | int | `3` | â€” | Celery retry tá»‘i Ä‘a |
| `EXTRACTION_TIMEOUT_MINUTES` | int | `30` | â€” | Timeout cho stuck jobs |
| `EXTRACTION_BATCH_MAX_FILES` | int | `20` | â€” | Max files/batch |
| `HYBRID_MAX_RETRIES` | int | `3` | `HYBRID_MAX_RETRIES` | Retry logic-level trong Hybrid pipeline |
| `HYBRID_MANUAL_REVIEW_DIR` | str | `"Needs_Manual_Review"` | `HYBRID_MANUAL_REVIEW_DIR` | NÆ¡i lÆ°u metadata file cáº§n xá»­ lÃ½ tay |
| `CONFIDENCE_HIGH` | float | `0.85` | â€” | NgÆ°á»¡ng confidence cao cho UI |
| `CONFIDENCE_MEDIUM` | float | `0.50` | â€” | NgÆ°á»¡ng confidence trung bÃ¬nh cho UI |

**Docker Compose defaults (tham kháº£o):**
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
    """Pipeline: load job â†’ S3 download â†’ orchestrator.run() â†’ persist."""
```

- **Queue:** `extraction` | **Concurrency:** 4 | **Prefetch:** 1
- **Block mode:** gá»i `run_stage1_from_bytes()` â†’ `persist_stage1_result()` â†’ dispatch `enrich_job_task`
- **Non-block mode:** gá»i `run_from_bytes()` â†’ `persist_pipeline_result()` (unchanged)
- **Retry:** Exponential backoff (30s â†’ 60s â†’ 120s + jitter), max 3 láº§n, chá»‰ retry transient errors
- **Failure:** Sau max retries â†’ `status = failed`, `error_message` ghi láº¡i

### 12.2 enrich_job_task *(v4 má»›i)*

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
    """Stage 2: Ä‘á»c chi_tiet_cnch â†’ gá»i LLM â†’ ghi enriched_data."""
```

- **Queue:** `enrichment` | **Concurrency:** 2 | **Soft time limit:** 180s
- Chá»‰ retry khi transient error (timeout, connection reset). Validation error / empty text â†’ khÃ´ng retry
- LuÃ´n safe-fail: náº¿u lá»—i sau max retries, `enrichment_status = FAILED`, `extracted_data` khÃ´ng bá»‹ áº£nh hÆ°á»Ÿng
- Guard: skip náº¿u `enrichment_status NOT IN (PENDING, FAILED)` â€” idempotent

### 12.3 cleanup_stuck_jobs

```python
@shared_task(name="cleanup_stuck_extraction_jobs")
def cleanup_stuck_jobs():
    """Periodic: tÃ¬m jobs stuck á»Ÿ 'processing' > 30 phÃºt â†’ mark 'failed'."""
```

- Cháº¡y bá»Ÿi **Celery Beat** má»—i 30 phÃºt
- Timeout: `settings.EXTRACTION_TIMEOUT_MINUTES` (default 30 phÃºt)

### 12.4 Celery queue routing

```python
task_routes = {
    "app.infrastructure.worker.tasks.process_document_task":       {"queue": "document_processing"},
    "app.infrastructure.worker.tasks.generate_embeddings_task":    {"queue": "embeddings"},
    "app.infrastructure.worker.extraction_tasks.extract_document_task": {"queue": "extraction"},
    "app.infrastructure.worker.enrichment_tasks.enrich_job_task":  {"queue": "enrichment"},
}
```

### 12.5 Docker Compose â€” Worker services

| Service | Queue | Concurrency | Má»¥c Ä‘Ã­ch |
|---|---|---|---|
| `celery-extraction-worker` | `extraction` | 4 | Stage 1 deterministic, táº£i PDF, parse |
| `celery-enrichment-worker` | `enrichment` | 2 | Stage 2 LLM enrichment (giá»›i háº¡n song song Ollama) |
| `celery-worker` | `default`, `document_processing`, `embeddings` | 4 | RAG, embeddings, general tasks |
| `celery-beat` | â€” | â€” | Scheduler (cleanup tasks) |

---

## 13. Word Template Scanner

**File:** `app/services/word_scanner.py`

### 12.1 Flow

```
.docx upload â†’ Regex scan {{...}} â†’ Type inference â†’ Table structure â†’ (optional) LLM refine â†’ Output
```

### 12.2 Scan Targets

| VÃ¹ng | PhÆ°Æ¡ng phÃ¡p |
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
| Máº·c Ä‘á»‹nh | `string` |

### 12.4 Table-aware Detection

Khi placeholder náº±m TRONG báº£ng Word:
1. Äá»c header row â†’ extract column names
2. Chuyá»ƒn thÃ nh array-of-object schema
3. Infer sub-field types báº±ng prefix matching (`so_*` â†’ number, `ten_*` â†’ string)
4. (Optional) Gá»i Gemini Flash refine types

### 12.5 Aggregation Rules Auto-generate

| Field type | Auto-generated rule |
|---|---|
| `number` | `SUM` |
| `array` | `CONCAT` |

---

## 14. Pydantic Schemas (Request/Response)

**File:** `app/schemas/extraction_schema.py`

### 13.1 Schema Validation

| Model | MÃ´ táº£ |
|---|---|
| `FieldDefinition` | 1 field: `name` (snake_case), `type` (string\|number\|boolean\|array\|object), `description`, `items` (cho array), `fields` (cho object) |
| `SchemaDefinition` | `{"fields": [FieldDefinition...]}` â€” requires unique names |
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

| Model | Fields chÃ­nh |
|---|---|
| `TemplateResponse` | id, name, schema_definition, aggregation_rules, version, is_active |
| `JobResponse` | id, status, extraction_mode, extracted_data, confidence_scores, reviewed_data, llm_model, processing_time_ms |
| `BatchCreateResponse` | batch_id, total_files, jobs[] |
| `BatchStatusResponse` | total, pending, processing, extracted, approved, failed, progress_percent |
| `AggregateResponse` | id, name, aggregated_data, total_jobs, approved_jobs, status |

---

## 15. Phase 3 â€” Template-driven Â· Dynamic Columns Â· Batch Parallel Â· Observability

### 14.1 YAML Template System

> **NguyÃªn táº¯c: Zero hardcode â€” má»i regex, keyword, threshold Ä‘á»u náº±m trong file YAML.**

**Files:**
- `app/templates/pccc.yaml` â€” template PCCC (55+ patterns)
- `app/business/template_loader.py` â€” `DocumentTemplate` wrapper + registry

#### Kiáº¿n trÃºc

```
app/templates/
â””â”€â”€ pccc.yaml           â† file YAML chá»©a toÃ n bá»™ pattern nghiá»‡p vá»¥

app/business/
â””â”€â”€ template_loader.py  â† DocumentTemplate (typed wrapper) + load_template() + lru_cache
```

#### DocumentTemplate class

`DocumentTemplate` bá»c dict YAML thÃ nh typed properties:

```python
tpl = load_template("pccc")

tpl.template_id          # "pccc"
tpl.narrative_start_re   # re.Pattern â€” compiled regex
tpl.date_long_form_re    # re.Pattern
tpl.date_period_markers  # list[str]
tpl.unit_patterns        # list[str]
tpl.incident_row_patterns_spaced   # list[re.Pattern]
tpl.incident_row_patterns_compact  # list[re.Pattern]
tpl.year_range           # (int, int)
tpl.max_ket_qua          # int
tpl.non_negative_fields  # list[str]
tpl.extraction_prompt("header")    # str â€” system prompt cho block
# ... 40+ properties tá»•ng cá»™ng
```

#### YAML Structure (pccc.yaml)

```yaml
id: pccc
name: "BÃ¡o cÃ¡o PCCC ngÃ y"
version: 1

block_detection:
  narrative_start_pattern: "..."
  table_anchor_pattern: "..."

prompts:
  header: "TrÃ­ch xuáº¥t header..."
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

Táº¥t cáº£ module sau Ä‘á»u nháº­n `tpl: DocumentTemplate | None`:

| Module | HÃ m | TrÆ°á»›c | Sau |
|---|---|---|---|
| `block_extraction_pipeline.py` | `__init__()` | Hardcode 55+ regex | `self.tpl.*` |
| `extractors.py` | `extract_metadata_from_header()` | Hardcode regex | `tpl.report_number_primary_re` |
| `validators.py` | `validate_business()` | Hardcode constants | `tpl.year_range`, `tpl.max_ket_qua` |
| `engine.py` | `run_business_rules()` | KhÃ´ng cÃ³ tpl | Truyá»n `tpl=` xuá»‘ng táº¥t cáº£ extractors/validators |
| `block_business_workflow.py` | `__init__()` | KhÃ´ng cÃ³ template | `self.tpl` â†’ pipeline + payload |

### 14.2 Dynamic Column Detection

Thay vÃ¬ giáº£ Ä‘á»‹nh cá»™t cá»‘ Ä‘á»‹nh `[0]=STT, [1]=Ná»™i dung, [2]=Káº¿t quáº£`, pipeline parser giá» **quÃ©t header row** Ä‘á»ƒ xÃ¡c Ä‘á»‹nh column index:

```python
# Trong _parse_bang_thong_ke_from_tables()
for idx, cell in enumerate(header_row):
    upper = cell.upper()
    if any(kw in upper for kw in ["STT", "Sá» TT"]):
        col_stt = idx
    elif any(kw in upper for kw in ["Káº¾T QUáº¢", "Sá» LIá»†U", "THá»°C HIá»†N"]):
        col_kq = idx
    elif any(kw in upper for kw in ["Ná»˜I DUNG", "CHá»ˆ TIÃŠU"]):
        col_nd = idx
```

Keywords Ä‘Æ°á»£c load tá»« `tpl.column_detection_keywords("stt" | "noi_dung" | "ket_qua")`.

Khi detect thÃ nh cÃ´ng â†’ `metrics.inc("dynamic_col_detected")`.

### 14.3 Batch Parallel Pipeline

**File:** `app/services/batch_extraction.py`

Cháº¡y block pipeline song song trÃªn N PDF files **in-process** (khÃ´ng qua Celery):

```python
from app.services.batch_extraction import BatchItem, run_batch

items = [BatchItem("file1.pdf", bytes1), BatchItem("file2.pdf", bytes2), ...]
result = run_batch(items, max_workers=2)

result.total        # 5
result.succeeded    # 4
result.failed       # 1
result.results      # list[dict] â€” payload má»—i file
result.errors       # list[{"filename": ..., "error": ...}]
result.metrics      # batch-level counters/timers
```

#### TÃ­nh nÄƒng

| TÃ­nh nÄƒng | MÃ´ táº£ |
|---|---|
| **ThreadPoolExecutor** | Song song N files, máº·c Ä‘á»‹nh `EXTRACTION_BATCH_MAX_FILES // 2` (cap 4) |
| **Backpressure** | Items vÆ°á»£t `EXTRACTION_BATCH_MAX_FILES` bá»‹ reject ngay vá»›i error `"backpressure: queue full"` |
| **Per-item metrics** | Má»—i item cÃ³ `batch_item` timer |
| **Batch counters** | `batch_total`, `batch_succeeded`, `batch_failed` |
| **Directory mode** | `run_batch_from_directory("/path/to/pdfs/")` â€” quÃ©t táº¥t cáº£ `*.pdf` |

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

Má»—i láº§n cháº¡y pipeline táº¡o 1 instance `PipelineMetrics`:

```python
metrics = PipelineMetrics()

metrics.inc("llm_calls")                    # counter += 1
metrics.inc("llm_calls", 3)                 # counter += 3

with metrics.timer("stage1_layout"):        # context manager â€” tá»± tÃ­nh elapsed_ms
    do_layout_stuff()

metrics.to_dict()
# {"counters": {"llm_calls": 4, ...}, "timers_ms": {"stage1_layout": 1234.5, ...}}
```

#### Counters Ä‘Æ°á»£c track

| Counter | Khi nÃ o tÄƒng |
|---|---|
| `llm_calls` | Má»—i láº§n gá»i LLM (extract block) |
| `llm_extract_fallback` | LLM tráº£ rá»—ng â†’ dÃ¹ng fallback |
| `schema_enforcer_reask` | Schema enforcer pháº£i há»i láº¡i LLM |
| `narrative_fallback` | Regex fallback cho pháº§n nghiá»‡p vá»¥ |
| `dynamic_col_detected` | Dynamic column detection thÃ nh cÃ´ng |
| `pipeline_success` | Pipeline káº¿t thÃºc thÃ nh cÃ´ng |
| `pipeline_failure` | Pipeline káº¿t thÃºc tháº¥t báº¡i |

#### Timers Ä‘Æ°á»£c track

| Timer | Äo cÃ¡i gÃ¬ |
|---|---|
| `stage1_layout` | PDF â†’ reconstructed text + tables |
| `stage2_detect` | Block detection |
| `stage3_extract` | LLM extraction + schema enforcement |
| `stage3_header_llm` | Header LLM call riÃªng |
| `stage6_business` | Business rules engine |

#### GlobalMetrics (thread-safe aggregator)

```python
from app.core.metrics import global_metrics

# Má»—i pipeline run tá»± merge vÃ o global:
global_metrics.merge(per_run_metrics)

# API endpoint tráº£ vá» tá»•ng há»£p:
# GET /api/v1/extraction/metrics
global_metrics.to_dict()
# {"counters": {"llm_calls": 150, "pipeline_success": 42, ...}, "timers_ms": {...}}

global_metrics.reset()  # Reset khi cáº§n
```

---

## 16. Cáº¥u trÃºc Source Code

```
app/
â”œâ”€â”€ api/v1/
â”‚   â”œâ”€â”€ document.py
â”‚   â”œâ”€â”€ extraction.py
â”‚   â”œâ”€â”€ templates.py
â”‚   â”œâ”€â”€ jobs.py
â”‚   â”œâ”€â”€ aggregation.py
â”‚   â”œâ”€â”€ rag.py
â”‚   â”œâ”€â”€ auth.py
â”‚   â””â”€â”€ tenant.py
â”œâ”€â”€ application/
â”‚   â”œâ”€â”€ aggregation_service.py   # flatten_block_output + build_word_export_context
â”‚   â”œâ”€â”€ auth_service.py
â”‚   â”œâ”€â”€ doc_service.py
â”‚   â”œâ”€â”€ extraction_service.py    # Backward-compat facade
â”‚   â”œâ”€â”€ job_service.py           # â˜… JobManager: persist_stage1_result, persist_enrichment_result (v4)
â”‚   â”œâ”€â”€ review_service.py
â”‚   â””â”€â”€ template_service.py
â”œâ”€â”€ core/
â”‚   â”œâ”€â”€ config.py
â”‚   â”œâ”€â”€ constants.py
â”‚   â”œâ”€â”€ exceptions.py
â”‚   â”œâ”€â”€ logger.py
â”‚   â”œâ”€â”€ logging.py
â”‚   â”œâ”€â”€ security.py
â”‚   â””â”€â”€ tracing.py
â”œâ”€â”€ domain/
â”‚   â”œâ”€â”€ models/
â”‚   â”‚   â”œâ”€â”€ document.py
â”‚   â”‚   â”œâ”€â”€ extraction_job.py  # â˜… ExtractionJob, ExtractionJobStatus, EnrichmentStatus (v4)
â”‚   â”‚   â”œâ”€â”€ tenant.py
â”‚   â”‚   â””â”€â”€ user.py
â”‚   â”œâ”€â”€ rules/
â”‚   â”‚   â”œâ”€â”€ engine.py          # run_business_rules() â€” RuleEngine domain checks
â”‚   â”‚   â”œâ”€â”€ extractors.py      # Regex-based deterministic extractors (accepts tpl)
â”‚   â”‚   â””â”€â”€ normalizers.py     # Vietnamese word spacing + date normalization
â”‚   â””â”€â”€ templates/
â”‚       â””â”€â”€ template_loader.py # DocumentTemplate wrapper + YAML registry + lru_cache
â”œâ”€â”€ engines/
â”‚   â””â”€â”€ extraction/
â”‚       â”œâ”€â”€ block_pipeline.py      # â˜… BlockExtractionPipeline (PDF two-stage)
â”‚       â”‚                          #    - run_stage1_from_bytes() â€” no LLM (v4)
â”‚       â”‚                          #    - run_from_bytes()        â€” legacy, full pipeline
â”‚       â”‚                          #    - _llm_enrich_cnch()      â€” LLM method duy nháº¥t (v4)
â”‚       â”œâ”€â”€ extractors.py          # OllamaInstructorExtractor, GeminiExtractor...
â”‚       â”œâ”€â”€ hybrid_pipeline.py    # HybridExtractionPipeline + PipelineResult (chi_tiet_cnch v4)
â”‚       â”œâ”€â”€ orchestrator.py        # â˜… ExtractionOrchestrator.run() â€” two-stage dispatch (v4)
â”‚       â”œâ”€â”€ schemas.py             # BlockExtractionOutput, CNCHItem (8 fields), CNCHListOutput...
â”‚       â””â”€â”€ rag/                   # Engine 1 RAG pipeline
â”œâ”€â”€ infrastructure/
â”‚   â”œâ”€â”€ db/
â”‚   â”‚   â””â”€â”€ session.py
â”‚   â”œâ”€â”€ llm/
â”‚   â”œâ”€â”€ storage/
â”‚   â””â”€â”€ worker/
â”‚       â”œâ”€â”€ celery_app.py       # â˜… Queue routing: extraction + enrichment (v4)
â”‚       â”œâ”€â”€ enrichment_tasks.py # â˜… enrich_job_task â€” Stage 2 LLM (v4, file má»›i)
â”‚       â”œâ”€â”€ extraction_tasks.py # extract_document_task â€” Stage 1 dispatch
â”‚       â””â”€â”€ tasks.py            # RAG + general tasks
â”œâ”€â”€ schemas/
â”‚   â”œâ”€â”€ auth_schema.py
â”‚   â”œâ”€â”€ doc_schema.py
â”‚   â”œâ”€â”€ extraction_schema.py
â”‚   â””â”€â”€ rag_schema.py
â””â”€â”€ utils/
    â”œâ”€â”€ debug_trace.py
    â”œâ”€â”€ file_utils.py
    â”œâ”€â”€ metrics.py             # â˜… PipelineMetrics + GlobalMetrics (thread-safe)
    â”œâ”€â”€ pdf_utils.py
    â”œâ”€â”€ word_export.py         # Secure docxtpl renderer (anti zip-bomb)
    â””â”€â”€ word_scanner.py        # Word template scanner â†’ auto-generate schema

scripts/
â”œâ”€â”€ migrate_add_enrichment_columns.py  # â˜… Idempotent SQL migration cho 5 enrichment columns (v4)
â””â”€â”€ ...

app/domain/templates/
â””â”€â”€ pccc.yaml                  # YAML extraction template (55+ externalized patterns)

â˜… = thÃªm hoáº·c thay Ä‘á»•i lá»›n trong v4
```

---

## 17. VÃ­ dá»¥ End-to-End

### Scenario: 7 BÃ¡o cÃ¡o PCCC NgÃ y â†’ 1 BÃ¡o cÃ¡o Tuáº§n Word

#### Step 1: QuÃ©t file Word máº«u â†’ táº¡o Template

```bash
# Upload Word template máº«u cÃ³ {{so_vu_chay}}, {{ngay_bao_cao}}, báº£ng {{danh_sach_su_co}}
curl -X POST "http://localhost:8000/api/v1/extraction/templates/scan-word" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@bao_cao_pccc_mau.docx" \
  -F "use_llm=true"

# Response: schema_definition + aggregation_rules (auto-generated)
```

```bash
# Táº¡o template tá»« káº¿t quáº£ scan
curl -X POST "http://localhost:8000/api/v1/extraction/templates" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "BÃ¡o cÃ¡o PCCC NgÃ y",
    "schema_definition": { "fields": [...] },
    "aggregation_rules": { "rules": [...] }
  }'
# â†’ template_id
```

#### Step 2: Upload 7 PDF bÃ¡o cÃ¡o ngÃ y

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
# â†’ batch_id + 7 job_ids
```

#### Step 3: Poll status

```bash
curl "http://localhost:8000/api/v1/extraction/jobs/batch/$BATCH_ID/status" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID"
# â†’ {"total": 7, "extracted": 7, "progress_percent": 100.0}
```

#### Step 4: Review (xem extracted payload + approve)

```bash
# Xem káº¿t quáº£ extraction
curl "http://localhost:8000/api/v1/extraction/jobs/$JOB_ID" ...
# â†’ extracted_data, confidence_scores (status + attempts)

# Approve tá»«ng job
curl -X POST "http://localhost:8000/api/v1/extraction/review/$JOB_ID/approve" \
  -d '{"notes": "OK"}' ...
```

#### Step 5: Aggregate (BÆ°á»›c 3)

```bash
curl -X POST "http://localhost:8000/api/v1/extraction/aggregate" \
  -H "Content-Type: application/json" \
  -d '{
    "template_id": "'$TEMPLATE_ID'",
    "job_ids": ["job1", "job2", ..., "job7"],
    "report_name": "PCCC Tuáº§n 10"
  }' ...
# â†’ report_id + aggregated_data (SUM, CONCAT applied)
```

#### Step 6: Export Word (BÆ°á»›c 4)

```bash
# Upload Word template tuáº§n + render
curl -X POST "http://localhost:8000/api/v1/extraction/aggregate/$REPORT_ID/export-word" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -F "file=@bao_cao_tuan_template.docx" \
  --output bao_cao_tuan_10.docx

# â†’ File Word hoÃ n chá»‰nh, viá»n báº£ng nÃ©t cÄƒng 100% nhÆ° báº£n gá»‘c
```

#### Káº¿t quáº£

```
ðŸ“„ bao_cao_tuan_10.docx
â”œâ”€â”€ {{ten_don_vi}}     â†’ "PhÃ²ng PCCC Quáº­n 1"
â”œâ”€â”€ {{tong_so_vu}}     â†’ 45 (SUM 7 ngÃ y)
â”œâ”€â”€ {{ngay_bao_cao}}   â†’ "ngÃ y 10 thÃ¡ng 03 nÄƒm 2026"
â”œâ”€â”€ Báº£ng sá»± cá»‘         â†’ 45 hÃ ng (CONCAT 7 ngÃ y)
â””â”€â”€ {{nguoi_ky}}       â†’ "Äáº¡i tÃ¡ Nguyá»…n VÄƒn A" (LAST)
```

---

> **TÃ i liá»‡u nÃ y Ä‘Æ°á»£c cáº­p nháº­t láº§n cuá»‘i: 03/04/2026**
> **PhiÃªn báº£n 4.0 â€” Two-Stage Block Pipeline:** Stage 1 deterministic (no LLM) + Stage 2 LLM enrichment async Â· EnrichmentStatus state machine Â· enriched_data column tÃ¡ch biá»‡t Â· enrich_job_task trÃªn queue riÃªng Â· celery-enrichment-worker (concurrency=2) Â· migrate_add_enrichment_columns.py
> **Tá»•ng source code Engine 2:** kiáº¿n trÃºc split-router/application/domain Â· 25 endpoints Â· 3 báº£ng DB Â· 12 JSONB columns (7 gá»‘c + 5 enrichment) Â· 3 GIN indexes cá»‘t lÃµi (+1 enrichment_status partial index) Â· YAML template system Â· PipelineMetrics + GlobalMetrics Â· Batch parallel pipeline
