# 📱 UI/UX Design System — Doc Automation Engine

**Version:** 1.0
**Last Updated:** 2026-04-21
**Tech Stack:** Next.js 14, React 18, TypeScript, Tailwind CSS, Radix UI, shadcn/ui

---

## 📐 1. Layout & Navigation

### 1.1 Root Layout (`app/layout.tsx`)

```
┌─────────────────────────────────────────────────────────────┐
│  <html>                                                     │
│  ┌─────────┬──────────────────────────────────────────────┐ │
│  │ Sidebar │ Main Content (overflow-y-auto, bg-muted/30) │ │
│  │  (64px) │ p-6, flex-1                                 │ │
│  └─────────┴──────────────────────────────────────────────┘ │
│  </body>                                                    │
└─────────────────────────────────────────────────────────────┘
```

**Key Features:**
- Fixed sidebar (width: 16rem = 256px)
- Scrollable main content area
- Theme support (dark/light via `next-themes`)
- Multi-tenant context via `AuthProvider`
- Toast notifications (sonner) positioned top-right

### 1.2 Sidebar (`components/layout/sidebar.tsx`)

**Sections:**

1. **Logo Area** (h-16, border-b)
   - Icon: `FileText` (primary color)
   - Text: "Doc Automation"

2. **Navigation** (flex-1, overflow-y-auto, py-4)
   - Dashboard (`/`) - `LayoutDashboard` icon
   - Trích xuất dữ liệu (`/extraction`) - `Settings2` icon
   - Tài liệu (`/documents`) - `FileText` icon
   - Active state: `bg-primary text-primary-foreground`
   - Inactive: `text-muted-foreground hover:bg-accent`

3. **Bottom Panel** (border-t, p-3)
   - **Tenant Selector** (DropdownMenu)
     - Button: `Building2` icon + tenant name (truncate)
     - Dropdown: List all tenants, "Tạo tổ chức mới", "Tải lại"
     - Active tenant highlighted with `bg-accent`
   - **User Row**
     - Email (truncate, text-xs text-muted-foreground)
     - Theme Toggle (`ThemeToggle` component)
     - Logout Button (`LogOut` icon, h-8 w-8, ghost)

**Interactions:**
- Create tenant dialog (Dialog)
  - Input: Tên tổ chức
  - Buttons: Huỷ, Tạo (loading state)
- Tenant switch: Updates `tenantId` in AuthProvider, triggers data refetch

---

## 🎯 2. Extraction Page (`app/extraction/page.tsx`)

**Main Container:** Tabs component với 4 tabs:

```
┌─────────────────────────────────────────────────────────────┐
│  ⚙️ Trích xuất dữ liệu                                      │
│  ┌───────────────────────────────────────────────────────┐ │
│  │ [⚙️ Mẫu] [📤 Hồ sơ] [🔍 Duyệt] [📊 Báo cáo]         │ │
│  └───────────────────────────────────────────────────────┘ │
│  ┌───────────────────────────────────────────────────────┐ │
│  │   Tab Content (dynamic)                              │ │
│  └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 2.1 Templates Tab (`components/extraction/templates-tab.tsx`)

**Header:**
- Title: "Quản lý Mẫu"
- Subtitle: "Tạo mẫu bằng cách quét file Word hoặc nhập thủ công."
- Actions: "Làm mới" button, "Tạo mẫu mới" button

**Template List ( Accordion style):**
- Each template is a collapsible card
- Card header:
  - Chevron icon (expand/collapse)
  - Template name (font-medium, truncate)
  - Badges: `{fields.length} trường`, `{aggCount} luật`, `📝 Word` (if has template), `🎯 Auto` (if has filename_pattern)
  - Creation date (text-xs text-muted-foreground)
- Expanded content:
  - Table of fields (if fields exist)
    - Columns: Tên trường, Loại, Tổng hợp, Mô tả
  - Alert if no Word template attached
  - Actions: "Gắn Word template" / "Thay Word template", "Xoá"

**Create Dialog (max-w-3xl, max-h-[90vh], overflow-y-auto):**

**Step 1: Scan Word**
- File input (accept=".docx")
- "🔍 Scan" button (disabled nếu không có file)
- Loading: "Đang quét…"

**Step 2: Configure (after scan)**
- Stats grid (4 boxes):
  - Trường đơn (unique_variables)
  - Danh sách (array_with_object_schema)
  - Tổng trường (total_holes)
  - Vòng lặp (loop_count)
- Template name input (default = filename)
- Field Editor Table:
  - Columns: ✓ (checkbox), Tên trường, Loại (Select), Phương thức tổng hợp (Select), Mô tả (Input)
  - All fields selected by default
  - Aggregation method auto-suggested:
    - number → SUM
    - array → CONCAT
    - date/string → LAST (empty)
- "← Quét lại" button to restart

**Attach Word Dialog:**
- Target template display
- File input (.docx)
- Buttons: Huỷ, "📤 Upload & Gắn"

---

### 2.2 Jobs Tab (`components/extraction/jobs-tab.tsx`)

**Section 1: Upload**
- Card with rounded border
- Title: "📤 Nạp tài liệu"
- Alert if no templates exist
- File input (accept=".pdf", multiple, styled as button)
- Selected files count + total size (KB)
- Template override Select:
  - Default: "🔄 Tự phát hiện mẫu"
  - List all templates
- "🚀 Nộp hồ sơ" button (disabled if no files)
- Uploading state: "Đang gửi…" with spinner

**Section 2: Job List**

**Stats bar (if jobs exist):**
- 5 boxes: Tổng, Đang xử lý, Chờ duyệt, Đã duyệt, Cần xem lại

**Filters:**
- Status Select:
  - Tất cả trạng thái
  - 🔄 Đang xử lý (pending, processing, extracted, enriching)
  - ✅ Sẵn sàng duyệt (ready_for_review)
  - ✅ Đã duyệt (approved, aggregated)
  - ⚠️ Cần xem lại (failed, rejected)
- Template Select: Tất cả mẫu + individual templates

**Job Table:**
- Columns: Tên file, Mẫu, Trạng thái, Thời gian, Thao tác
- Status Badge (color-coded):
  - info: pending, processing, extracted, enriching
  - success: ready_for_review, approved
  - warning: failed
  - destructive: rejected
  - purple: aggregated
- Actions:
  - Retry button (RotateCcw) - only for failed jobs
  - Delete button (Trash2, destructive) - not for processing/pending

**Row states:**
- Hover: hover:bg-accent
- Selected: `bg-accent` (controlled by `actionJobId`)

---

### 2.3 Review Tab (`components/extraction/review-tab.tsx`)

**Header:**
- Title: "Duyệt hồ sơ trích xuất"
- "Làm mới" button

**Stats bar (5 columns):**
- Tổng hồ sơ
- Sẵn sàng duyệt
- Đã duyệt
- Đang xử lý
- Cần xem lại

**Filters:**
- Status Select (all, ready_for_review, approved, failed)
- Template Select (all + individual)
- Search Input (by filename)

**Job Table:**
- Columns: Tên file, Mẫu, Trạng thái, Thời gian
- Click row → load detail into bottom panel
- Selected row: `bg-accent`

**Detail Panel (appears below when job selected):**

**Job header:**
- File name (h3)
- Template + processing time (text-sm text-muted-foreground)
- Status Badge
- Alert if error_message exists

**Tabs:**
- **View tab** (default):
  - Alert if reviewed_data exists (showing edited version)
  - `RenderExtractedData` component:
    - Scalars: grid 2-3 cols, each box shows field name + value
    - Objects (header, phan_I_va_II...): section header + grid of fields
    - Arrays (bang_thong_ke, danh_sach_cnch, etc.): Table with all columns
- **Edit tab**:
  - Textarea (font-mono, 14 rows) with JSON
  - "✅ Kiểm tra JSON" button
  - Validation feedback (success/error toast)

**Approve/Reject Section:**
- Notes Textarea (required for reject, optional for approve)
- Buttons:
  - "✅ DUYỆT HỒ SƠ" (success, full width)
  - "❌ TỪ CHỐI" (destructive, full width)
- Help text: Trạng thái hiện tại chưa thể duyệt nếu không phải ready_for_review/extracted

---

### 2.4 Export Tab (`components/extraction/export-tab.tsx`)

**Section 1: Create Report**

Two modes via Tabs:

**A. Calendar Mode (default)**
- Uses `CalendarPicker` component (see below)
- Interactive month grid with job counts
- Select day → show jobs for that day
- Select jobs → create report

**B. Template Mode**
- Template Select (only templates with approved jobs)
- Report name Input
- Job list for selected template (with checkboxes)
- "Chọn tất cả" / "Bỏ chọn" buttons
- "📊 Tổng hợp N hồ sơ → report_name" button

**Section 2: Report List**

- Reports Select dropdown (formatted: "📑 Name (N hồ sơ · date)")
- If report selected:
  - **Info grid (4 columns):**
    - Hồ sơ gom
    - Đã duyệt
    - Luật đã áp (from `_metadata.rules_applied`)
    - Tạo lúc
  - **Aggregated data preview** (`RenderAggPreview`):
    - Scalars: grid 3-5 cols
    - Arrays: table (first 50 rows) or list (simple items)
  - **Export buttons (grid 2x4):**
    - Excel (FileSpreadsheet icon)
    - Word (auto) (FileText icon) - uses template stored in S3
    - JSON (Download icon)
    - Word (upload) - separate file input + render button
  - **Danger zone:**
    - Warning text
    - "Xoá báo cáo này" button (destructive)

---

## 📅 3. Calendar Picker (`components/extraction/calendar-picker.tsx`)

**Purpose:** Visual month calendar for selecting jobs by date to aggregate.

**State:**
- `year`, `month` (default = current)
- `days[]` (CalendarDay[] from API)
- `selectedDay` (CalendarDay | null)
- `selectedJobIds` (Set<string>)
- `selTplId`, `reportName`, `creating`

**Layout:**

```
┌─────────────────────────────────────────────────────────────┐
│  Legend: [✅ Hoàn thành] [🟡 Có hồ sơ chờ] [🔴 Có vấn đề]   │
│                                                             │
│  ┌─────────────────────┬──────────────────────────────────┐│
│  │    Calendar Grid    │   Job List Panel                ││
│  │  (7x6 grid)         │   - Selected day header         ││
│  │                     │   - Select all / Deselect all   ││
│  │                     │   - Scrollable job list        ││
│  │                     │     (checkbox + file + badge)   ││
│  └─────────────────────┴──────────────────────────────────┘│
│                                                             │
│  ┌───────────────────────────────────────────────────────┐│
│  │ Tạo báo cáo từ lịch                                  ││
│  │ [Template ▼] [Tên báo cáo          ] [Create]        ││
│  └───────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

**Calendar Grid:**
- Weekday headers: T2, T3, T4, T5, T6, T7, CN
- Day cells (h-12, rounded, hover:shadow-md hover:scale-105):
  - Background color by status:
    - complete: bg-green-100 dark:bg-green-900/40, border-green-300
    - partial: bg-yellow-100 dark:bg-yellow-900/40, border-yellow-300
    - issues: bg-red-100 dark:bg-red-900/40, border-red-300
    - empty: bg-muted/30, border-transparent
  - Selected: border-blue-600 border-2 ring-2 ring-blue-200
  - Content: day number (text-sm), job count (text-[10px])
- Loading: Skeleton cells (animate-pulse)

**Job List Panel:**
- Header: "📋 YYYY-MM-DD — N hồ sơ" + X button
- Buttons: "☑️ Chọn tất cả", "⬜ Bỏ chọn"
- List (max-h-64, overflow-y-auto):
  - Each job: checkbox + file name (truncate) + status badge + template (text-[10px])
  - Click row toggles checkbox
- Empty state: "Không có hồ sơ nào trong ngày này."

**Create Report Bar:**
- Template Select: shows templates from selected day OR all templates
- Report name Input (default: "Báo cáo {today}")
- Validation: `canCreate = selTplId && selectedJobIds.size > 0 && !creating`
- Button: "📊 Tạo báo cáo (N)" (disabled if !canCreate)

**API Calls:**
- `GET /api/v1/extraction/jobs/by-date?month=4&year=2026`
  - Returns `CalendarDay[]`: `{date, job_count, approved_count, has_issues, jobs[]}`
- Jobs in `jobs[]` have: `{id, file_name, status, template_id, created_at}`

---


## 📊 4. Common UI Patterns

### 4.1 Status Badges

**Variants (from shadcn/ui Badge):**
- `default` / `secondary` - neutral
- `success` - green (approved, complete)
- `warning` - yellow (failed, needs review)
- `destructive` - red (rejected)
- `info` - blue (processing, pending)
- `purple` - purple (aggregated)

**Vietnamese Status Labels (`STATUS_VI`):**
```typescript
{
  pending: "⏳ Đang tiếp nhận…",
  processing: "🔄 AI đang đọc tài liệu…",
  extracted: "🔄 AI đang phân tích…",
  enriching: "🔄 AI đang phân tích chi tiết…",
  ready_for_review: "✅ Sẵn sàng duyệt",
  approved: "✅ Đã duyệt",
  rejected: "🚫 Từ chối",
  failed: "⚠️ Cần xem lại",
  aggregated: "📊 Có trong báo cáo"
}
```

### 4.2 Loading States

- **Button loading:** `<Button disabled><RefreshCw className="animate-spin" /> Đang…</Button>`
- **Table loading:** Skeleton rows with `animate-pulse bg-muted`
- **Page loading:** Spinner centered with `h-5 w-5 animate-spin text-muted-foreground`

### 4.3 Error Handling

- **Toast notifications** (sonner):
  - `toast.success()` - green
  - `toast.error()` - red
  - `toast.warning()` - yellow
  - `toast.info()` - blue
- **Alert components:**
  - `variant="default"` - info
  - `variant="warning"` - yellow background
  - `variant="success"` - green
  - `variant="destructive"` - red

### 4.4 Tables

- Base: `shadcn/ui Table` component
- Responsive: `overflow-auto` wrapper
- Sticky headers: `sticky top-0 bg-background`
- Zebra striping: implicit via row hover
- Cell truncation: `truncate` class, `title` attribute for full text

### 4.5 Dialogs

- **Size variants:**
  - Default: `DialogContent` (max-w-lg)
  - Large: `max-w-3xl` (Templates create)
  - Tall: `max-h-[90vh] overflow-y-auto` (scrollable)
- **Footer:** `DialogFooter` with right-aligned buttons
- **Close:** Click outside or X button (implicit)

---

## 🎨 5. Color & Theme

**Tailwind Config:**
- `primary`: Blue (default) - used for active states, primary buttons
- `muted`: Gray-100 (light) / Gray-800 (dark) - backgrounds
- `accent`: Gray-100 (light) / Gray-800 (dark) - hover states
- `destructive`: Red (errors, delete)
- `success`: Green (approved, complete)
- `warning`: Yellow (failed, pending)
- `info`: Blue (processing)

**Dark mode:** Full support via `next-themes` with `dark` class strategy.

---

## 📱 6. Responsive Design

- **Grid systems:**
  - Dashboard stats: `grid-cols-5` (desktop) → wrap on mobile
  - Form grids: `grid-cols-2` (desktop) → single column mobile
  - Export buttons: `grid-cols-2 md:grid-cols-4`
- **Tables:** `overflow-auto` for horizontal scroll on small screens
- **Sidebar:** Fixed width (w-64), main content flex-1

---

## 🔧 7. Component Library (shadcn/ui)

**Used Components:**
- `Button` (variants: default, outline, destructive, ghost, secondary)
- `Input` (text, file)
- `Select` (with `SelectTrigger`, `SelectValue`, `SelectContent`, `SelectItem`)
- `Badge` (variants)
- `Alert` (variants: default, warning, success, destructive)
- `Table` (full suite: TableHeader, TableBody, TableRow, TableCell, TableHead)
- `Tabs` (TabsList, TabsTrigger, TabsContent)
- `Dialog` (DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription)
- `Separator` (horizontal)
- `Textarea`
- `Checkbox` (in Tables)
- `DropdownMenu` (for tenant selector)
- `Sonner` (toast notifications)
- `ThemeToggle` (custom component)

---

## 🚀 8. Key UX Patterns

### 8.1 Optimistic Updates

- Upload jobs → immediate UI update (optimistic) + toast
- Retry → immediate state change
- Approve/Reject → detail panel closes, list refreshes

### 8.2 Progressive Disclosure

- Templates: Accordion expand for details
- Review: Split view (list above, detail below)
- Export: Two-step (select template → select jobs)

### 8.3 Inline Editing

- Review tab: JSON edit inline with validation
- Template creation: Field editor table with live edits

### 8.4 Visual Hierarchy

- **Size:** h1 (text-2xl), h2 (text-xl), h3 (text-base), body (text-sm), helper (text-xs)
- **Weight:** font-bold (counters), font-semibold (section headers), font-medium (labels)
- **Color:** Primary (actions), muted-foreground (secondary info), foreground (primary text)

### 8.5 Feedback

- **Loading:** Spinners, disabled buttons, skeleton screens
- **Success:** Green checkmarks, "Đã thành công" toasts
- **Error:** Red badges, warning alerts, error toasts with details
- **Empty states:** Helpful text with actions (e.g., "Chưa có mẫu nào. Nhấn Tạo mẫu mới")

---

## 📝 9. Documentation & Annotations

**In-code documentation:**
- Component interfaces with JSDoc comments
- Inline comments for complex logic
- Status mapping constants (`STATUS_VI`, `statusBadgeVariant`)

**User-facing copy:**
- All text in Vietnamese
- Consistent terminology:
  - "hồ sơ" = extraction job
  - "mẫu" = template
  - "duyệt" = approve
  - "tổng hợp" = aggregate
  - "báo cáo" = report

**Icons (lucide-react):**
- `FileText` - documents
- `Settings2` - extraction (configuration)
- `LayoutDashboard` - dashboard
- `Upload`, `RefreshCw`, `Trash2` - actions
- `CheckCircle2`, `XCircle` - approve/reject
- `Calendar`, `FileSpreadsheet`, `BarChart3` - tab icons

---

## 🔒 10. Security & Multi-Tenancy

**Tenant Isolation:**
- All API calls automatically include `X-Tenant-ID` header (via `api` wrapper)
- Sidebar tenant selector visible when logged in
- Tenant context stored in `AuthProvider`

**Authentication:**
- JWT Bearer token in `Authorization` header
- Login page at `/login` (not covered here)
- Protected routes check `isLoggedIn` + `tenantId`

---

## 📈 11. Performance Considerations

- **Virtualization:** None currently - tables could be virtualized for 1000+ rows
- **Lazy loading:** Report details loaded on demand (`useEffect` when `selectedReportId` changes)
- **Caching:** No client-side caching; each filter change triggers API call
- **Bundle size:** Moderate - uses tree-shaking for icons and components

---

## 🐛 12. Known Issues & Tech Debt

1. **No real-time updates:** Jobs don't auto-refresh; user must click "Làm mới"
2. **No pagination:** Job lists load all jobs (could be thousands)
3. **CalendarPicker duplication:** Same calendar UI exists in Export tab and Inspect page - should extract to shared component
4. **Hard-coded limits:** Table max-h-72, max-h-48 - could be configurable
5. **No error boundaries:** Component crashes would take down entire tab
6. **JSON validation in Review:** Only basic `JSON.parse()` - no schema validation
7. **Date formatting:** `formatDate()` utility exists but not always used consistently

---

## 🎯 13. Design Principles Recap

From system requirements:

| Principle | Implementation |
|-----------|----------------|
| **Data-first** | All screens show extracted JSON data; templates are configuration only |
| **Template Isolation** | Word templates attached to templates but never read directly by UI |
| **Source Clarity** | UI surfaces the document job status and `parser_used` metadata without source-specific branches |
| **Deterministic** | Job data is immutable after extraction; review edits create new version |
| **Auditability** | `source_references` preserved; job history via state transitions |

---

## 📦 14. Component Checklist for New Features

When adding new UI screens:

- [ ] Use `shadcn/ui` components (no custom buttons/tables)
- [ ] Support dark mode (use `bg-background`, `text-foreground`, not hard colors)
- [ ] Include loading states (disabled buttons, spinners)
- [ ] Handle empty states (helpful messages + CTAs)
- [ ] Show error messages (toast + inline alerts)
- [ ] Respect tenant context (all API calls include `X-Tenant-ID`)
- [ ] Vietnamese copy only (no English except technical terms)
- [ ] Use icons from `lucide-react` (not emoji)
- [ ] Responsive design (mobile-first if possible)
- [ ] Accessibility (ARIA labels, keyboard navigation)

---

## 🎓 15. Developer Guide

**Adding a new tab:**
1. Create component in `components/extraction/`
2. Add to `extraction/page.tsx` TabsList + TabsContent
3. Pass `templates`, `jobs`, `onRefreshJobs` props
4. Use `api` wrapper for all API calls (auto-adds tenant header)

**Styling:**
- Use Tailwind utility classes
- Follow existing color patterns (muted, accent, primary)
- Use `cn()` utility for conditional classes

**State management:**
- Local state via `useState`
- Shared state (templates, jobs) lifted to `extraction/page.tsx` and passed down
- No global state (except AuthProvider)

**API integration:**
- Define types in `lib/types.ts`
- Add methods to `lib/api.ts` (return `{ok, data, error}`)
- Use `toast` for feedback

---

**END OF DOCUMENT**
