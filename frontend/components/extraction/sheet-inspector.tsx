"use client";

import { Fragment, useCallback, useEffect, useState } from "react";
import { RefreshCw, Download, ChevronLeft, ChevronRight, AlertTriangle, CheckCircle2, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { TableSkeleton } from "@/components/ui/table-skeleton";
import { api } from "@/lib/api";
import { downloadBlob, getMonthName } from "@/lib/utils";
import type {
  SheetInspectDay,
  SheetInspectJob,
  SheetIssue,
  ColumnMappingRow,
} from "@/lib/types";
import { toast } from "sonner";
import { CalendarGrid } from "./calendar-grid";

// ─── Types for internal use ────────────────────────────────────────────────────

type TabKey = "grid" | "mapping" | "issues";

const SHEETS = [
  { id: "BC NGÀY", label: "📋 BC NGÀY", color: "bg-green-100 dark:bg-green-900/30" },
  { id: "CNCH",    label: "🚑 CNCH",     color: "bg-blue-100 dark:bg-blue-900/30" },
  { id: "CHI VIỆN", label: "🏢 CHI VIỆN", color: "bg-purple-100 dark:bg-purple-900/30" },
  { id: "VỤ CHÁY", label: "🔥 VỤ CHÁY", color: "bg-red-100 dark:bg-red-900/30" },
];

// Key STTs to display in the grid
const GRID_STTS = [
  { stt: "2",  label: "STT 2",  desc: "Vụ cháy" },
  { stt: "14", label: "STT 14", desc: "CNCH" },
  { stt: "22", label: "STT 22", desc: "Tin bài MXH" },
  { stt: "31", label: "STT 31", desc: "Tổng kiểm tra" },
  { stt: "32", label: "STT 32", desc: "Định kỳ" },
  { stt: "33", label: "STT 33", desc: "Đột xuất" },
  { stt: "43", label: "STT 43", desc: "PA PC06" },
  { stt: "47", label: "STT 47", desc: "PA PC08" },
  { stt: "50", label: "STT 50", desc: "PA PC09" },
  { stt: "55", label: "STT 55", desc: "CBCS HL" },
  { stt: "60", label: "STT 60", desc: "Lái xe" },
  { stt: "61", label: "STT 61", desc: "Lái tàu" },
];

// ─── Cell color helpers ────────────────────────────────────────────────────────

function cellColor(value: number | null, present: boolean): string {
  if (!present || value === null) return "bg-red-50 dark:bg-red-950/30 text-red-600"; // missing
  if (value === 0) return "bg-yellow-50 dark:bg-yellow-950/30 text-yellow-700";       // zero
  return "bg-green-50 dark:bg-green-950/30 text-green-700";                         // has value
}

function issueSeverityColor(severity: string): "destructive" | "warning" | "secondary" {
  if (severity === "missing") return "destructive";
  if (severity === "mismatch") return "destructive";
  return "warning";
}

function issueSeverityLabel(severity: string): string {
  if (severity === "missing") return "🔴 MISSING";
  if (severity === "mismatch") return "🔴 MISMATCH";
  return "🟡 ZERO";
}

// ─── Main component ─────────────────────────────────────────────────────────────

interface SheetInspectorProps {
  month: number;
  year: number;
  documentId?: string;
}

export function SheetInspector({ month: initMonth, year: initYear, documentId }: SheetInspectorProps) {
  const [month, setMonth] = useState(initMonth);
  const [year, setYear] = useState(initYear);
  const [selectedDay, setSelectedDay] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabKey>("grid");
  const [selectedSheet, setSelectedSheet] = useState("BC NGÀY");

  const [inspectData, setInspectData] = useState<SheetInspectDay[]>([]);
  const [issues, setIssues] = useState<SheetIssue[]>([]);
  const [mapping, setMapping] = useState<ColumnMappingRow[]>([]);

  const [loadingInspect, setLoadingInspect] = useState(false);
  const [loadingIssues, setLoadingIssues] = useState(false);
  const [loadingMapping, setLoadingMapping] = useState(false);

  // ── Load data ──────────────────────────────────────────────────────────────

  const loadInspect = useCallback(async () => {
    setLoadingInspect(true);
    const res = await api.sheets.inspect(month, year);
    setLoadingInspect(false);
    if (res.ok) {
      setInspectData(res.data as SheetInspectDay[]);
    } else {
      toast.error(`Lỗi tải dữ liệu: ${res.error}`);
    }
  }, [month, year]);

  const loadIssues = useCallback(async () => {
    setLoadingIssues(true);
    const res = await api.sheets.issues(month, year, documentId);
    setLoadingIssues(false);
    if (res.ok) {
      setIssues(res.data as SheetIssue[]);
    } else {
      toast.error(`Lỗi tải issues: ${res.error}`);
    }
  }, [month, year, documentId]);

  const loadMapping = useCallback(async () => {
    setLoadingMapping(true);
    const res = await api.sheets.mapping();
    setLoadingMapping(false);
    if (res.ok) {
      setMapping(res.data as ColumnMappingRow[]);
    } else {
      toast.error(`Lỗi tải mapping: ${res.error}`);
    }
  }, []);

  useEffect(() => { loadInspect(); }, [loadInspect]);
  useEffect(() => { loadMapping(); }, [loadMapping]);

  // ── Coverage summary ────────────────────────────────────────────────────────

  const totalJobs = inspectData.reduce((s, d) => s + d.job_count, 0);
  const jobsWithIssues = inspectData.reduce((s, d) => s + (d.has_issues ? 1 : 0), 0);
  const totalIssues = issues.length;
  const missingCount = issues.filter((i) => i.severity === "missing").length;
  const mappedCols = mapping.filter((m) => m.status === "mapped").length;
  const totalCols = mapping.length;

  // ── Month navigation ────────────────────────────────────────────────────

  function prevMonth() {
    if (month === 1) { setMonth(12); setYear((y) => y - 1); }
    else setMonth((m) => m - 1);
  }
  function nextMonth() {
    if (month === 12) { setMonth(1); setYear((y) => y + 1); }
    else setMonth((m) => m + 1);
  }

  // ── Export JSON ──────────────────────────────────────────────────────────

  function handleExportJson() {
    const payload = { month, year, documentId, inspectData, issues, mapping };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    downloadBlob(blob, `SheetInspector_${year}_${String(month).padStart(2, "0")}.json`);
    toast.success("Đã tải JSON!");
  }

  // ── Day selection from calendar ──────────────────────────────────────────

  const selectedDayData = selectedDay
    ? inspectData.find((d) => d.date === selectedDay) ?? null
    : null;

  return (
    <div className="space-y-3">
      {/* ── Header: filters + actions ──────────────────────────────────── */}
      <div className="flex items-center gap-3 flex-wrap">
        <Button variant="ghost" size="icon" onClick={prevMonth} aria-label="Tháng trước">
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <span className="font-semibold min-w-36 text-center">
          {getMonthName(month, year)}
        </span>
        <Button variant="ghost" size="icon" onClick={nextMonth} aria-label="Tháng sau">
          <ChevronRight className="h-4 w-4" />
        </Button>

        <Select value={String(month)} onValueChange={(v) => setMonth(Number(v))}>
          <SelectTrigger className="w-24">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {Array.from({ length: 12 }, (_, i) => (
              <SelectItem key={i + 1} value={String(i + 1)}>Tháng {i + 1}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={String(year)} onValueChange={(v) => setYear(Number(v))}>
          <SelectTrigger className="w-28">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {[2024, 2025, 2026, 2027].map((y) => (
              <SelectItem key={y} value={String(y)}>{y}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Button
          variant="outline"
          size="sm"
          onClick={() => { loadInspect(); loadIssues(); }}
          disabled={loadingInspect || loadingIssues}
        >
          <RefreshCw className={`h-4 w-4 mr-1.5 ${loadingInspect ? "animate-spin" : ""}`} />
          Tải lại
        </Button>

        <Button variant="outline" size="sm" onClick={handleExportJson}>
          <Download className="h-4 w-4 mr-1.5" />
          Export JSON
        </Button>
      </div>

      {/* ── Main layout: sidebar + content ──────────────────────────────── */}
      <div className="flex gap-4 flex-col md:flex-row">
        {/* ── Sidebar: sheet tree ──────────────────────────────────────── */}
        <div className="shrink-0 md:w-48">
          <p className="text-xs font-semibold text-muted-foreground uppercase mb-2">
            Sheets
          </p>
          <div className="space-y-1">
            {SHEETS.map((s) => (
              <button
                key={s.id}
                onClick={() => setSelectedSheet(s.id)}
                className={`
                  w-full text-left px-3 py-2 rounded-md text-sm
                  transition-colors cursor-pointer
                  ${selectedSheet === s.id
                    ? `${s.color} font-semibold border border-primary`
                    : "hover:bg-accent"
                  }
                `}
              >
                {s.label}
              </button>
            ))}
          </div>

          {/* Quick stats */}
          <div className="mt-4 space-y-1 text-xs">
            <div className="flex justify-between">
              <span>Tháng này:</span>
              <span className="font-semibold">{totalJobs} hồ sơ</span>
            </div>
            <div className="flex justify-between">
              <span>Có issues:</span>
              <span className={`font-semibold ${jobsWithIssues > 0 ? "text-red-600" : "text-green-600"}`}>
                {jobsWithIssues} ngày
              </span>
            </div>
          </div>
        </div>

        {/* ── Content: tabs ──────────────────────────────────────────────── */}
        <div className="flex-1 min-w-0">
          <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as TabKey)}>
            <TabsList className="mb-3">
              <TabsTrigger value="calendar">📅 Calendar</TabsTrigger>
              <TabsTrigger value="grid">📊 Grid</TabsTrigger>
              <TabsTrigger value="mapping">🔗 Mapping</TabsTrigger>
              <TabsTrigger value="issues">
                ⚠️ Issues
                {totalIssues > 0 && (
                  <Badge variant="destructive" className="ml-1.5 text-xs px-1 py-0">
                    {totalIssues}
                  </Badge>
                )}
              </TabsTrigger>
            </TabsList>

            {/* ── Tab 1: Calendar ───────────────────────────────────────── */}
            <TabsContent value="calendar" className="mt-0">
              <CalendarTab
                month={month}
                year={year}
                inspectData={inspectData}
                loading={loadingInspect}
              />
            </TabsContent>

            {/* ── Tab 2: Grid ────────────────────────────────────────── */}
            <TabsContent value="grid" className="mt-0">
              <GridTab
                inspectData={inspectData}
                selectedDay={selectedDay}
                onSelectDay={setSelectedDay}
                loading={loadingInspect}
              />
            </TabsContent>


            {/* ── Tab 3: Mapping ─────────────────────────────────────── */}
            <TabsContent value="mapping" className="mt-0">
              <MappingTab mapping={mapping} loading={loadingMapping} />
            </TabsContent>

            {/* ── Tab 4: Issues ─────────────────────────────────────── */}
            <TabsContent value="issues" className="mt-0">
              <IssuesTab
                issues={issues}
                loading={loadingIssues}
                onReload={loadIssues}
              />
            </TabsContent>
          </Tabs>
        </div>
      </div>

      {/* ── Status bar ──────────────────────────────────────────────────── */}
      <Separator />
      <div className="flex gap-4 flex-wrap text-xs text-muted-foreground">
        <span>Tổng STT: <strong>61</strong></span>
        <span>·</span>
        <span>Cột đã map: <strong className="text-green-600">{mappedCols}/{totalCols}</strong></span>
        <span>·</span>
        <span>Hồ sơ tháng: <strong>{totalJobs}</strong></span>
        <span>·</span>
        <span>Issues: <strong className={totalIssues > 0 ? "text-red-600" : "text-green-600"}>
          {totalIssues} ({missingCount} missing)
        </strong></span>
      </div>
    </div>
  );
}

// ─── Tab 1: Grid ────────────────────────────────────────────────────────────────

interface GridTabProps {
  inspectData: SheetInspectDay[];
  selectedDay: string | null;
  onSelectDay: (date: string) => void;
  loading: boolean;
}

function GridTab({ inspectData, selectedDay, onSelectDay, loading }: GridTabProps) {
  const [expandedDay, setExpandedDay] = useState<string | null>(null);
  const days = inspectData.filter((d) => d.job_count > 0);

  if (loading) {
    return <TableSkeleton rows={8} columns={14} headerHeight="h-10" rowHeight="h-12" />;
  }

  if (days.length === 0) {
    return (
      <Alert variant="warning">
        <AlertDescription>Chưa có hồ sơ nào trong tháng này.</AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-2">
      {/* Header row */}
      <div className="overflow-x-auto rounded-md border">
        <table className="w-full text-xs">
          <caption className="sr-only">Lưới theo dõi hồ sơ theo ngày và STT</caption>
          <thead>
            <tr className="bg-muted/50">
              <th className="text-left px-3 py-2 font-semibold w-24 sticky left-0 bg-muted/50">Ngày</th>
              {GRID_STTS.map((s) => (
                <th key={s.stt} className="text-center px-2 py-2 min-w-16">
                  <div>{s.label}</div>
                  <div className="text-muted-foreground font-normal">{s.desc}</div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {days.map((day) => {
              const isExpanded = expandedDay === day.date;
              const totalCoverage = day.jobs.reduce((sum, job) => sum + (job.stt_coverage?.total ?? 0), 0);
              const populatedCoverage = day.jobs.reduce((sum, job) => sum + (job.stt_coverage?.populated ?? 0), 0);
              const isComplete = totalCoverage > 0 && populatedCoverage === totalCoverage;
              const isEmpty = populatedCoverage === 0;
              const isPartial = !isComplete && !isEmpty;
              const rowClass = day.has_issues
                ? "bg-red-50/50 dark:bg-red-950/10"
                : isComplete
                  ? "bg-green-50/30 dark:bg-green-950/10"
                  : isPartial
                    ? "bg-yellow-50/30 dark:bg-yellow-950/10"
                    : "bg-red-50/30 dark:bg-red-950/5";
              // Aggregate stt_values across all jobs for the day
              const aggValues: Record<string, number> = {};
              day.jobs.forEach((j) => {
                Object.entries(j.stt_values).forEach(([k, v]) => {
                  aggValues[k] = (aggValues[k] ?? 0) + v;
                });
              });

              return (
                <Fragment key={day.date}>
                  <tr
                    key={day.date}
                    className={`cursor-pointer hover:bg-accent/50 ${rowClass}`}
                    onClick={() => setExpandedDay(isExpanded ? null : day.date)}
                  >
                    <td className="px-3 py-2 font-medium sticky left-0 bg-background">
                      {day.date.slice(8, 10)}/{day.date.slice(5, 7)}
                      {isComplete && <span className="ml-1">✅</span>}
                      {isPartial && <span className="ml-1">⚠️</span>}
                      {isEmpty && <span className="ml-1">❌</span>}
                      {day.has_issues && <span className="ml-1 text-red-500">⚠️</span>}
                    </td>
                    {GRID_STTS.map((s) => {
                      const key = `stt_${s.stt.padStart(2, "0")}`;
                      const val = aggValues[key] ?? 0;
                      const present = day.jobs.some((j) =>
                        j.btk_rows.some((r: { stt: string }) => r.stt === s.stt)
                      );
                      return (
                        <td key={s.stt} className={`text-center px-2 py-2 ${cellColor(val, present)}`}>
                          {val > 0 ? val : present ? "0" : "—"}
                        </td>
                      );
                    })}
                  </tr>
                  {isExpanded && (
                    <tr className="bg-muted/10 text-xs">
                      <td colSpan={GRID_STTS.length + 1} className="px-4 py-2">
                        <div className="flex items-center gap-2">
                          <Badge variant={isComplete ? "success" : isPartial ? "warning" : "destructive"}>
                            {isComplete ? "Complete" : isPartial ? "Partial" : "Empty"}
                          </Badge>
                          <span className="text-muted-foreground">STT coverage: {populatedCoverage}/{totalCoverage || 0}</span>
                        </div>
                      </td>
                    </tr>
                  )}
                  {isExpanded && day.jobs.map((job) => (
                    <tr key={`${day.date}-${job.id}`} className="bg-muted/20 text-xs">
                      <td colSpan={GRID_STTS.length + 1} className="px-4 py-2">
                        <div className="flex items-center gap-3 mb-2">
                          <span className="font-medium">{job.file_name}</span>
                          <Badge variant={job.status === "approved" ? "success" : job.status === "failed" ? "destructive" : "secondary"}>
                            {job.status}
                          </Badge>
                          {job.stt_coverage && (
                            <span className="text-muted-foreground">
                              STT: {job.stt_coverage.populated}/{job.stt_coverage.total}
                            </span>
                          )}
                        </div>
                        {job.btk_rows.length > 0 && (
                          <div className="overflow-auto rounded border max-h-48">
                            <table className="w-full text-xs">
                              <thead>
                                <tr className="bg-muted/50">
                                  <th className="text-left px-2 py-1">STT</th>
                                  <th className="text-left px-2 py-1">Nội dung</th>
                                  <th className="text-right px-2 py-1">Kết quả</th>
                                </tr>
                              </thead>
                              <tbody>
                                {job.btk_rows.map((r: { stt: string; noi_dung: string; ket_qua: number }, i: number) => (
                                  <tr key={i} className={r.ket_qua === 0 ? "bg-yellow-50/50 dark:bg-yellow-950/10" : ""}>
                                    <td className="px-2 py-1">{r.stt}</td>
                                    <td className="px-2 py-1">{r.noi_dung}</td>
                                    <td className={`text-right px-2 py-1 font-mono ${r.ket_qua === 0 ? "text-yellow-700" : "text-green-700"}`}>
                                      {r.ket_qua}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}


// ─── Tab 2: Calendar ────────────────────────────────────────────────────────────

interface CalendarTabProps {
  month: number;
  year: number;
  inspectData: SheetInspectDay[];
  loading: boolean;
}

function CalendarTab({ month, year, inspectData, loading }: CalendarTabProps) {
  const [selectedDay, setSelectedDay] = useState<string | null>(null);

  if (loading) {
    return (
      <div className="h-48 flex items-center justify-center">
        <RefreshCw className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  // Status helpers (same as CalendarPicker)
  type DayStatus = "complete" | "partial" | "issues" | "empty";

  function inspectDayStatus(day: SheetInspectDay): DayStatus {
    if (day.job_count === 0) return "empty";
    if (day.has_issues) return "issues";
    if (day.approved_count > 0) return "complete";
    return "partial";
  }

  function inspectDayBgClass(s: DayStatus): string {
    switch (s) {
      case "complete": return "bg-green-100 dark:bg-green-900/40";
      case "partial": return "bg-yellow-100 dark:bg-yellow-900/40";
      case "issues": return "bg-red-100 dark:bg-red-900/40";
      case "empty": return "bg-muted/30";
    }
    return "";
  }

  function inspectDayBorderClass(s: DayStatus, selected: boolean): string {
    if (selected) return "border-blue-600 border-2 ring-2 ring-blue-200 dark:ring-blue-800";
    switch (s) {
      case "complete": return "border-green-300 dark:border-green-700";
      case "partial": return "border-yellow-300 dark:border-yellow-700";
      case "issues": return "border-red-300 dark:border-red-700";
      case "empty": return "border-transparent";
    }
    return "";
  }

  return (
    <div className="space-y-4">
      <CalendarGrid
        month={month}
        year={year}
        days={inspectData}
        selectedDay={selectedDay}
        onSelectDay={setSelectedDay}
        showHeader={false}
        showLegend={true}
        renderDay={(dayData, dayNumber, isSelected) => {
          const s = inspectDayStatus(dayData);
          return (
            <>
              <span className={`text-sm font-medium ${s !== "empty" ? "text-foreground" : "text-muted-foreground"}`}>
                {dayNumber}
              </span>
              {dayData.job_count > 0 && (
                <span className="text-[10px] leading-none text-muted-foreground">
                  {dayData.job_count}
                </span>
              )}
            </>
          );
        }}
        getCellClassName={(dayData, isSelected) => {
          const s = inspectDayStatus(dayData);
          return `${inspectDayBgClass(s)} ${inspectDayBorderClass(s, isSelected)}`;
        }}
        getCellTitle={(dayData) => `${dayData.job_count} hồ sơ · ${dayData.approved_count} duyệt${dayData.has_issues ? " · ⚠️" : ""}`}
      />
      {selectedDay && (
        <div className="mt-4 border rounded-md p-4">
          <h4 className="font-semibold mb-2">
            Chi tiết ngày {selectedDay}
          </h4>
          <p className="text-sm text-muted-foreground">
            Xem chi tiết trong tab Grid hoặc chức năng đang phát triển.
          </p>
        </div>
      )}
    </div>
  );
}


// ─── Tab 3: Mapping ────────────────────────────────────────────────────────────

interface MappingTabProps {
  mapping: ColumnMappingRow[];
  loading: boolean;
}

function MappingTab({ mapping, loading }: MappingTabProps) {
  if (loading) {
    return <TableSkeleton rows={8} columns={5} />;
  }

  if (!mapping.length) {
    return <p className="text-sm text-muted-foreground">Chưa có mapping data.</p>;
  }

  const mapped = mapping.filter((m) => m.status === "mapped").length;
  const unmapped = mapping.filter((m) => m.status === "unmapped").length;
  const skipped = mapping.filter((m) => m.status === "skipped").length;

  return (
    <div className="space-y-3">
      <div className="flex gap-4 text-xs text-muted-foreground">
        <span>🟢 Map: <strong className="text-green-600">{mapped}</strong></span>
        <span>🟡 Unmapped: <strong className="text-yellow-600">{unmapped}</strong></span>
        <span>⬜ Skipped: <strong>{skipped}</strong></span>
      </div>

      <div className="overflow-x-auto rounded-md border">
        <table className="w-full text-xs">
          <caption className="sr-only">Ánh xạ cột Excel sang trường dữ liệu</caption>
          <thead>
            <tr className="bg-muted/50">
              <th className="text-left px-3 py-2">Col</th>
              <th className="text-left px-3 py-2">Header</th>
              <th className="text-center px-3 py-2">STT</th>
              <th className="text-left px-3 py-2">Field</th>
              <th className="text-center px-3 py-2">Status</th>
            </tr>
          </thead>
          <tbody>
            {mapping.map((row) => (
              <tr
                key={row.col_index}
                className={`
                  ${row.status === "unmapped" ? "bg-yellow-50/50 dark:bg-yellow-950/10" : ""}
                  ${row.status === "skipped" ? "bg-muted/20" : ""}
                  hover:bg-accent/50
                `}
              >
                <td className="px-3 py-2 font-mono font-semibold">{row.col_letter}</td>
                <td className="px-3 py-2 max-w-48 truncate">{row.col_header}</td>
                <td className="px-3 py-2 text-center">
                  {row.stt ? `STT ${row.stt}` : "—"}
                </td>
                <td className="px-3 py-2 font-mono max-w-48 truncate">{row.field || "—"}</td>
                <td className="px-3 py-2 text-center">
                  {row.status === "mapped" && <CheckCircle2 className="inline h-3.5 w-3.5 text-green-600" />}
                  {row.status === "unmapped" && <AlertTriangle className="inline h-3.5 w-3.5 text-yellow-600" />}
                  {row.status === "skipped" && <span className="text-muted-foreground">—</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─── Tab 4: Issues ─────────────────────────────────────────────────────────────

interface IssuesTabProps {
  issues: SheetIssue[];
  loading: boolean;
  onReload: () => void;
}

function IssuesTab({ issues, loading, onReload }: IssuesTabProps) {
  if (loading) {
    return <TableSkeleton rows={6} columns={5} />;
  }

  if (!issues.length) {
    return (
      <div className="space-y-3">
        <Alert variant="success">
          <AlertDescription>
            <CheckCircle2 className="inline h-4 w-4 mr-1.5" />
            Không có issue nào — tất cả STT đều OK!
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  const byDate: Record<string, SheetIssue[]> = {};
  issues.forEach((issue) => {
    if (!byDate[issue.date]) byDate[issue.date] = [];
    byDate[issue.date].push(issue);
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          {issues.length} issue{issues.length !== 1 ? "s" : ""} phát hiện
        </p>
        <Button variant="outline" size="sm" onClick={onReload}>
          <RefreshCw className="h-3.5 w-3.5 mr-1.5" />
          Tải lại
        </Button>
      </div>

      {Object.entries(byDate).map(([date, dateIssues]) => (
        <div key={date} className="space-y-2">
          <h4 className="text-sm font-semibold">{date}</h4>
          <div className="overflow-x-auto rounded-md border">
            <table className="w-full text-xs">
              <caption className="sr-only">Danh sách sự khác biệt giữa Excel và hệ thống</caption>
              <thead>
                <tr className="bg-muted/50">
                  <th className="text-left px-3 py-2">STT</th>
                  <th className="text-left px-3 py-2">Mô tả</th>
                  <th className="text-right px-3 py-2">Excel</th>
                  <th className="text-right px-3 py-2">Hệ thống</th>
                  <th className="text-left px-3 py-2">Hồ sơ</th>
                </tr>
              </thead>
              <tbody>
                {dateIssues.map((issue, i) => (
                  <tr key={i} className={`
                    ${issue.severity === "missing" ? "bg-red-50/50 dark:bg-red-950/10" : "bg-yellow-50/50 dark:bg-yellow-950/10"}
                    hover:bg-accent/50
                  `}>
                    <td className="px-3 py-2 font-mono font-semibold">{issue.stt}</td>
                    <td className="px-3 py-2 max-w-48 truncate" title={issue.description}>
                      {issue.label}
                    </td>
                    <td className={`px-3 py-2 text-right font-mono ${issue.excel_value === null ? "text-red-500 italic" : "text-foreground"}`}>
                      {issue.excel_value === null ? "null" : issue.excel_value}
                    </td>
                    <td className="px-3 py-2 text-right font-mono">{issue.system_value}</td>
                    <td className="px-3 py-2 max-w-32 truncate text-muted-foreground" title={issue.file_name}>
                      {issue.file_name || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  );
}
