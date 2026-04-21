"use client";

import { useCallback, useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, BarChart3 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { Separator } from "@/components/ui/separator";
import { api } from "@/lib/api";
import { getMonthName } from "@/lib/utils";
import type { CalendarDay, CalendarJob, Template } from "@/lib/types";
import { toast } from "sonner";

// ─── Status helpers ─────────────────────────────────────────────────────────────

type DayStatus = "complete" | "partial" | "issues" | "empty";

function dayStatus(day: CalendarDay): DayStatus {
  if (day.job_count === 0) return "empty";
  if (day.has_issues) return "issues";
  if (day.approved_count > 0) return "complete";
  return "partial";
}

function dayBgClass(s: DayStatus): string {
  switch (s) {
    case "complete":  return "bg-green-100 dark:bg-green-900/40";
    case "partial":   return "bg-yellow-100 dark:bg-yellow-900/40";
    case "issues":    return "bg-red-100 dark:bg-red-900/40";
    case "empty":     return "bg-muted/30";
  }
}

function dayBorderClass(s: DayStatus, selected: boolean): string {
  if (selected) return "border-blue-600 border-2 ring-2 ring-blue-200 dark:ring-blue-800";
  switch (s) {
    case "complete":  return "border-green-300 dark:border-green-700";
    case "partial":   return "border-yellow-300 dark:border-yellow-700";
    case "issues":    return "border-red-300 dark:border-red-700";
    case "empty":     return "border-transparent";
  }
}

function jobBadgeVariant(status: string): "success" | "warning" | "destructive" | "secondary" | "info" {
  if (status === "approved" || status === "aggregated") return "success";
  if (status === "ready_for_review") return "info";
  if (status === "failed" || status === "rejected") return "destructive";
  if (["pending", "processing", "extracted", "enriching"].includes(status)) return "warning";
  return "secondary";
}

function jobStatusLabel(status: string): string {
  const m: Record<string, string> = {
    approved: "✅ Đã duyệt",
    aggregated: "📊 Đã gom",
    ready_for_review: "🔍 Chờ duyệt",
    failed: "⚠️ Lỗi",
    rejected: "🚫 Từ chối",
    pending: "⏳ Đang chờ",
    processing: "🔄 Đang xử lý",
    extracted: "🔄 Đã trích",
    enriching: "🔄 Đang phân tích",
  };
  return m[status] ?? status;
}

// ─── Types ───────────────────────────────────────────────────────────────────────────

interface CalendarPickerProps {
  templates: Template[];
  onRefreshJobs: () => void;
}

const WEEKDAYS_VI = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];

// ─── Component ────────────────────────────────────────────────────────────────

export function CalendarPicker({ templates, onRefreshJobs }: CalendarPickerProps) {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);

  const [days, setDays] = useState<CalendarDay[]>([]);
  const [loadingDays, setLoadingDays] = useState(false);

  const [selectedDay, setSelectedDay] = useState<CalendarDay | null>(null);
  const [selectedJobIds, setSelectedJobIds] = useState<Set<string>>(new Set());

  // Create report form
  const [selTplId, setSelTplId] = useState<string>("");
  const [reportName, setReportName] = useState(
    `Báo cáo ${new Date().toLocaleDateString("vi-VN")}`
  );
  const [creating, setCreating] = useState(false);

  // ── Load month ──────────────────────────────────────────────────────────────

  const loadMonth = useCallback(async () => {
    setLoadingDays(true);
    const res = await api.jobs.byDate(month, year);
    setLoadingDays(false);
    if (res.ok) {
      setDays(res.data as CalendarDay[]);
    } else {
      toast.error(`Lỗi tải lịch: ${res.error}`);
    }
  }, [month, year]);

  useEffect(() => { loadMonth(); }, [loadMonth]);

  // Reset selection when month changes
  useEffect(() => { setSelectedDay(null); setSelectedJobIds(new Set()); }, [month, year]);

  // ── Calendar grid helpers ───────────────────────────────────────────────────

  const numDays = new Date(year, month, 0).getDate();
  const firstDow = (() => {
    // Convert JS getDay() (0=Sun) to Mon-based (0=Mon)
    const js = new Date(year, month - 1, 1).getDay();
    return js === 0 ? 6 : js - 1;
  })();

  const cells: (CalendarDay | null)[] = [
    ...Array(firstDow).fill(null),
    ...days,
    // fill remaining to complete last row
  ];
  const rows: (CalendarDay | null)[][] = [];
  for (let i = 0; i < cells.length; i += 7) {
    rows.push(cells.slice(i, i + 7));
  }
  // pad last row to 7
  const lastRow = rows[rows.length - 1];
  while (lastRow.length < 7) lastRow.push(null);

  // ── Job toggling ────────────────────────────────────────────────────────────

  function toggleJob(id: string) {
    setSelectedJobIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  function selectAll() {
    if (!selectedDay) return;
    setSelectedJobIds(new Set(selectedDay.jobs.map((j) => j.id)));
  }

  function deselectAll() {
    setSelectedJobIds(new Set());
  }

  // ── Create report ──────────────────────────────────────────────────────────

  async function handleCreateReport() {
    if (!selTplId || selectedJobIds.size === 0) {
      toast.warning("Chọn mẫu báo cáo và ít nhất 1 hồ sơ.");
      return;
    }
    setCreating(true);
    const res = await api.reports.create({
      template_id: selTplId,
      job_ids: Array.from(selectedJobIds),
      report_name: reportName.trim() || `Báo cáo ${new Date().toLocaleDateString("vi-VN")}`,
    });
    setCreating(false);
    if (res.ok) {
      toast.success(`✅ Đã tạo báo cáo "${(res.data as { name?: string }).name}"!`);
      setSelectedJobIds(new Set());
      onRefreshJobs();
    } else {
      toast.error(`Tổng hợp thất bại: ${res.error}`);
    }
  }

  // ── Month navigation ────────────────────────────────────────────────────────

  function prevMonth() {
    if (month === 1) { setMonth(12); setYear((y) => y - 1); }
    else setMonth((m) => m - 1);
  }

  function nextMonth() {
    if (month === 12) { setMonth(1); setYear((y) => y + 1); }
    else setMonth((m) => m + 1);
  }

  function goToday() {
    setMonth(now.getMonth() + 1);
    setYear(now.getFullYear());
  }

  const tplMap: Record<string, string> = {};
  templates.forEach((t) => { tplMap[t.id] = t.name; });

  const selectedJobs = selectedDay?.jobs ?? [];
  const tplsInSelected = Array.from(
    new Set(selectedJobs.map((j) => j.template_id).filter(Boolean))
  ) as string[];

  const canCreate = selTplId && selectedJobIds.size > 0 && !creating;

  return (
    <div className="space-y-4">
      {/* ── Legend ─────────────────────────────────────────────────────────── */}
      <div className="flex gap-4 flex-wrap text-xs text-muted-foreground">
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-3 rounded bg-green-100 dark:bg-green-900/40 border border-green-300 dark:border-green-700" />
          ✅ Hoàn thành
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-3 rounded bg-yellow-100 dark:bg-yellow-900/40 border border-yellow-300 dark:border-yellow-700" />
          🟡 Có hồ sơ chờ
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-3 rounded bg-red-100 dark:bg-red-900/40 border border-red-300 dark:border-red-700" />
          🔴 Có vấn đề
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-3 rounded bg-muted/30 border border-transparent" />
          ⬜ Trống
        </span>
      </div>

      {/* ── Main layout: calendar + panel ─────────────────────────────────── */}
      <div className="flex gap-4 flex-col lg:flex-row">
        {/* ── Calendar grid ─────────────────────────────────────────────── */}
        <div className="flex-1 min-w-0">
          {/* Month header */}
          <div className="flex items-center justify-between mb-2">
            <Button variant="ghost" size="icon" onClick={prevMonth}>
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <div className="flex items-center gap-2">
              <span className="font-semibold text-base">
                {getMonthName(month, year)}
              </span>
              <Button variant="outline" size="sm" onClick={goToday} className="text-xs px-2 py-1 h-7">
                Hôm nay
              </Button>
            </div>
            <Button variant="ghost" size="icon" onClick={nextMonth}>
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>

          {/* Weekday headers */}
          <div className="grid grid-cols-7 mb-1">
            {WEEKDAYS_VI.map((d) => (
              <div key={d} className="text-center text-xs font-medium text-muted-foreground py-1">
                {d}
              </div>
            ))}
          </div>

          {/* Day cells */}
          {loadingDays ? (
            <div className="grid grid-cols-7 gap-1">
              {Array.from({ length: 35 }).map((_, i) => (
                <div key={i} className="h-12 rounded-md bg-muted animate-pulse" />
              ))}
            </div>
          ) : (
            <div className="grid grid-cols-7 gap-1">
              {rows.flat().map((day, i) => {
                if (!day) {
                  return <div key={`empty-${i}`} className="h-12 rounded-md" />;
                }
                const s = dayStatus(day);
                const isSelected = selectedDay?.date === day.date;
                const dayNum = parseInt(day.date.split("-")[2], 10);
                return (
                  <button
                    key={day.date}
                    onClick={() => setSelectedDay(day)}
                    title={`${day.job_count} hồ sơ · ${day.approved_count} duyệt${day.has_issues ? " · ⚠️" : ""}`}
                    className={`
                      h-12 rounded-md flex flex-col items-center justify-center
                      transition-all cursor-pointer select-none
                      hover:shadow-md hover:scale-105
                      ${dayBgClass(s)}
                      ${dayBorderClass(s, isSelected)}
                    `}
                  >
                    <span className={`text-sm font-medium ${s !== "empty" ? "text-foreground" : "text-muted-foreground"}`}>
                      {dayNum}
                    </span>
                    {day.job_count > 0 && (
                      <span className="text-[10px] leading-none text-muted-foreground">
                        {day.job_count}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* ── Job list panel ──────────────────────────────────────────────── */}
        <div className="w-full lg:w-80 shrink-0 space-y-3">
          {selectedDay ? (
            <>
              <div className="flex items-center justify-between">
                <h3 className="font-semibold text-sm">
                  📋 {selectedDay.date} — {selectedDay.jobs.length} hồ sơ
                </h3>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => { setSelectedDay(null); setSelectedJobIds(new Set()); }}
                  className="text-xs h-7 px-2"
                >
                  ✕
                </Button>
              </div>

              {/* Select all / deselect */}
              {selectedDay.jobs.length > 0 && (
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" onClick={selectAll} className="text-xs h-7 flex-1">
                    ☑️ Chọn tất cả
                  </Button>
                  <Button variant="outline" size="sm" onClick={deselectAll} className="text-xs h-7 flex-1">
                    ⬜ Bỏ chọn
                  </Button>
                </div>
              )}

              {/* Job list */}
              {selectedDay.jobs.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-6">
                  Không có hồ sơ nào trong ngày này.
                </p>
              ) : (
                <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
                  {selectedDay.jobs.map((job) => (
                    <div
                      key={job.id}
                      className="flex items-start gap-2 rounded-md border p-2 hover:bg-accent/50 transition-colors cursor-pointer"
                      onClick={() => toggleJob(job.id)}
                    >
                      <Checkbox
                        checked={selectedJobIds.has(job.id)}
                        onCheckedChange={() => toggleJob(job.id)}
                        onClick={(e) => e.stopPropagation()}
                        className="mt-0.5 shrink-0"
                      />
                      <div className="min-w-0 flex-1">
                        <div className="text-sm font-medium truncate">{job.file_name}</div>
                        <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
                          <Badge variant={jobBadgeVariant(job.status)} className="text-[10px] px-1 py-0">
                            {jobStatusLabel(job.status)}
                          </Badge>
                          {tplMap[job.template_id] && (
                            <span className="text-[10px] text-muted-foreground truncate">
                              {tplMap[job.template_id]}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : (
            <div className="h-full flex flex-col items-center justify-center text-muted-foreground text-sm border rounded-md p-6 min-h-48">
              <span className="text-2xl mb-2">📅</span>
              <p className="text-center">Click vào ngày để xem hồ sơ</p>
            </div>
          )}
        </div>
      </div>

      {/* ── Action bar: create report ─────────────────────────────────────── */}
      <Separator />

      <div className="space-y-3">
        <h3 className="font-semibold text-base flex items-center gap-2">
          <BarChart3 className="h-4 w-4" />
          Tạo báo cáo từ lịch
        </h3>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label>Template</Label>
            <Select value={selTplId} onValueChange={setSelTplId}>
              <SelectTrigger className="mt-1.5">
                <SelectValue placeholder="Chọn mẫu báo cáo…" />
              </SelectTrigger>
              <SelectContent>
                {tplsInSelected.length > 0 ? (
                  tplsInSelected.map((tid) => (
                    <SelectItem key={tid} value={tid}>
                      {tplMap[tid] ?? tid.slice(0, 8)}
                    </SelectItem>
                  ))
                ) : templates.length > 0 ? (
                  templates.map((t) => (
                    <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>
                  ))
                ) : (
                  <SelectItem value="__none__" disabled>Chưa có template</SelectItem>
                )}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Tên báo cáo</Label>
            <Input
              value={reportName}
              onChange={(e) => setReportName(e.target.value)}
              className="mt-1.5"
            />
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <div className="flex-1 min-w-0">
            <p className="text-sm text-muted-foreground">
              {selectedJobIds.size === 0
                ? "Chọn ngày và hồ sơ bên trên để tạo báo cáo."
                : `Đã chọn ${selectedJobIds.size} hồ sơ`}
            </p>
          </div>
          <Button
            onClick={handleCreateReport}
            disabled={!canCreate}
          >
            <BarChart3 className="h-4 w-4 mr-2" />
            {creating ? "Đang tổng hợp…" : `📊 Tạo báo cáo (${selectedJobIds.size})`}
          </Button>
        </div>
      </div>
    </div>
  );
}
