# 🎨 UI/UX Documentation & Optimization Guide
## Doc Automation Engine — Frontend v2.0

**Last Updated:** 2026-04-24  
**Tech Stack:** Next.js 14 (App Router), React 18, TypeScript, Tailwind CSS, Radix UI, shadcn/ui  
**Design Philosophy:** Data-first, Template-isolated, Source-independent, Deterministic, Auditable

---

## 📊 1. Current Workflow Analysis

### 1.1 End-to-End User Journey

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         COMPLETE DATA FLOW                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────┐    ┌────────────┐    ┌────────────┐    ┌────────────┐    │
│  │  Login   │───▶│ Dashboard  │───▶│ Extraction │───▶│  Review    │───▶│
│  │ + Tenant │    │  (Overview)│    │  Engine    │    │  & Approve │    │
│  └──────────┘    └────────────┘    └────────────┘    └────────────┘    │
│       │                 │                  │                  │           │
│       ▼                 ▼                  ▼                  ▼           │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                     KEY WORKFLOWS                                │    │
│  │  • Template Management (Create via Word scan)                  │    │
│  │  • Job Ingestion (PDF upload / Google Sheets)                 │    │
│  │  • Quality Review (Approve/Reject with editing)              │    │
│  │  • Report Aggregation (Excel/Word export)                    │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Core User Personas

| Persona | Goals | Primary Screens | Pain Points |
|---------|-------|----------------|-------------|
| **Operator** | Upload docs, monitor jobs, review extracted data | Jobs Tab, Review Tab | Unclear statuses, bulk actions missing |
| **Manager** | Create templates, generate reports, monitor KPIs | Dashboard, Templates, Export | Calendar UX confusing, report preview limited |
| **QA/Admin** | Inspect data quality, troubleshoot issues | Sheet Inspector | Buried navigation, complex grid |
| **Super Admin** | Manage tenants, configure integrations | Sidebar, Settings | Tenant creation UI basic |

---

## 🗺️ 2. Information Architecture

### 2.1 Navigation Structure

```
/ (Dashboard)
├── Overview Metrics (6 cards)
├── Pipeline Funnel (progress bar)
├── Recent Reports Table
└── Quick Nav Cards → /extraction, /documents

/extraction (Main Engine)
├── ⚙️ Templates (tab)
│   ├── Template List (accordion)
│   └── Create Dialog (Word scan / manual)
├── 📤 Jobs (tab)
│   ├── Upload Section (file input + template select)
│   ├── Stats Bar (5 metrics)
│   ├── Filters (status, template)
│   └── Job Table (with actions)
├── 🔍 Review (tab)
│   ├── Stats Bar
│   ├── Filters (status, template, search)
│   ├── Job Table (clickable rows)
│   └── Detail Panel (split view: data + actions)
├── 📋 Inspect (tab) — QA Tool
│   ├── Sidebar (sheet selector, stats)
│   ├── Tabs: Grid | Calendar | Mapping | Issues
│   └── Status Bar
└── 📊 Export (tab)
    ├── Create Report (Calendar OR Template mode)
    ├── Report List (dropdown)
    └── Export Options (Excel, Word auto, Word upload, JSON)

/documents
└── Document List Table

/login
└── Auth Form (login/register toggle)
```

### 2.2 State Management Flow

```mermaid
graph TD
    A[API Calls] --> B[Local Component State]
    B --> C[Props Lifting to extraction/page.tsx]
    C --> D[Props Down to Tabs]
    D --> E[Child Components]
    
    E --> F[Toast Notifications]
    E --> G[Optimistic Updates]
    G --> H[Refresh on Success]
    
    subgraph "Shared State"
        C --> Templates[]
        C --> Jobs[]
    end
```

**Current Issues:**
- No global state (Context/Redux) → prop drilling through 3 levels
- No caching layer → repeated API calls on every refresh
- No optimistic updates for review/delete → waiting for server

---

## 🎯 3. UI Component Patterns (shadcn/ui)

### 3.1 Status Badge System

```typescript
// Centralized in components/extraction/*-tab.tsx
const STATUS_VI = {
  pending: "⏳ Đang tiếp nhận…",
  processing: "🔄 AI đang đọc tài liệu…",
  extracted: "🔄 AI đang phân tích…",
  enriching: "🔄 AI đang phân tích chi tiết…",
  ready_for_review: "✅ Sẵn sàng duyệt",
  approved: "✅ Đã duyệt",
  rejected: "🚫 Từ chối",
  failed: "⚠️ Cần xem lại",
  aggregated: "📊 Có trong báo cáo"
};

function statusBadgeVariant(s: string) {
  if (["processing", "extracted", "enriching", "pending"].includes(s))
    return "info";       // blue
  if (["ready_for_review", "approved"].includes(s))
    return "success";    // green
  if (s === "failed") return "warning";     // yellow
  if (s === "rejected") return "destructive"; // red
  if (s === "aggregated") return "purple";   // purple custom
  return "secondary";
}
```

### 3.2 Color & Theme Consistency

| Token | Usage | Light | Dark |
|-------|-------|-------|------|
| `bg-primary/5` | Highlight cards | #eff6ff | #1e3a5f |
| `bg-muted/30` | Empty states, backgrounds | #f5f5f5 | #262626 |
| `text-muted-foreground` | Secondary text | #6b7280 | #a3a3a3 |
| `border` | Borders | #e5e7eb | #404040 |
| `accent` | Hover states | #f5f5f5 | #262626 |

---

## 🔍 4. Screen-by-Screen UX Audit

### 4.1 Dashboard (`app/page.tsx`)

**What Works:**
- Clear metric cards with icons
- Pipeline funnel visualization with progress bar
- Quick action cards for navigation
- Notifications with direct links

**Issues:**
1. Notifications use `Alert` component but could be more prominent
2. Recent reports table shows limited info (no status drill-down)
3. "Quick nav" cards at bottom feel like afterthought
4. No "Create Template" shortcut from dashboard
5. Loading states not optimized (no skeleton)

**Recommendations:**
- [ ] Replace Alert notifications with Toast or Banner component
- [ ] Make recent reports interactive (click → export tab)
- [ ] Add "Quick Actions" section with primary CTAs
- [ ] Add skeleton loading for metrics
- [ ] Show approval rate trend (up/down arrow)

---

### 4.2 Templates Tab (`components/extraction/templates-tab.tsx`)

**What Works:**
- Accordion UI keeps list clean
- Badge system shows template capabilities at a glance
- Word scan with field editor is powerful
- Google Sheets config hidden in `<details>` (good for advanced)

**Issues:**
1. Template list doesn't show which have Word templates attached at a glance
2. Field editor table is cramped (5 columns on small screens)
3. No preview of Word template
4. No duplicate template functionality
5. Google Sheets config too hidden (collapsible)
6. No template grouping/categorization
7. No search/filter for templates

**Recommendations:**
- [ ] Add template icon badges: 📝 (Word), 📊 (Sheets), 🎯 (Auto-filename)
- [ ] Make field editor responsive (stack columns on mobile)
- [ ] Add "Preview" button that shows sample Word fields
- [ ] Add "Duplicate" action in template dropdown
- [ ] Move Google Sheets config to separate "Integrations" tab or modal
- [ ] Add search input above template list
- [ ] Allow template categories/tags

---

### 4.3 Jobs Tab (`components/extraction/jobs-tab.tsx`)

**What Works:**
- Clear upload section with file size display
- Smart auto-detect template option
- Google Sheets quick-import button (conditional)
- Status filter + template filter combo
- Retry button for failed jobs

**Critical Issues:**
1. **No bulk operations** (cannot select multiple jobs for delete/retry)
2. **No job grouping** by batch/date
3. **No progress bar** during upload (just spinner)
4. **No pagination** - will break with 1000+ jobs
5. **Table overflow** inconsistent (some use `overflow-auto`, some fixed height)
6. **File upload** doesn't show individual file status (just aggregated toast)
7. **Google Sheets ingestion** progress is text-only, hard to see

**Recommendations:**
- [ ] Add checkboxes + bulk actions toolbar (Approve, Delete, Retry)
- [ ] Implement virtual scrolling for job table (1000+ rows)
- [ ] Add pagination with page size selector (50, 100, 500)
- [ ] Show upload progress per file (list with progress bars)
- [ ] Add job grouping: by batch_id, by date, by template
- [ ] Improve sheet ingestion: use Progress component instead of text
- [ ] Add "Download original PDF" action for each job
- [ ] Add column to show parser_used (PDF vs Sheets)

---

### 4.4 Review Tab (`components/extraction/review-tab.tsx`)

**What Works:**
- Split view: list above, detail below (clear context)
- View/Edit tabs for data (non-destructive editing)
- JSON validation before approve
- Notes required for reject (enforces documentation)
- Selected row highlighting

**Critical Issues:**
1. **Detail panel pushes content down** - hard to see list while reviewing
2. **JSON editor is raw** - no syntax highlighting, formatting issues
3. **No side-by-side comparison** (original vs edited)
4. **Cannot see confidence scores** or source references
5. **No keyboard shortcuts** (Enter to approve, Esc to close)
6. **Detail panel closes** after approve/reject (loses context of list position)
7. **No batch approve** from list view
8. **Scalar fields** displayed as boxes - hard to scan
9. **Arrays** shown as full tables - overwhelming for large datasets

**Recommendations:**
- [ ] **Redesign as split-pane** (list left 40%, detail right 60%) - fixed height with scroll
- [ ] Add syntax highlighting to JSON editor (use CodeMirror or Monaco)
- [ ] Add "Compare" view showing original (left) vs edited (right) with diff highlighting
- [ ] Show confidence_scores inline (color code by threshold)
- [ ] Add keyboard shortcuts: `Ctrl+Enter` (approve), `Ctrl+Shift+Enter` (reject), `Esc` (close)
- [ ] Keep list position after approve (don't close panel, just mark row as approved)
- [ ] Add bulk approve from list (checkboxes + approve button)
- [ ] For arrays, default show first 10 rows with "Show all N" expand
- [ ] Allow field-level editing in View mode (click to edit, not just JSON)

---

### 4.5 Export Tab (`components/extraction/export-tab.tsx`)

**What Works:**
- Two creation modes (Calendar + Template)
- Preview of aggregated data before export
- Multiple export formats (Excel, Word auto, Word custom, JSON)
- Shows sources used (template, sheet names, date range)

**Critical Issues:**
1. **Confusing dual creation modes** - users don't know which to use
2. **Calendar mode** requires template selection after picking day (extra step)
3. **Template mode** shows "Chọn tất cả" but doesn't indicate what's selected
4. **Report list** is a dropdown - hard to compare multiple reports
5. **No export history** or scheduled exports
6. **Word upload** file input appears only after selecting report (discoverability)
7. **Aggregated data preview** truncates to 50 rows - no way to see full data
8. **No validation** that selected jobs have same template (for aggregation)

**Recommendations:**
- [ ] **Consolidate creation modes**: Single form with toggle between "By Date" and "By Template"
- [ ] In Calendar mode: auto-select template if only one exists for selected day
- [ ] Replace report dropdown with card list (name, date, count) + "Manage Reports" page
- [ ] Add "Export History" table showing past exports with download links
- [ ] Move Word upload to report creation (upload template during report build)
- [ ] Add pagination in data preview (show all N rows)
- [ ] Show warning if mixing templates in report
- [ ] Add "Schedule Export" button (cron-like, email delivery)

---

### 4.6 Sheet Inspector (`components/extraction/sheet-inspector.tsx`)

**What Works:**
- Powerful QA tool with 4 views
- Color-coded grid for STT coverage
- Issues tab groups problems by date
- Mapping tab shows column configuration
- JSON export for debugging

**Critical Issues:**
1. **Buried navigation** - /extraction?tab=inspect is not discoverable
2. **Grid tab** uses custom HTML table (not shadcn/ui Table) - inconsistency
3. **Calendar tab** duplicates CalendarPicker logic (should be shared component)
4. **No date range picker** - only single month at a time
5. **Sheet selector** shows 4 hard-coded sheets - not dynamic from document
6. **No drill-down** from Issues table to job detail
7. **Status bar** hard-coded STT count (61) - should be dynamic

**Recommendations:**
- [ ] Add "Inspect" link in Jobs tab (for sheet jobs) → opens inspector with filters
- [ ] Extract calendar grid to reusable component (used by Export + Inspector)
- [ ] Add date range picker (start/end) for multi-month analysis
- [ ] Fetch sheet names dynamically from API instead of hard-coded
- [ ] Make Issues table rows clickable → opens job in Review tab
- [ ] Calculate STT count from GRID_STTS array (not hard-coded)
- [ ] Add "Export to Excel" for issues list

---

### 4.7 Sidebar (`components/layout/sidebar.tsx`)

**What Works:**
- Clean navigation with active state
- Tenant switcher with dropdown
- Theme toggle integrated
- User email display

**Issues:**
1. **Tenant selector at bottom** - important control, should be higher
2. **No notification badge** for awaiting reviews
3. **Create tenant** dialog is basic (no settings, no member invite)
4. **No "Settings" link** in navigation
5. **No help/documentation link**
6. **Sidebar is fixed width** (w-64) - not collapsible on small screens
7. **No user avatar** or profile menu

**Recommendations:**
- [ ] Move tenant selector below navigation (before user section)
- [ ] Add badge count on nav items (e.g., "Duyệt (5)")
- [ ] Expand create tenant dialog: add description, billing settings
- [ ] Add "Settings" page link (tenant config, user profile)
- [ ] Add "Help" link to documentation
- [ ] Make sidebar collapsible (hamburger menu on mobile)
- [ ] Add user avatar with dropdown (Profile, Settings, Logout)

---

### 4.8 Login Page (`app/login/page.tsx`)

**What Works:**
- Simple, clean form
- Toggle between login/register
- Proper validation
- Redirect after login

**Issues:**
1. **No "Forgot password"** flow
2. **No SSO/OAuth options** (Google, Microsoft)
3. **No email verification** UI
4. **No loading skeleton** - just button spinner
5. **No password visibility toggle**
6. **No remember me** checkbox

**Recommendations:**
- [ ] Add "Forgot password?" link with reset flow
- [ ] Add SSO buttons (if backend supports)
- [ ] Add password show/hide toggle (eye icon)
- [ ] Add "Remember me" checkbox
- [ ] Add loading skeleton on form submit
- [ ] Show password requirements on register

---

## 🚀 5. High-Priority Optimizations

### 5.1 Performance (Immediate)

**Problem:** No virtualization → thousands of rows crash browser

**Solution:**
```bash
npm install @tanstack/react-virtual
```
```tsx
// Use in JobsTab, ReviewTab, ExportTab
import { useVirtualizer } from '@tanstack/react-virtual';

const rowVirtualizer = useVirtualizer({
  count: filtered.length,
  getScrollElement: () => parentRef.current,
  estimateSize: () => 40, // row height
  overscan: 20,
});
```

**Impact:** 10x faster rendering for 1000+ rows, smoother scrolling

---

### 5.2 Real-time Updates (Immediate)

**Problem:** Manual refresh required → stale data

**Solution:** WebSocket or polling
```tsx
// In extraction/page.tsx
useEffect(() => {
  const ws = new WebSocket(`${API_WS_URL}?tenant_id=${tenantId}`);
  ws.onmessage = (e) => {
    const event = JSON.parse(e.data);
    if (event.type === 'job_update') {
      // Optimistic update in jobs state
      setJobs(prev => prev.map(j => 
        j.id === event.job_id ? { ...j, ...event.data } : j
      ));
    }
  };
  return () => ws.close();
}, [tenantId]);
```

**Fallback:** Polling every 10s for `/api/v1/jobs/updates?since=timestamp`

---

### 5.3 Bulk Operations (High)

**Problem:** Cannot approve/reject/delete multiple jobs

**Solution:** Add checkboxes to tables
```tsx
// Add to JobsTab, ReviewTab
const [selectedJobIds, setSelectedJobIds] = useState<Set<string>>(new Set());

// Table row:
<TableRow>
  <TableCell>
    <Checkbox checked={selectedJobIds.has(j.id)} onCheckedChange={() => toggleJob(j.id)} />
  </TableCell>
  {/* ... */}
</TableRow>

// Bulk action bar (sticky bottom):
{selectedJobIds.size > 0 && (
  <div className="fixed bottom-4 left-64 right-6 bg-background border rounded-lg shadow-lg p-3 flex items-center gap-3">
    <span>{selectedJobIds.size} mục đã chọn</span>
    <Button onClick={bulkApprove}>✅ Duyệt tất cả</Button>
    <Button variant="destructive" onClick={bulkDelete}>🗑️ Xoá</Button>
    <Button variant="ghost" onClick={() => setSelectedJobIds(new Set())}>Huỷ</Button>
  </div>
)}
```

---

### 5.4 Split-Pane Review (High)

**Problem:** Detail panel pushes content, breaks context

**Proposed Redesign:**

```tsx
<div className="flex h-[calc(100vh-200px)] gap-4">
  {/* Left: Job List (40%) */}
  <div className="w-2/5 overflow-auto border rounded-lg">
    <Table>
      {/* ... job list ... */}
    </Table>
  </div>

  {/* Right: Detail Panel (60%) */}
  <div className="w-3/5 overflow-auto border rounded-lg p-4">
    {selectedJob ? (
      <>
        <JobHeader job={selectedJob} />
        <Tabs>
          <TabsContent value="view">
            <RenderExtractedData data={...} />
          </TabsContent>
          <TabsContent value="compare">
            <DiffView original={...} edited={...} />
          </TabsContent>
          <TabsContent value="edit">
            <CodeEditor value={json} onChange={...} />
          </TabsContent>
        </Tabs>
        <ApprovalActions />
      </>
    ) : (
      <EmptyState>Chọn hồ sơ để xem chi tiết</EmptyState>
    )}
  </div>
</div>
```

**Benefits:**
- Both list and detail visible simultaneously
- No layout shift when detail loads
- Easy to compare across jobs

---

### 5.5 Template Creation UX (Medium)

**Problem:** Google Sheets config buried in accordion

**Proposed Flow:**
```
Create Template Dialog
├── Step 1: Choose Method
│   ├── [ ] Scan Word file
│   └── [ ] Manual entry
│
├── Step 2 (if scan): Upload .docx → Scan → Field Editor
│   └── NEW: Checkbox "Enable Google Sheets import"
│       └── If checked → show sheet config inline (not hidden)
│
├── Step 3: Review & Create
│   ├── Summary card: fields, agg rules, integrations
│   └── Create button
```

**Integrations Tab (separate page):**
- `/extraction/integrations` or modal from template list
- List all templates with their integrations (Word, Sheets)
- Toggle enable/disable per integration
- Test connection button

---

## 📱 6. Responsive Design Issues

### Current Breakpoints

| Screen | Issue | Fix |
|--------|-------|-----|
| Mobile (< 768px) | Sidebar covers content, no hamburger | Add collapsible sidebar |
| Tablet (768-1024) | Tables overflow, no horizontal scroll | Add `overflow-x-auto` wrapper |
| Small laptop (1024-1280) | Calendar picker cramped, grid overflow | Responsive grid cols |

### 6.1 Mobile Navigation Pattern

```tsx
// Add to layout.tsx
const [sidebarOpen, setSidebarOpen] = useState(false);

// Add hamburger button in main:
<Button variant="ghost" size="icon" className="md:hidden" onClick={() => setSidebarOpen(true)}>
  <Menu className="h-5 w-5" />
</Button>

// Sidebar: add overlay when open on mobile
{sidebarOpen && (
  <div className="fixed inset-0 bg-black/50 z-40 md:hidden" onClick={() => setSidebarOpen(false)} />
)}
```

---

## ♿ 7. Accessibility Checklist

### 7.1 Required Fixes

- [ ] **All buttons** need `aria-label` if icon-only
  ```tsx
  <Button aria-label="Làm mới danh sách">
    <RefreshCw />
  </Button>
  ```
- [ ] **Form inputs** need proper `htmlFor` + `id` association
- [ ] **Tables** need `<caption>` for screen readers
- [ ] **Color contrast** - verify AA compliance (4.5:1 for normal text)
- [ ] **Focus management** - trap focus in dialogs (Radix handles mostly)
- [ ] **Skip to content** link for keyboard users
- [ ] **Status badges** should be announced (use `role="status"`)
- [ ] **Required fields** marked with `aria-required="true"`

### 7.2 Screen Reader Testing

Test with NVDA/JAWS:
1. Navigate job list → hear status, template, filename
2. Open review detail → hear field names and values
3. Fill template form → hear validation errors

---

## 🎨 8. Visual Design System Updates

### 8.1 Typography Scale

| Element | Current | Recommended |
|---------|---------|-------------|
| Page title | text-2xl font-bold | text-3xl font-bold tracking-tight |
| Section header | text-xl font-semibold | text-lg font-semibold flex items-center gap-2 |
| Card title | text-sm font-medium | text-sm font-semibold |
| Body text | text-sm | text-sm leading-relaxed |
| Helper text | text-xs | text-xs text-muted-foreground |

### 8.2 Spacing System

Use consistent spacing scale (Tailwind `space-y-*`):
- `space-y-2`: Tight grouping (related controls)
- `space-y-4`: Section spacing
- `space-y-6`: Major page sections

**Current issue:** Inconsistent spacing (some `space-y-3`, some `space-y-4`)

---

## 🔧 9. Technical Debt & Refactoring

### 9.1 Component Extraction Needed

1. **`DataTable`** - reusable table with sorting, pagination, virtualization
2. **`StatusFilterBar`** - reuse in JobsTab + ReviewTab
3. **`CalendarGrid`** - shared between Export + Inspector
4. **`JobActions`** - approve/reject/delete dropdown
5. **`TemplateCard`** - reusable template display
6. **`UploadZone`** - drag-and-drop file upload component
7. **`JsonEditor`** - Monaco editor wrapper with validation

### 9.2 Code Quality Issues

- **Prop drilling:** Templates/jobs passed through 3 levels → use context
- **Duplicate code:** STATUS_VI, statusBadgeVariant copied 4x → extract to `lib/constants.ts`
- **API calls repeated:** fetchTemplates, fetchJobs in every tab → centralize in parent
- **Magic numbers:** `max-h-72`, `max-h-48` → extract to CSS variables
- **Hard-coded strings:** "Tất cả", "Chưa có..." → extract to `lib/i18n.ts`

### 9.3 TypeScript Improvements

```typescript
// Current: any[] used heavily
// Fix: Define proper types

type JobFilters = {
  status: StatusFilter;
  templateId: string | "__all";
  search: string;
  dateFrom?: string;
  dateTo?: string;
};

type TemplateFormData = {
  name: string;
  fields: FieldRow[];
  aggregationRules: AggregationRule[];
  googleSheetsConfig?: GoogleSheetsConfig;
  wordTemplateKey?: string;
};
```

---

## 📈 10. KPI-Driven Improvements

### 10.1 Metrics to Track

| Metric | Current | Target | How to Measure |
|--------|---------|--------|----------------|
| Time to review 1 job | ~60s | <30s | User testing, analytics |
| Templates created/week | ? | +50% | Funnel analysis |
| Jobs uploaded vs processed | ? | 95%+ success rate | Dashboard |
| Report generation time | ~10s | <5s | Performance monitoring |
| User error rate (failed uploads) | ? | <5% | Error logging |

### 10.2 A/B Test Ideas

1. **Review UX**: Split-pane vs current push-down
2. **Job upload**: Show individual file progress vs single toast
3. **Template creation**: Inline fields vs modal dialog
4. **Export workflow**: Single mode vs dual mode (calendar/template)

---

## 🛠️ 11. Implementation Roadmap (Chi Tiết)

### 📌 Legend
- ⚡ Quick Win (1-2 days)
- 🔥 High Impact (1 week)
- 🟡 Medium Effort (1-2 weeks)
- 🔵 Long-term (3-4 weeks)

---

### Phase 1: Quick Wins (1-2 tuần) - ⚡⚡⚡

**Mục tiêu:** Cải thiện UX cơ bản, fix các issue nghiêm trọng nhất

#### 1.1 Extract Shared Constants (⚡ 1 day)
- [ ] Tạo `lib/constants.ts`:
  - `STATUS_VI` mapping
  - `statusBadgeVariant()` function
  - `STATUS_ORDER` array để sorting
  - `JOB_FILTER_OPTIONS` constant
- [ ] Update tất cả tabs tham chiếu từ constants
- [ ] Remove duplicate code trong jobs-tab, review-tab, export-tab

#### 1.2 Bulk Operations in Review Tab (🔥 3 days)
- [ ] Add checkboxes vào Review table
- [ ] Create `BulkActionBar` component (sticky bottom)
  - Shows "N mục đã chọn"
  - Buttons: ✅ Duyệt tất cả, ❌ Từ chối, 🗑️ Xoá
  - Cancel button to clear selection
- [ ] Implement `bulkApprove()` API call
- [ ] Implement `bulkReject()` API call
- [ ] Implement `bulkDelete()` API call
- [ ] Add confirmation dialog cho bulk delete
- [ ] Update job list state after bulk actions
- [ ] **Test:** 100 jobs selected → approve all in 1 click

#### 1.3 Virtual Scrolling for Tables (🔥 2 days)
- [ ] Install: `npm install @tanstack/react-virtual`
- [ ] Tạo `VirtualTable` wrapper component:
  ```tsx
  interface VirtualTableProps {
    data: T[];
    rowHeight?: number;
    overscan?: number;
    renderRow: (item: T, index: number) => ReactNode;
  }
  ```
- [ ] Apply to JobsTab table
- [ ] Apply to ReviewTab table
- [ ] Apply to ExportTab job selection table
- [ ] Test với 5000+ rows (phải mượt, no lag)
- [ ] Add "Rows per page" selector: 50, 100, 500, All

#### 1.4 Skeleton Loaders (⚡ 2 days)
- [ ] Tạo `SkeletonRow` component (shadcn Skeleton)
- [ ] Add to Dashboard metrics (6 cards)
- [ ] Add to Templates list (skeleton cards)
- [ ] Add to Jobs table (skeleton rows)
- [ ] Add to Review table (skeleton rows)
- [ ] Add to Reports dropdown (skeleton option)
- [ ] Show skeleton khi đang load data, hide khi xong

#### 1.5 Mobile Responsive Sidebar (🟡 3 days)
- [ ] Add hamburger button (md:hidden) trong layout
- [ ] Tạo `useSidebar` hook để manage open/close state
- [ ] Add overlay backdrop khi sidebar mở trên mobile
- [ ] Make sidebar slide-in từ left (transform transition)
- [ ] Close sidebar khi click nội dung chính
- [ ] Close sidebar khi click navigation item
- [ ] **Test:** Chrome DevTools mobile view, swipe gestures

#### 1.6 Accessibility Fixes (⚡ 2 days)
- [ ] Audit tất cả buttons với icon-only → add `aria-label`
- [ ] Add `role="status"` cho status badges
- [ ] Add `aria-live="polite"` cho toast notifications
- [ ] Add `<caption>` cho tất cả tables
- [ ] Add `htmlFor` + `id` cho form labels
- [ ] Add `aria-required="true"` cho required fields
- [ ] Add skip-to-content link (sr-only) ở top của page
- [ ] Test với NVDA/JAWS screen reader
- [ ] Run axe-core accessibility audit

#### 1.7 Real-time Updates (Polling) (🔥 3 days)
- [ ] Create `usePolling` hook:
  ```tsx
  function usePolling(callback: () => Promise<void>, interval: number) {
    useEffect(() => {
      const id = setInterval(callback, interval);
      return () => clearInterval(id);
    }, [callback, interval]);
  }
  ```
- [ ] Apply to JobsTab: poll `/api/v1/jobs/updates?since=lastCheck`
- [ ] Apply to Dashboard: poll metrics every 30s
- [ ] Show "Live" indicator khi polling active
- [ ] Add "Pause updates" button để user stop polling
- [ ] Optimistic update: update UI trước khi API respond
- [ ] Handle conflicts (server state override)

**Deliverables Phase 1:**
- [ ] Split-pane Review tab (nếu kịp, else Phase 2)
- [ ] Bulk approve/delete trong Review
- [ ] Virtual scroll cho 3 tables
- [ ] Skeleton loaders khắp nơi
- [ ] Mobile sidebar hoạt động
- [ ] Accessibility audit pass
- [ ] Real-time updates cơ bản (polling)

---

### Phase 2: Core UX Redesign (2-4 tuần) - 🔥🔥

**Mục tiêu:** Refactor các workflow chính, cải thiện hiệu quả công việc

#### 2.1 Split-Pane Review Redesign (🔥🔥🔥 1 tuần)
- [ ] Design mockup: 40/60 split, fixed height 70vh
- [ ] Create `ReviewSplitPane` component:
  - Left: `JobListPanel` (filtesr + virtual table)
  - Right: `JobDetailPanel` (tabs: view/compare/edit)
- [ ] Keep selected job in URL hash (`#job-{id}`) để persist refresh
- [ ] Add resize handle giữa 2 panels (drag to adjust width)
- [ ] Preserve scroll position sau khi approve
- [ ] Add keyboard shortcuts:
  - `Ctrl+Enter` → Approve
  - `Ctrl+Shift+Enter` → Reject
  - `Esc` → Close detail panel
  - `↑/↓` → Navigate rows
- [ ] Show loading skeleton trong detail panel
- [ ] Add "Compare" tab với side-by-side diff view
- [ ] **Test:** User có thể review 10 jobs liên tục mà không mất context

#### 2.2 CalendarGrid Shared Component (🟡 5 days)
- [ ] Extract calendar logic từ `CalendarPicker` và `CalendarTab`
- [ ] Tạo `CalendarGrid` component:
  ```tsx
  <CalendarGrid
    days={calendarDays}
    onSelectDay={handleSelect}
    selectedDay={selectedDate}
    showHeader={true/false}
    showLegend={true/false}
  />
  ```
- [ ] Add `useCalendar` hook cho month navigation
- [ ] Reuse trong Export tab (Calendar mode)
- [ ] Reuse trong Inspector tab (Calendar view)
- [ ] Add `loading` và `error` states
- [ ] Make calendar cells customizable qua render props
- [ ] Add unit tests cho calendar logic

#### 2.3 Export Workflow Consolidation (🔥 1 tuần)
- [ ] Design unified export flow:
  ```
  [Toggle: By Date | By Template]
  ↓
  [Date Range Picker] OR [Template Select]
  ↓
  [Job List with checkboxes]
  ↓
  [Report Name + Create Button]
  ```
- [ ] Remove dual-tabs, replace với single component
- [ ] Auto-select template nếu chỉ có 1 template trong ngày
- [ ] Show validation: "Không thể mix templates trong 1 report"
- [ ] Replace dropdown report list với card grid
- [ ] Add "Export History" page mới:
  - Table: report name, date, jobs count, status
  - Actions: download, delete, resend
  - Filter by date range, template
- [ ] Add pagination cho export history (20 items/page)
- [ ] **Test:** User tạo report từ calendar → chọn template → success

#### 2.4 CodeMirror JSON Editor (⚡ 2 days)
- [ ] Install: `npm install @uiw/react-codemirror @codemirror/lang-json`
- [ ] Tạo `JsonEditor` component:
  ```tsx
  <JsonEditor
    value={jsonString}
    onChange={setJsonString}
    validate={true} // real-time syntax check
    height="400px"
  />
  ```
- [ ] Add syntax highlighting (JSON tokens)
- [ ] Add line numbers
- [ ] Add error underline khi JSON invalid
- [ ] Add format button (prettify)
- [ ] Add minify button
- [ ] Replace Textarea trong Review edit tab
- [ ] Add copy-to-clipboard button

#### 2.5 Template Search & Filter (🟡 3 days)
- [ ] Add search input above template list
- [ ] Filter logic: search theo name, field names, description
- [ ] Add debounce 300ms cho search input
- [ ] Show "N templates found" counter
- [ ] Add filter by template type (Word, Sheets, Both)
- [ ] Add filter by field count range
- [ ] Persist search query trong URL (?search=...)
- [ ] Clear search button
- [ ] Empty state khi no results

#### 2.6 Job Grouping & Enhanced Filters (🟡 4 days)
- [ ] Add "Group by" dropdown: None, Date, Template, Batch
- [ ] When grouped, show group headers với collapse/expand
- [ ] Add date range filter (from-date, to-date)
- [ ] Add parser_used filter (PDF, Google Sheets)
- [ ] Add confidence score filter (min threshold)
- [ ] Save filters to localStorage (restore on reload)
- [ ] Add "Export filtered list" → CSV
- [ ] Show active filters as removable tags

**Deliverables Phase 2:**
- [ ] Review tab split-pane hoàn chỉnh
- [ ] CalendarGrid component shared
- [ ] Export workflow unified + history page
- [ ] CodeMirror JSON editor
- [ ] Template search/filter
- [ ] Job grouping + advanced filters
- [ ] Virtual scroll production-ready

---

### Phase 3: Polish & Refinement (1-2 tuần) - 🟡

**Mục tiêu:** Polish UX, add small but impactful improvements

#### 3.1 Keyboard Shortcuts System (⚡ 2 days)
- [ ] Create `useKeyboardShortcuts` hook
- [ ] Define shortcut constants:
  ```ts
  const SHORTCUTS = {
    APPROVE: 'Mod+Enter',
    REJECT: 'Mod+Shift+Enter',
    CLOSE: 'Escape',
    SEARCH: 'Cmd+K',
    REFRESH: 'Cmd+R',
    NEXT_JOB: 'ArrowDown',
    PREV_JOB: 'ArrowUp',
  };
  ```
- [ ] Add keyboard hints trong UI (e.g., "Ctrl+Enter to approve")
- [ ] Add keyboard shortcuts modal (Help → Keyboard)
- [ ] Allow user customize shortcuts (localStorage)
- [ ] Conflicts detection nếu shortcut đã được browser use

#### 3.2 Export History Page (⚡ 3 days)
- [ ] New page: `/extraction/export-history`
- [ ] Table: report name, created_at, jobs_count, status
- [ ] Filters: date range, template, status
- [ ] Actions per row:
  - Download (Excel/Word/JSON)
  - Resend (re-run aggregation)
  - Delete
  - View details (modal with preview)
- [ ] Batch delete cho exports
- [ ] Add "Schedule Export" button:
  - Modal: pick template, schedule (cron), email recipients
  - Store schedule trong DB, background worker gửi email
- [ ] Show export metrics (total exports this month)

#### 3.3 Template Management Enhancements (🟡 3 days)
- [ ] Template categories/tags:
  - Add tag input trong create/edit
  - Filter by tag
  - Color-coded tags
- [ ] Duplicate template:
  - "Duplicate" button trong template dropdown
  - Copy fields, rules, integrations
  - Prompt for new name
- [ ] Template versioning:
  - Keep last 5 versions
  - "Rollback" button
  - Show changelog
- [ ] Template sharing:
  - Share between tenants (if multi-tenant allowed)
  - Export/import template as YAML
- [ ] Template validation:
  - Check Word template matches fields
  - Show missing/present fields
  - Preview button (sample merge)

#### 3.4 Enhanced Job Detail View (⚡ 2 days)
- [ ] Show confidence_scores với color coding:
  - >90%: green badge
  - 70-90%: yellow
  - <70%: red
- [ ] Show source_references (page number, bounding box)
- [ ] Add "View Original PDF" button (opens in new tab)
- [ ] Show processing_time_ms prominently
- [ ] Add "Edit history" tab (who approved, when, changes)
- [ ] Show retry_count với warning nếu >3
- [ ] Add copy button cho extracted data (JSON)

#### 3.5 Notifications & Toast Improvements (⚡ 1 day)
- [ ] Group similar toasts (e.g., "3 files uploaded")
- [ ] Add undo action trong toast (undo delete, undo approve)
- [ ] Persistent toasts (stay until user dismiss)
- [ ] Add toast grouping by category (jobs, templates, reports)
- [ ] Sound notification cho important events (optional)
- [ ] Email digest option (daily summary)

#### 3.6 Loading States & Empty States (⚡ 2 days)
- [ ] Create `EmptyState` component:
  ```tsx
  <EmptyState
    icon={<FileText />}
    title="Chưa có hồ sơ nào"
    description="Upload PDF để bắt đầu"
    action={<Button>Upload ngay</Button>}
  />
  ```
- [ ] Replace tất cả "Chưa có..." text với EmptyState
- [ ] Add illustrations (SVG) cho empty states
- [ ] Skeleton variations:
  - Card skeleton (dashboard)
  - Table skeleton (list pages)
  - Form skeleton (create/edit)
- [ ] Show "Last updated: {time}" trong tables

**Deliverables Phase 3:**
- [ ] Keyboard shortcuts toàn bộ app
- [ ] Export history page + scheduling
- [ ] Template tags + duplicate + versioning
- [ ] Enhanced job detail (confidence, source refs)
- [ ] Toast improvements với undo
- [ ] Empty states với illustrations

---

### Phase 4: Advanced Features (3-4 tuần) - 🔵

**Mục tiêu:** Advanced workflows, admin features, performance

#### 4.1 Settings & Tenant Management (🔥 2 tuần)
- [ ] New page: `/settings`
- [ ] Sections:
  - **Profile:** Name, email, password change
  - **Tenant:** Name, description, logo upload, timezone
  - **Members:** Invite by email, role assignment (admin/operator/viewer)
  - **Integrations:** Google Sheets API key, S3 config, webhook URLs
  - **Notifications:** Email preferences, digest schedule
  - **API:** Generate API keys, view usage
- [ ] Create `SettingsLayout` với sidebar navigation
- [ ] Implement settings API endpoints (PATCH /settings)
- [ ] Add form validation (Yup/Zod)
- [ ] Show success/error toasts sau save
- [ ] Add "Danger zone": Delete tenant, Download data

#### 4.2 Advanced Filtering System (🟡 1 tuần)
- [ ] Create `FilterBuilder` component:
  - Add filter: field, operator (==, !=, >, <, contains), value
  - Combine với AND/OR logic
  - Save filter presets
  - Share filter URL (encoded)
- [ ] Apply to Jobs, Review, Reports
- [ ] Add "Saved Filters" dropdown
- [ ] Export filtered results → CSV
- [ ] Batch actions on filtered set (not just selected)

#### 4.3 Dashboard Customization (🟡 1 tuần)
- [ ] Make dashboard widgets draggable (react-grid-layout)
- [ ] Add/remove widgets modal:
  - Metrics cards
  - Pipeline chart
  - Recent reports
  - Quick actions
  - Custom HTML/JSON
- [ ] Save layout to localStorage/user prefs
- [ ] Add date range picker cho dashboard metrics
- [ ] Export dashboard as PDF/PowerPoint
- [ ] Schedule dashboard email (daily/weekly)

#### 4.4 SSO & Enterprise Auth (🔵 2 tuần)
- [ ] Add SSO buttons trong login page:
  - Google (OAuth2)
  - Microsoft (Azure AD)
  - GitHub (OAuth)
- [ ] Configure NextAuth.js or custom OIDC
- [ ] Add SAML support (if needed)
- [ ] User provisioning (SCIM) từ IdP
- [ ] Role mapping từ IdP groups
- [ ] Logout từ all SPs (single logout)
- [ ] Documentation cho admin cấu hình SSO

#### 4.5 Performance Optimization (🔥 1 tuần)
- [ ] Implement React Query cho data fetching:
  - Caching (5min default)
  - Background refetch
  - Stale-while-revalidate
  - Optimistic updates
- [ ] Code splitting:
  - Dynamic import cho heavy components (CodeMirror, Calendar)
  - Route-based splitting (Settings page)
  - Lazy load icons (lucide-react)
- [ ] Image optimization:
  - Next.js Image component
  - WebP format
  - Lazy loading
- [ ] Bundle analysis:
  - `npm run build -- --analyze`
  - Remove unused dependencies
  - Tree-shaking optimization
- [ ] Database query optimization (backend):
  - Add indexes cho common queries
  - Query result caching (Redis)
  - Pagination với cursor-based

#### 4.6 Testing & Quality (🟡 1 tuần)
- [ ] Unit tests với Jest + React Testing Library:
  - Components: 80% coverage
  - Hooks: 100% coverage
  - Utils: 100% coverage
- [ ] E2E tests với Playwright:
  - Login flow
  - Template creation
  - Job upload + review
  - Report export
- [ ] Visual regression testing (Chromatic/Percy)
- [ ] Accessibility testing (axe-core, manual)
- [ ] Performance testing (Lighthouse CI)
- [ ] Add Storybook cho UI components

#### 4.7 Documentation & Developer Experience (⚡ 3 days)
- [ ] Update README với:
  - Setup instructions (local dev)
  - Environment variables
  - API documentation
  - Component stories
- [ ] Create CONTRIBUTING.md:
  - Git workflow
  - Code style (ESLint + Prettier)
  - Commit conventions (conventional commits)
  - PR template
- [ ] Add inline documentation:
  - JSDoc cho complex functions
  - Component prop comments
  - Architecture decision records (ADRs)
- [ ] Create component library docs (Storybook)
- [ ] Add debugging tips (React DevTools, network tab)

**Deliverables Phase 4:**
- [ ] Settings page hoàn chỉnh
- [ ] Advanced filtering system
- [ ] Customizable dashboard
- [ ] SSO integration
- [ ] Performance improvements (React Query, code splitting)
- [ ] Test coverage >80%
- [ ] Documentation đầy đủ

---

## 📋 12. Component Checklist (MANDATORY)

**Khi thêm feature mới hoặc refactor component, phải check:**

### Design System

- [ ] **Colors:** Dùng semantic tokens (`bg-background`, `text-foreground`, `border`, `muted`)
- [ ] **Spacing:** Tuân theo Tailwind scale (`space-y-2/4/6`, `gap-2/4`)
- [ ] **Typography:** Consistent với system (`text-sm`, `font-medium`, `leading-relaxed`)
- [ ] **Icons:** Chỉ dùng `lucide-react` (không emoji, không custom SVG)
- [ ] **Dark mode:** Test trong cả light/dark themes

### Components (shadcn/ui)

- [ ] **Base components:** Button, Input, Select, Table, Tabs, Dialog, etc.
- [ ] **No custom implementations** (đừng làm lại Button/Table từ scratch)
- [ ] **Variants:** Dùng đúng variant (default, outline, destructive, ghost, secondary)
- [ ] **Sizes:** Dùng size props (sm, md, lg) thay vì custom classes
- [ ] **Composition:** Compose components (Button + Icon, Input + Label)

### States

- [ ] **Loading:** Disabled buttons, spinners, skeleton screens
- [ ] **Empty:** EmptyState component với icon + text + CTA
- [ ] **Error:** Toast + inline Alert (variant="destructive")
- [ ] **Success:** Toast notifications (variant="success")
- [ ] **Disabled:** Tất cả interactive elements có `disabled` state

### Data & API

- [ ] **Tenant context:** Tất cả API calls qua `api` wrapper (auto-add X-Tenant-ID)
- [ ] **Error handling:** Try/catch, show user-friendly error
- [ ] **Loading states:** Show loading indicator trong async operations
- [ ] **Empty data:** Handle `null`, `undefined`, `[]` gracefully
- [ ] **Pagination:** Implement virtual scroll nếu >100 items
- [ ] **Caching:** Consider React Query cho repeated fetches

### Accessibility (a11y)

- [ ] **ARIA labels:** Icon-only buttons có `aria-label`
- [ ] **Form labels:** `htmlFor` + `id` association
- [ ] **Tables:** `<caption>` mô tả table purpose
- [ ] **Keyboard:** Tab order logical, Enter/Space activate buttons
- [ ] **Focus:** Visible focus ring (default browser hoặc custom)
- [ ] **Screen reader:** Role attributes (status, alert, dialog)
- [ ] **Color contrast:** Pass AA (4.5:1) - check với Lighthouse
- [ ] **Skip links:** "Skip to main content" link (sr-only)

### Responsive Design

- [ ] **Mobile-first:** Start từ smallest screen, enhance lên
- [ ] **Breakpoints:** Use Tailwind defaults (sm: 640px, md: 768px, lg: 1024px, xl: 1280px)
- [ ] **Tables:** Wrap trong `overflow-x-auto` cho horizontal scroll
- [ ] **Grids:** Responsive cols (`grid-cols-1 md:grid-cols-2 lg:grid-cols-4`)
- [ ] **Sidebar:** Hidden trên mobile, hamburger menu
- [ ] **Modals:** Full-width trên mobile, centered trên desktop

### Performance

- [ ] **Virtualization:** Use `@tanstack/react-virtual` nếu list >100 items
- [ ] **Memoization:** `useMemo`, `useCallback` cho expensive ops
- [ ] **Lazy loading:** Dynamic imports cho heavy components
- [ ] **Image optimization:** Next.js Image component, WebP format
- [ ] **Bundle size:** Check với `next build --analyze`
- [ ] **Network:** Minimize API calls, debounce search inputs

### Internationalization (i18n)

- [ ] **Vietnamese only:** No hardcoded English trong UI
- [ ] **Extract strings:** Dùng translation function (future-proof)
- [ ] **Date/number formatting:** Use Intl API (đã có trong utils)
- [ ] **RTL support:** Not needed (Vietnamese LTR)

### Testing

- [ ] **Unit tests:** Test logic, not implementation details
- [ ] **E2E tests:** Critical user flows (login → upload → review → export)
- [ ] **Accessibility tests:** Run axe-core in dev/CI
- [ ] **Visual tests:** Storybook + Chromatic for UI components

### Code Quality

- [ ] **TypeScript:** No `any`, proper interfaces
- [ ] **Linting:** ESLint + Next.js rules pass
- [ ] **Formatting:** Prettier consistent
- [ ] **Comments:** Only explain WHY, not WHAT
- [ ] **File size:** Keep components <300 lines (extract nếu lớn)

### Security

- [ ] **XSS:** Sanitize user input (dang tinhr JSON.parse safe)
- [ ] **CSRF:** Next.js CSRF tokens (automatic)
- [ ] **Secrets:** No hardcoded API keys, use env vars
- [ ] **Permissions:** Check user role trước show actions
- [ ] **Audit:** Log important actions (delete, approve)

---

## 🎯 13. Design Principles (Reafirmed)

| Principle | Definition | Example |
|-----------|------------|---------|
| **Data-first** | Show extracted data prominently, templates are config only | Review tab hiển thị JSON trực tiếp |
| **Template Isolation** | Word templates là attachments, không đọc trực tiếp | UI chỉ store S3 key, không parse .docx |
| **Source Independence** | UI không quan tâm PDF hay Sheets, chỉ care job status | `parser_used` badge nhưng không ảnh hưởng workflow |
| **Deterministic** | Job data immutable sau ingestion; edits tạo version mới | reviewed_data separate từ extracted_data |
| **Auditability** | Giữ nguyên source_references, track thay đổi | `source_references` trong extracted_data |

**Violations cần fix:**
- [ ] Source references không hiển thị trong UI → cần show trong Review
- [ ] No version history cho template changes
- [ ] No audit log cho approve/reject actions

---

## 📚 14. References

### API Endpoints Used

| Feature | Endpoint | Method | Auth | Body |
|---------|----------|--------|------|------|
| Templates | `GET /api/v1/templates` | List | JWT | `?page=1&limit=50` |
| Templates | `POST /api/v1/templates` | Create | JWT | `{name, schema_definition, ...}` |
| Templates | `DELETE /api/v1/templates/:id` | Delete | JWT | - |
| Templates | `PATCH /api/v1/templates/:id` | Update | JWT | `{word_template_s3_key}` |
| Templates | `POST /api/v1/templates/scan-word` | Scan | JWT | `multipart/form-data` |
| Jobs | `GET /api/v1/jobs` | List | JWT | `?status=...&template_id=...` |
| Jobs | `POST /api/v1/jobs/upload` | Upload PDF | JWT | `multipart/form-data` |
| Jobs | `POST /api/v1/jobs/ingest-sheet` | Sheets | JWT | `{template_id, sheet_id, ...}` |
| Jobs | `GET /api/v1/jobs/:id` | Detail | JWT | - |
| Jobs | `POST /api/v1/jobs/:id/retry` | Retry | JWT | - |
| Jobs | `DELETE /api/v1/jobs/:id` | Delete | JWT | - |
| Review | `POST /api/v1/review/:id/approve` | Approve | JWT | `{reviewed_data, notes}` |
| Review | `POST /api/v1/review/:id/reject` | Reject | JWT | `{notes}` |
| Reports | `GET /api/v1/reports` | List | JWT | `?page=1&limit=20` |
| Reports | `POST /api/v1/reports` | Create | JWT | `{template_id, job_ids, report_name}` |
| Reports | `GET /api/v1/reports/:id/export` | Export | JWT | `?format=xlsx\|docx\|json` |
| Reports | `DELETE /api/v1/reports/:id` | Delete | JWT | - |
| Sheets | `GET /api/v1/sheets/inspect/by-date` | QA data | JWT | `?month=4&year=2026` |
| Sheets | `GET /api/v1/sheets/inspect/issues` | Issues | JWT | `?month=4&year=2026&document_id=...` |
| Sheets | `GET /api/v1/sheets/inspect/mapping` | Mapping | JWT | - |
| Dashboard | `GET /api/v1/dashboard` | Metrics | JWT | - |
| Auth | `POST /api/v1/auth/login` | Login | No | `{email, password}` |
| Auth | `POST /api/v1/auth/register` | Register | No | `{email, password}` |
| Auth | `POST /api/v1/auth/logout` | Logout | JWT | - |

### File Structure

```
frontend/
├── app/
│   ├── layout.tsx              # Root layout (Sidebar + main)
│   ├── page.tsx                # Dashboard
│   ├── login/page.tsx          # Auth (login/register)
│   ├── documents/page.tsx      # Document list
│   ├── extraction/
│   │   ├── page.tsx            # Main engine (tabs container)
│   │   ├── inspect/page.tsx   # Sheet Inspector (QA)
│   │   └── export-history/page.tsx  # [NEW] Export history
│   └── settings/page.tsx       # [NEW] Settings
├── components/
│   ├── layout/
│   │   ├── sidebar.tsx         # Navigation + tenant selector
│   │   └── mobile-nav.tsx      # [NEW] Hamburger menu
│   ├── extraction/
│   │   ├── templates-tab.tsx   # Template management
│   │   ├── jobs-tab.tsx        # Upload + job list
│   │   ├── review-tab.tsx      # Review workflow
│   │   ├── review-split-pane.tsx  # [NEW] Split-pane version
│   │   ├── export-tab.tsx      # Report aggregation
│   │   ├── export-unified.tsx  # [NEW] Consolidated export
│   │   ├── calendar-picker.tsx # Calendar (for export)
│   │   ├── calendar-grid.tsx   # [NEW] Shared calendar component
│   │   ├── sheet-inspector.tsx # QA tool
│   │   ├── status-filter-bar.tsx  # [NEW] Reusable filter
│   │   ├── bulk-action-bar.tsx    # [NEW] Bulk operations
│   │   └── job-actions.tsx     # Dropdown actions per job
│   ├── ui/                     # shadcn/ui components
│   └── shared/
│       ├── virtual-table.tsx   # Virtual scroll wrapper
│       ├── json-editor.tsx     # CodeMirror wrapper
│       ├── empty-state.tsx     # Reusable empty state
│       ├── skeleton.tsx        # Skeleton loaders
│       └── filter-builder.tsx  # Advanced filtering
├── lib/
│   ├── api.ts                  # API wrapper (tenant header)
│   ├── constants.ts            # [NEW] Shared constants
│   ├── types.ts                # TypeScript interfaces
│   ├── utils.ts                # Helpers (formatDate, downloadBlob)
│   ├── hooks/
│   │   ├── use-polling.ts      # Real-time polling
│   │   ├── use-keyboard.ts     # Keyboard shortcuts
│   │   ├── use-sidebar.ts      # Sidebar state
│   │   └── use-virtualization.ts # Virtual scroll logic
│   └── auth.ts                 # Auth context
├── styles/
│   └── globals.css             # Global styles (if needed)
└── tailwind.config.ts
```

---

## ✅ 15. Immediate Action Items (Next 2 Weeks)

### Week 1: Foundation

- [ ] **Day 1-2:** Extract shared constants (STATUS_VI, statusBadgeVariant)
- [ ] **Day 2-3:** Add skeleton loaders (Dashboard, Tables)
- [ ] **Day 3-4:** Virtual scrolling proof-of-concept (JobsTab)
- [ ] **Day 4-5:** Mobile sidebar hamburger + overlay

### Week 2: High-Impact Features

- [ ] **Day 1-3:** Bulk operations trong Review (checkboxes + bulk approve/delete)
- [ ] **Day 3-4:** Real-time polling (Dashboard + Jobs)
- [ ] **Day 5:** Accessibility audit + fixes

**Stretch goal (nếu còn thời gian):**
- [ ] Start split-pane Review redesign (partial)

---

## 🏆 Success Metrics

| Metric | Baseline | Target (Phase 1) | Measurement |
|--------|----------|------------------|-------------|
| Review time per job | 60s | <45s | User timing |
| User satisfaction (NPS) | ? | >50 | Survey |
| Template creation rate | ? | +30% | Funnel analytics |
| Job upload success | ? | >98% | Error tracking |
| Mobile usability | ❌ | ✅ | User testing |
| Accessibility score | ? | >90 (axe) | Lighthouse |

---

**END OF DOCUMENTATION**

*This document is the single source of truth for frontend architecture and design decisions. Update with each major UX change. Last updated: 2026-04-23.*

### API Endpoints Used

| Feature | Endpoint | Method |
|---------|----------|--------|
| Templates | `GET /api/v1/templates` | List |
| Templates | `POST /api/v1/templates` | Create |
| Templates | `DELETE /api/v1/templates/:id` | Delete |
| Templates | `PATCH /api/v1/templates/:id` | Update |
| Templates | `POST /api/v1/templates/scan-word` | Word scan |
| Jobs | `GET /api/v1/jobs` | List |
| Jobs | `POST /api/v1/jobs/upload` | Upload PDF |
| Jobs | `POST /api/v1/jobs/ingest-sheet` | Google Sheets |
| Jobs | `GET /api/v1/jobs/:id` | Detail |
| Jobs | `POST /api/v1/jobs/:id/retry` | Retry |
| Jobs | `DELETE /api/v1/jobs/:id` | Delete |
| Review | `POST /api/v1/review/:id/approve` | Approve |
| Review | `POST /api/v1/review/:id/reject` | Reject |
| Reports | `GET /api/v1/reports` | List |
| Reports | `POST /api/v1/reports` | Create |
| Reports | `GET /api/v1/reports/:id/export?format=xlsx|docx|json` | Export |
| Sheets | `GET /api/v1/sheets/inspect/by-date` | QA data |

### File Structure

```
frontend/
├── app/
│   ├── layout.tsx              # Root layout with Sidebar
│   ├── page.tsx                # Dashboard
│   ├── login/page.tsx          # Auth
│   ├── documents/page.tsx      # Document list
│   ├── extraction/
│   │   ├── page.tsx            # Main engine with tabs
│   │   └── inspect/page.tsx   # Sheet Inspector
├── components/
│   ├── layout/
│   │   └── sidebar.tsx         # Navigation + tenant selector
│   ├── extraction/
│   │   ├── templates-tab.tsx   # Template management
│   │   ├── jobs-tab.tsx        # Upload + job list
│   │   ├── review-tab.tsx      # Review workflow
│   │   ├── export-tab.tsx      # Report aggregation
│   │   ├── calendar-picker.tsx # Calendar UI (shared?)
│   │   └── sheet-inspector.tsx # QA tool
│   └── ui/                     # shadcn/ui components
├── lib/
│   ├── api.ts                  # API wrapper with tenant header
│   ├── types.ts                # TypeScript interfaces
│   ├── utils.ts                # Helpers (formatDate, downloadBlob)
│   └── auth.ts                 # Auth context
└── tailwind.config.ts
```

---

## ✅ 15. Immediate Action Items

### For Next Sprint:

1. **Fix Review tab UX** - Split pane redesign (highest impact)
2. **Add bulk operations** - Checkboxes + bulk approve/delete
3. **Implement virtual scroll** - For job tables (1000+ rows)
4. **Add real-time updates** - Polling fallback
5. **Extract shared constants** - Remove duplicate STATUS_VI
6. **Add accessibility labels** - Aria for all interactive elements
7. **Mobile sidebar** - Hamburger menu
8. **Consolidate Export modes** - Single creation flow

### Quick Wins (Can ship same day):

- [ ] Add skeleton loaders
- [ ] Add toast on template delete
- [ ] Fix date formatting consistency
- [ ] Add "Select all" in job filters
- [ ] Show parser_used in job table
- [ ] Add confirmation dialog for bulk delete

---

## 🔧 16. Quick Debug & Troubleshooting Guide

### 16.1 Common Errors & Fixes

| Error | Cause | Fix |
|-------|-------|-----|
| `Cannot read properties of undefined (reading 'inspect')` | `api.sheets` not defined | Add sheets methods to `lib/api.ts` |
| `Property 'X' does not exist on type 'Y'` | Missing type definition | Add interface in `lib/types.ts` |
| `Hydration mismatch` | Server/client render difference | Check `useEffect` dependencies, use `suppressHydrationWarning` |
| `Invalid hook call` | Hooks called conditionally | Ensure hooks at component top-level |
| `Maximum update depth exceeded` | Infinite re-render | Check `useEffect` dependencies, avoid setState in render |
| `Failed to fetch` | API endpoint not running | Start backend: `docker-compose up` |
| `401 Unauthorized` | Token expired/missing | Call `login()` again, check `auth.ts` |

### 16.2 Debug Checklist

**Before reporting bug:**
- [ ] Run `npm run dev` and check console for errors
- [ ] Verify backend is running (`curl http://localhost:8000/api/v1/health`)
- [ ] Check Network tab for failing API calls
- [ ] Clear browser localStorage (auth tokens may be stale)
- [ ] Test in incognito mode (disable extensions)
- [ ] Run `npm run lint` and fix warnings
- [ ] Check TypeScript errors: `npx tsc --noEmit`

### 16.3 Environment Setup

```bash
# 1. Install dependencies
cd frontend
npm install

# 2. Set environment variables
cp .env.local.example .env.local
# Edit .env.local:
# NEXT_PUBLIC_API_URL=http://localhost:8000

# 3. Run dev server
npm run dev

# 4. Open http://localhost:3000
```

### 16.4 Hot Reload Issues

If changes not reflecting:
```bash
# Clear Next.js cache
rm -rf .next
npm run dev

# Or force refresh: Ctrl+Shift+R (Windows) / Cmd+Shift+R (Mac)
```

### 16.5 API Debug Mode

Enable verbose logging in `lib/api.ts`:
```tsx
// Add before fetch:
console.log(`[API] ${endpoint}`, options);

// After response:
console.log(`[API] ${endpoint} →`, response.status, data);
```

---

## 🏆 16. Success Metrics (Updated)

| Metric | Baseline | Target (Phase 1) | Measurement |
|--------|----------|------------------|-------------|
| Review time per job | 60s | <45s | User timing |
| User satisfaction (NPS) | ? | >50 | Survey |
| Templates created/week | ? | +50% | Funnel analytics |
| Job upload success | ? | >98% | Error tracking |
| Mobile usability | ❌ | ✅ | User testing |
| Accessibility score | ? | >90 (axe) | Lighthouse |
| Bundle size (initial) | ? | <200KB | `next build` |
| Time to interactive | ? | <3s | Lighthouse |

**How to measure:**
- Use `console.time()` in review flow
- Add analytics (PostHog, Mixpanel) for funnel tracking
- Run Lighthouse CI on PRs
- User testing sessions (bi-weekly)

---

**END OF DOCUMENTATION**

*This document is the single source of truth for frontend architecture and design decisions. Update with each major UX change. Last updated: 2026-04-24.*
