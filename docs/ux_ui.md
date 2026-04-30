# 🎨 UI/UX Documentation — Frontend v2.1

**Last Updated:** 2026-04-28
**Tech Stack:** Next.js 14 (App Router), React 18, TypeScript, Tailwind CSS, Radix UI, shadcn/ui
**Design Philosophy:** Data-first, Template-isolated, Source-independent, Deterministic, Auditable

---

## 📊 1. Current State Assessment (2026-04-28)

### Implemented ✅ (previously "proposed" in roadmap)

| Component | Status | File |
|----------|--------|------|
| `CalendarGrid` (shared) | ✅ Done | `components/extraction/calendar-grid.tsx` |
| `VirtualTable` (TanStack) | ✅ Done | `components/ui/virtual-table.tsx` |
| `TableSkeleton` | ✅ Done | `components/ui/table-skeleton.tsx` |
| `Skeleton` primitive | ✅ Done | `components/ui/skeleton.tsx` |
| `Inspect` tab in extraction | ✅ Done | `app/extraction/page.tsx` (tab 5) |
| `Inspect` standalone page | ✅ Done | `app/extraction/inspect/page.tsx` |
| Sheet selector in Inspector | ✅ Done | `sheet-inspector.tsx` (BC NGÀY, CNCH, CHI VIỆN, VỤ CHÁY) |
| Calendar view in Inspector | ✅ Done | `sheet-inspector.tsx` → `CalendarTab` |
| Grid view (STT coverage) | ✅ Done | `sheet-inspector.tsx` → `GridTab` |
| Issues tab | ✅ Done | `sheet-inspector.tsx` → `IssuesTab` |
| Mapping tab | ✅ Done | `sheet-inspector.tsx` → `MappingTab` |
| Export tab (Calendar + Template) | ✅ Done | `components/extraction/export-tab.tsx` |
| CalendarPicker (report creation) | ✅ Done | `components/extraction/calendar-picker.tsx` |

### NOT Implemented Yet ❌

| Component | Proposed In | Priority |
|-----------|-------------|----------|
| `Split-pane Review` | Phase 2.1 | 🔥 High |
| Bulk approve/reject/delete | Phase 1.2 | 🔥 High |
| `BulkActionBar` | Phase 1.2 | 🔥 High |
| `StatusFilterBar` (shared) | Phase 9.1 | 🔥 High |
| `JsonEditor` (CodeMirror) | Phase 2.4 | ⚡ Medium |
| `EmptyState` component | Phase 3.6 | ⚡ Medium |
| `FilterBuilder` | Phase 4.2 | 🔵 Long |
| Settings page | Phase 4.1 | 🔵 Long |
| Template tags + duplicate | Phase 3.3 | 🔵 Long |
| Export history page | Phase 3.2 | ⚡ Medium |
| Keyboard shortcuts system | Phase 3.1 | ⚡ Medium |
| WebSocket real-time | Phase 5.2 | 🔵 Long |

### FE Files Not Matching Docs

| Issue | In ux_ui.md | Actual FE |
|-------|------------|-----------|
| Sheet Inspector table | "uses custom HTML table" | ✅ Uses shadcn/ui `Table` |
| `review-split-pane.tsx` | Listed in file structure | ❌ Does not exist |
| `export-unified.tsx` | Listed in file structure | ❌ Does not exist |
| `mobile-nav.tsx` | Listed in file structure | ❌ Does not exist |
| `use-polling.ts` | Listed in lib/hooks | ❌ Does not exist |
| `use-keyboard.ts` | Listed in lib/hooks | ❌ Does not exist |
| `use-sidebar.ts` | Listed in lib/hooks | ❌ Does not exist |
| `review-split-pane.tsx` | Proposed component | ❌ Not built |
| `export-unified.tsx` | Proposed component | ❌ Not built |
| `status-filter-bar.tsx` | Proposed component | ❌ Not built |
| `bulk-action-bar.tsx` | Proposed component | ❌ Not built |
| `filter-builder.tsx` | Proposed component | ❌ Not built |
| `export-history/page.tsx` | Proposed page | ❌ Not built |
| `settings/page.tsx` | Proposed page | ❌ Not built |
| `lib/constants.ts` | ✅ Created — STATUS_VI, statusBadgeVariant, JOB_STATUSES | — |
| STATUS_VI duplicated | "extract to lib/constants.ts" | ✅ Resolved — moved to `lib/constants.ts` |

---

## 📋 2. Immediate Action Items

### Week 1: Foundation (CRITICAL)

1. **Extract `lib/constants.ts`** (⚡ 1 day)
   - STATUS_VI, statusBadgeVariant from jobs-tab, review-tab, export-tab
   - Remove duplicate code in all tabs

2. **Add `aria-label`** to all icon-only buttons (⚡ 1 day)
   - JobsTab, ReviewTab, ExportTab all have unlabeled icon buttons

3. **Add skip-to-content link** (⚡ 1 day)
   - Add `sr-only` link at top of extraction/page.tsx

4. **Bulk operations in Review Tab** (🔥 3 days) — **HIGHEST PRIORITY**
   - Add checkboxes to Review table
   - Create `BulkActionBar` component (sticky bottom)
   - `bulkApprove()`, `bulkReject()`, `bulkDelete()` API calls

### Week 2: UX Polish

5. **Split-pane Review redesign** (🔥🔥 1 week)
   - Replace current push-down panel with 40/60 split
   - `ReviewSplitPane` component

6. **Add `EmptyState` component** (⚡ 1 day)
   - Replace hardcoded "Chưa có..." text in all tabs

7. **Sheet Inspector: Make rows clickable** (⚡ 2 days)
   - Issues tab rows → open job in Review tab

8. **Add `parser_used` badge** in Jobs table (⚡ 1 day)
   - Show "PDF" vs "Sheets" for each job

---

## 🔧 3. Technical Debt

### Duplicated Code — Resolved

```
jobs-tab.tsx         → imports from lib/constants.ts ✅
review-tab.tsx       → imports from lib/constants.ts ✅
export-tab.tsx       → imports from lib/constants.ts ✅
sheet-inspector.tsx  → has inline status helpers (intentional — scoped use)
calendar-picker.tsx  → has inline dayStatus() helpers (intentional — scoped use)
```

**STATUS_VI and statusBadgeVariant** are now sourced from `lib/constants.ts`. Backend canonical source: `app/domain/workflow.py:JobStatus`.

### Magic Strings Still Present

| Location | Magic String | Should Be |
|----------|-------------|----------|
| jobs-tab.tsx:48 | `"Chưa có công việc nào"` | `EMPTY_JOBS` |
| review-tab.tsx | `"Chưa có hồ sơ nào"` | `EMPTY_REVIEW` |
| export-tab.tsx | `"Chưa có báo cáo nào"` | `EMPTY_REPORTS` |
| jobs-tab.tsx | `max-h-72` | CSS variable |
| review-tab.tsx | `max-h-48` | CSS variable |

---

## 🗺️ 4. Updated File Structure (v2.1)

```
frontend/
├── app/
│   ├── layout.tsx              # Root layout (Sidebar + main)
│   ├── page.tsx               # Dashboard ✅
│   ├── login/page.tsx         # Auth
│   ├── documents/page.tsx     # Document list
│   └── extraction/
│       ├── page.tsx           # Main engine (5 tabs) ✅
│       │                       # Tabs: templates | jobs | review | inspect | export
│       └── inspect/
│           └── page.tsx       # Sheet Inspector (standalone) ✅
│
├── components/
│   ├── layout/
│   │   └── sidebar.tsx        # Navigation + tenant selector ✅
│   │
│   ├── extraction/
│   │   ├── templates-tab.tsx  # Template management ✅
│   │   ├── jobs-tab.tsx       # Upload + job list ✅
│   │   ├── review-tab.tsx      # Review workflow (push-down panel) ❌
│   │   │                       # TODO: Replace with split-pane ❌
│   │   ├── export-tab.tsx      # Report aggregation (Calendar + Template) ✅
│   │   ├── calendar-picker.tsx # Calendar picker + report creation ✅
│   │   ├── calendar-grid.tsx   # Shared calendar grid (generic) ✅
│   │   ├── sheet-inspector.tsx # QA tool (4 tabs) ✅
│   │   ├── pipeline-indicator.tsx # Pipeline status ✅
│   │   │                       # TODO: Add bulk-action-bar.tsx ❌
│   │   └── job-actions.tsx     # Dropdown actions per job ✅
│   │
│   └── ui/                    # shadcn/ui components ✅
│       ├── virtual-table.tsx   # TanStack virtual scroll ✅
│       ├── skeleton.tsx        # Skeleton primitive ✅
│       └── table-skeleton.tsx  # Table skeleton ✅
│       # TODO: empty-state.tsx ❌
│       # TODO: json-editor.tsx (CodeMirror) ❌
│       # TODO: status-filter-bar.tsx ❌
│       # TODO: bulk-action-bar.tsx ❌
│
├── lib/
│   ├── api.ts                  # API wrapper (tenant header) ✅
│   ├── types.ts               # TypeScript interfaces ✅
│   ├── utils.ts               # Helpers (formatDate, downloadBlob) ✅
│   ├── auth.ts                # Auth context ✅
│   │   # TODO: constants.ts (STATUS_VI, statusBadgeVariant) ✅ RESOLVED — use frontend/lib/constants.ts
│   │   # TODO: hooks/use-polling.ts ❌
│   │   # TODO: hooks/use-keyboard.ts ❌
│   │   # TODO: hooks/use-sidebar.ts ❌
│   └── i18n.ts                # TODO: extract hardcoded Vietnamese strings ❌
│
└── tailwind.config.ts
```

**Legend:** ✅ = exists and used | ❌ = proposed but not built | ~~strikethrough~~ = removed

---

## ✅ 5. Implemented Component Reference

### CalendarGrid ✅

Reusable, generic calendar component. Shared between Export tab (CalendarPicker) and Sheet Inspector (CalendarTab).

```tsx
import { CalendarGrid } from "@/components/extraction/calendar-grid";

<CalendarGrid
  days={calendarDays}
  onSelectDay={handleSelect}
  selectedDay={selectedDate}
  showHeader={true}
  showLegend={true}
/>
```

**File:** `components/extraction/calendar-grid.tsx`
**Type:** Generic `CalendarGrid<T extends { date: string }>`

### VirtualTable ✅

TanStack-powered virtualized table for 1000+ rows.

```tsx
import { VirtualTable } from "@/components/ui/virtual-table";

<VirtualTable
  data={jobs}
  columns={columns}
  rowHeight={40}
  overscan={20}
  onRowClick={handleRowClick}
/>
```

**File:** `components/ui/virtual-table.tsx`

### TableSkeleton ✅

Loading placeholder for tables.

```tsx
import { TableSkeleton } from "@/components/ui/table-skeleton";

<TableSkeleton rows={5} columns={4} />
```

**File:** `components/ui/table-skeleton.tsx`

---

## 🚧 6. Proposed Components (Not Built)

### BulkActionBar (PROPOSED)

Sticky bottom bar for bulk operations in Review tab.

```tsx
// File: components/extraction/bulk-action-bar.tsx
interface BulkActionBarProps {
  count: number;
  onApprove: () => void;
  onReject: () => void;
  onDelete: () => void;
  onClear: () => void;
}

<BulkActionBar
  count={selectedJobIds.size}
  onApprove={() => bulkApprove(selectedJobIds)}
  onReject={() => bulkReject(selectedJobIds)}
  onDelete={() => bulkDelete(selectedJobIds)}
  onClear={() => setSelectedJobIds(new Set())}
/>
```

### StatusFilterBar (PROPOSED)

Shared status filter component for Jobs + Review tabs.

```tsx
// File: components/extraction/status-filter-bar.tsx
interface StatusFilterBarProps {
  value: string;
  onChange: (status: string) => void;
  options?: { value: string; label: string }[];
}

<StatusFilterBar value={status} onChange={setStatus} />
```

### EmptyState (PROPOSED)

Reusable empty state for all tabs.

```tsx
// File: components/ui/empty-state.tsx
interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
}

<EmptyState
  icon={<FileText />}
  title="Chưa có hồ sơ nào"
  description="Upload hồ sơ để bắt đầu"
  action={<Button>Upload ngay</Button>}
/>
```

---

## 📱 7. Responsive Status

| Screen | Status | Issue |
|--------|--------|-------|
| Desktop (>1024px) | ✅ Works | — |
| Tablet (768-1024px) | ⚠️ Partial | Tables overflow, sidebar fixed |
| Mobile (<768px) | ❌ Broken | No hamburger menu, sidebar covers content |

---

## 🎨 8. Design Principles

| Principle | Definition | Status |
|-----------|------------|--------|
| **Data-first** | Show extracted data prominently, templates are config only | ✅ Applied |
| **Template Isolation** | Word templates are S3 keys, not parsed in UI | ✅ Applied |
| **Source Independence** | UI shows parser_used badge, doesn't change workflow | ✅ Applied |
| **Deterministic** | Job data immutable; edits tracked separately | ✅ Applied |
| **Auditability** | Source references kept, changes tracked | ⚠️ Partial |

---

## 📚 9. References

### API Endpoints Used

| Feature | Endpoint | Method |
|---------|----------|--------|
| Templates | `GET /api/v1/templates` | List |
| Templates | `POST /api/v1/templates` | Create |
| Jobs | `GET /api/v1/jobs` | List |
| Jobs | `POST /api/v1/jobs/upload` | Upload PDF |
| Jobs | `POST /api/v1/jobs/ingest-sheet` | Sheets |
| Jobs | `POST /api/v1/jobs/:id/retry` | Retry |
| Jobs | `DELETE /api/v1/jobs/:id` | Delete |
| Review | `POST /api/v1/review/:id/approve` | Approve |
| Review | `POST /api/v1/review/:id/reject` | Reject |
| Reports | `GET /api/v1/reports` | List |
| Reports | `POST /api/v1/reports` | Create |
| Reports | `GET /api/v1/reports/:id/export` | Export |
| Sheets | `GET /api/v1/sheets/inspect/by-date` | QA data |
| Sheets | `GET /api/v1/sheets/inspect/issues` | Issues |
| Dashboard | `GET /api/v1/dashboard` | Metrics |
| Auth | `POST /api/v1/auth/login` | Login |

---

## Sheet Pipeline Cleanup (2026-04-28)

### Deleted Sheet Pipeline Files
No Sheet Pipeline-specific files were deleted. All Sheet Pipeline components remain active.

### Created
| File | Reason |
|------|--------|
| `frontend/lib/constants.ts` | ✅ Created — exports `STATUS_VI`, `statusBadgeVariant`, `JOB_STATUSES`, `JobStatusValue`. Imported by `jobs-tab.tsx` and `review-tab.tsx`. |

### Fixed (non-breaking)
| Location | Before | After |
|----------|--------|--------|
| `sheet-inspector.tsx:34` | SHEETS label: `"VỤ CHÁY"` | `"VỤ CHÁY THỐNG KÊ"` (matches Excel sheet name) |

### Preserved Active Pieces
- `app/extraction/inspect/page.tsx` — standalone inspect page
- `app/extraction/page.tsx` — Tab 5 (Inspect) embeds `SheetInspector`
- `components/extraction/sheet-inspector.tsx` — 4 tabs: Calendar, Grid, Mapping, Issues
- `CalendarGrid` — shared by Sheet Inspector (CalendarTab)
- `CalendarPicker` — used only by Export tab (not shared with Sheet Pipeline)
- `api.sheets.inspect/issues/mapping` — Sheet inspection API calls
- `api.jobs.ingestGoogleSheet` — Sheet ingestion entry point
- `waitForIngestionTask` — polling helper in jobs-tab and templates-tab
- `GRID_STTS` — hard-coded STT list for BC NGÀY grid view

### Intentionally Not Removed
| Item | Reason |
|------|--------|
| `legacy` fields in templates-tab (`google_sheet_worksheet`, `google_sheet_schema_path`) | Still referenced in template list items — removing would break template-level ingestion |
| `handleIngestTemplate` in templates-tab.tsx | Uses legacy fields but is a separate entry point from jobs-tab |
| `waitForIngestionTask` in jobs-tab.tsx | Active polling function for batch status |

### Uncertain — Requires Human Review
| Item | Question |
|------|----------|
| `ColumnMappingRow` in `types.ts` | Only consumed by MappingTab; could be moved inline to sheet-inspector if types.ts is later pruned |
| `SheetIssue` interface | Only used by Sheet Inspector; if inspector is later simplified, this may become stale |
| `GRID_STTS` hard-coded array | Does it reflect the actual STT list in the database? If bc_ngay_schema.yaml `stt_map` keys change, this needs updating |
| `handleIngestTemplate` legacy path in templates-tab | Backend may not support the legacy single-worksheet ingestion path; could be dead code on the server side |

### Pre-existing TypeScript Errors (NOT caused by cleanup)
These errors existed before any changes and are unrelated to Sheet Pipeline cleanup:
- `CalendarGrid.getMonthName(month, year)` — `getMonthName` in `utils.ts` only accepts 1 arg
- `export-tab.tsx` — `downloadBlob` not imported, `report_name` typo
- `review-tab.tsx` — various `possibly undefined` state issues
- `templates-tab.tsx` — `stats` property on `ScanWordResult` type
- `sheet-inspector.tsx` — null-safety in `renderDay` callback

---

## Sheet Pipeline Follow-up (2026-04-28)

### GRID_STTS vs bc_ngay_schema.yaml stt_map

**Schema `stt_map` keys:** 61 entries ("1" through "61")
**Frontend `GRID_STTS`:** 12 curated entries (intentionally excludes sub-rows)

| Key | Frontend Label | Schema `noi_dung` | Status |
|-----|---------------|-------------------|--------|
| `2` | STT 2 - Vụ cháy | "1. Tổng số vụ cháy" | ✅ |
| `14` | STT 14 - CNCH | "3. Tổng số vụ tai nạn, sự cố" | ✅ |
| `22` | STT 22 - Tin bài MXH | "1.1 Tuyên truyền qua MXH" | ✅ |
| `31` | STT 31 - Tổng kiểm tra | "Số cơ sở được kiểm AT PCCC" | ✅ |
| `32` | STT 32 - Định kỳ | "Kiểm tra định kỳ" | ✅ |
| `33` | STT 33 - Đột xuất | "Kiểm tra đột xuất theo chuyên đề" | ✅ |
| `43` | STT 43 - PA PC06 | "Số PA được xây dựng và phê duyệt" | ✅ |
| `47` | STT 47 - ~~PA PC08~~ | Section 3.2 → should be **PA PC07** | ⚠️ Fixed |
| `50` | STT 50 - ~~PA PC09~~ | Section 3.3 → should be **PA PC08** | ⚠️ Fixed |
| `55` | STT 55 - CBCS HL | "Tổng số CBCS tham gia huấn luyện" | ✅ |
| `60` | STT 60 - Lái xe | "Chiến sĩ nghĩa vụ" | ✅ |
| `61` | STT 61 - Lái tàu | "Lái tàu CC và CNCH" | ✅ |

**Fixed:** STT 47 desc "PA PC08" → "PA PC07", STT 50 desc "PA PC09" → "PA PC08".
**Note:** GRID_STTS is a curated subset. Sub-rows (STT 3-13, 15-21, 23-30, 34-42, 44-46, 48-49, 51-54, 56-59) are intentionally excluded for readability.

### handleIngestTemplate Legacy Path

**Backend:** `app/api/v1/ingestion.py` — `POST /api/v1/extraction/jobs/ingest/google-sheet`
- ✅ **Active and supported**
- Legacy single-field path (`body.worksheet` + `body.schema_path`) explicitly handled at lines 92-99
- Falls back to template's `google_sheet_worksheet` + `google_sheet_schema_path` when request fields absent
- `require_admin` role enforced

**Frontend:** `templates-tab.tsx:270` — `handleIngestTemplate(templateId)`
- ✅ **Active** — button visible when template has all legacy fields
- Calls `POST /api/v1/extraction/jobs/ingest/google-sheet`
- Polls via `api.jobs.getBatchStatus(batchId)` → Celery `AsyncResult` (correct for task IDs)
- **Conclusion:** Not dead code. Both frontend and backend fully support the legacy path.

### TypeScript Errors Fixed (2026-04-28)

| File | Line | Error | Fix |
|------|------|-------|-----|
| `sheet-inspector.tsx` | 177 | `getMonthName(month, year)` — takes 1 arg | Removed `year` |
| `sheet-inspector.tsx` | 552,558,560 | `dayData` is `SheetInspectDay \| null` in `renderDay` | Added `!` non-null assertions |
| `calendar-grid.tsx` | 96 | `getMonthName(month, year)` — takes 1 arg | Removed `year` (pre-existing) |
| `constants.ts` | — | Missing canonical `JOB_STATUSES` list | Added `JOB_STATUSES` + `JobStatusValue` from `app/domain/workflow.py:JobStatus` |

**Status badge coverage:** `STATUS_VI` + `statusBadgeVariant` in `constants.ts` cover all 9 backend statuses sourced from `app/domain/workflow.py:JobStatus`.

**Remaining pre-existing errors (out of scope):**
- `export-tab.tsx` — `downloadBlob` not imported, `report_name` typo
- `review-tab.tsx` — `possibly undefined` state issues
- `templates-tab.tsx` — `stats`/`schema_definition`/`variables`/`aggregation_rules` missing from `ScanWordResult`
- `calendar-picker.tsx` — `report_name` property mismatch
- `app/page.tsx`, `app/documents/page.tsx` — various type mismatches

---

**END OF DOCUMENT**
