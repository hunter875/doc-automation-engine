"use client";

import { useCallback, useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, RefreshCw, FileJson, AlertTriangle, Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useAuth } from "@/components/providers";
import { api } from "@/lib/api";
import type { DailyReportCalendarDay, DailyReportDetail, DailyReportDiffChange, Template } from "@/lib/types";
import { toast } from "sonner";
import { CalendarGrid } from "@/components/extraction/calendar-grid";

type SourceTab = "default" | "auto" | "manual";

function getMonthName(month: number, year?: number): string {
  const months = [
    "Tháng 1", "Tháng 2", "Tháng 3", "Tháng 4", "Tháng 5", "Tháng 6",
    "Tháng 7", "Tháng 8", "Tháng 9", "Tháng 10", "Tháng 11", "Tháng 12",
  ];
  return year ? `${months[month - 1]} ${year}` : months[month - 1];
}

function extractSheetId(input: string): string | null {
  if (!input.trim()) return null;
  const match = input.match(/\/d\/([a-zA-Z0-9-_]+)/);
  if (match) return match[1];
  if (/^[a-zA-Z0-9-_]+$/.test(input.trim())) return input.trim();
  return null;
}

function extractSheetGid(input: string): string | null {
  if (!input.trim()) return null;
  // Match gid in URL: ...?gid=123456789 or #gid=123456789
  const match = input.match(/[?&#]gid=([0-9]+)/);
  return match ? match[1] : null;
}

export default function DailyReportsPage() {
  const { isLoggedIn, tenantId } = useAuth();
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);

  // Templates
  const [templates, setTemplates] = useState<Template[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>("");

  // Sync panel
  const [sheetUrl, setSheetUrl] = useState("https://docs.google.com/spreadsheets/d/1vfWhL4ZFRiwlrhjEAlCemE9sPlNHvuxFiT_1hA5NDYI/edit?usp=sharing");
  const [syncing, setSyncing] = useState(false);
  const [syncProgress, setSyncProgress] = useState("");

  // Calendar
  const [allDays, setAllDays] = useState<DailyReportCalendarDay[]>([]);
  const [loadingCalendar, setLoadingCalendar] = useState(false);
  const [calendarError, setCalendarError] = useState("");

  // Detail
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [detail, setDetail] = useState<DailyReportDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [detailError, setDetailError] = useState("");

  // Edit
  const [editJson, setEditJson] = useState("");
  const [editReason, setEditReason] = useState("");
  const [saving, setSaving] = useState(false);

  // Diff
  const [diff, setDiff] = useState<DailyReportDiffChange[]>([]);
  const [loadingDiff, setLoadingDiff] = useState(false);

  // Source tab
  const [sourceTab, setSourceTab] = useState<SourceTab>("default");

  // Load templates on mount
  useEffect(() => {
    if (!tenantId) return;
    api.templates
      .list(1, 100)
      .then((res) => {
        if (res.ok && res.data?.items) {
          setTemplates(res.data.items);
          const active = res.data.items.find((t: Template) => t.is_active);
          if (active) setSelectedTemplateId(active.id);
        }
      })
      .catch((err) => {
        console.error("Failed to load templates:", err);
        toast.error("Không thể tải danh sách mẫu báo cáo");
      });
  }, [tenantId]);

  // Load calendar (all tenant days, metadata only)
  const loadCalendar = useCallback(async () => {
    if (!tenantId) return;
    setLoadingCalendar(true);
    setCalendarError("");
    const res = await api.dailyReports.getCalendar();
    setLoadingCalendar(false);
    if (res.ok) {
      const payload = res.data as { days?: DailyReportCalendarDay[] };
      setAllDays(payload.days || []);
    } else {
      setCalendarError(res.error || "Lỗi tải lịch");
      setAllDays([]);
    }
  }, [tenantId]);

  // Load detail for selected date
  const loadDetail = useCallback(
    async (date: string, source: SourceTab = "default", tmplId: string = selectedTemplateId) => {
      if (!tenantId || !tmplId) return;
      setLoadingDetail(true);
      setDetailError("");
      setDetail(null);
      setDiff([]);
      const res = await api.dailyReports.getDetail({ date, templateId: tmplId, source });
      setLoadingDetail(false);
      if (res.ok) {
        setDetail(res.data as DailyReportDetail);
        if (res.data?.data) {
          setEditJson(JSON.stringify(res.data.data, null, 2));
        }
      } else {
        if (source !== "manual" && res.error?.includes("404")) {
          setDetail(null);
        } else {
          setDetailError(res.error || "Lỗi tải chi tiết");
        }
      }
    },
    [tenantId, selectedTemplateId]
  );

  // Sync Google Sheet
  async function handleSync() {
    const sheetId = extractSheetId(sheetUrl);
    if (!sheetId) {
      toast.error("URL Google Sheet không hợp lệ");
      return;
    }
    if (!selectedTemplateId) {
      toast.error("Vui lòng chọn template");
      return;
    }

    setSyncing(true);
    setSyncProgress("Đang gửi yêu cầu...");

    const sheetGid = extractSheetGid(sheetUrl);
    const payload: any = {
      template_id: selectedTemplateId,
      sheet_id: sheetId,
      mode: "kv30",
    };
    if (sheetGid) {
      payload.worksheet_gid = sheetGid;
    }

    const res = await api.jobs.ingestGoogleSheet(payload);

    if (!res.ok) {
      setSyncing(false);
      setSyncProgress("");
      toast.error(`Đồng bộ thất bại: ${res.error}`);
      return;
    }

    const taskId = (res.data as { task_id?: string }).task_id;
    if (!taskId) {
      setSyncing(false);
      setSyncProgress("Hoàn tất");
      toast.success("Đồng bộ xong");
      loadCalendar();
      return;
    }

    // Poll ingestion status
    setSyncProgress("Đang xử lý...");
    const maxAttempts = 120;
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      await new Promise((resolve) => setTimeout(resolve, 2000));
      const statusRes = await api.jobs.getIngestionStatus(taskId);
      if (!statusRes.ok) {
        setSyncProgress("Lỗi đọc trạng thái");
        setSyncing(false);
        return;
      }

      const payload = statusRes.data as any;
      const status = payload.status;
      const state = payload.state;

      if (status === "completed" && payload.summary) {
        const summary = payload.summary;
        // Check inner status: if ingestion failed, show error instead of counters
        if (summary.status === "error") {
          const errorMsg = summary.error || "Lỗi xử lý sheet";
          const resolverDebug = summary.resolver_debug;

          let detailedMsg = errorMsg;
          if (resolverDebug) {
            const preferred = resolverDebug.preferred_worksheet;
            const available = resolverDebug.available_worksheets || [];
            const checked = resolverDebug.candidates_checked || [];

            detailedMsg += `\n\nTab config: ${preferred}`;
            if (available.length > 0) {
              detailedMsg += `\nTab có sẵn: ${available.join(", ")}`;
            }
            if (checked.length > 0) {
              const topCandidates = checked.slice(0, 3).map((c: any) =>
                `${c.name} (${c.valid_daily_rows} dòng hợp lệ)`
              ).join(", ");
              detailedMsg += `\nĐã kiểm tra: ${topCandidates}`;
            }
          }

          setSyncProgress(`Lỗi: ${errorMsg}`);
          toast.error(`❌ Đồng bộ thất bại: ${detailedMsg}`, { duration: 10000 });
          setSyncing(false);
          return;
        }
        // Success: show counters
        const created = Number(summary.dates_created || 0);
        const duplicate = Number(summary.dates_duplicate || 0);
        const skipped = Number(summary.dates_skipped_no_data || 0);
        const failed = Number(summary.rows_failed || 0);
        setSyncProgress(`Hoàn tất: ${created} ngày mới, ${duplicate} trùng, ${skipped} bỏ qua, ${failed} lỗi`);
        toast.success(`✅ Đồng bộ xong: ${created} ngày mới`);
        setSyncing(false);
        loadCalendar();
        return;
      }

      if (status === "failed") {
        toast.error(`Đồng bộ thất bại: ${payload.error || "Unknown error"}`);
        setSyncProgress("Thất bại");
        setSyncing(false);
        return;
      }

      if (status === "running" || state === "STARTED") {
        setSyncProgress(`Đang xử lý... (${state})`);
      } else if (status === "queued") {
        setSyncProgress(`Đang chờ... (${state})`);
      }
    }
    toast.warning("Đồng bộ vẫn đang chạy, vui lòng kiểm tra lại sau.");
    setSyncProgress("Đang chạy nền…");
    setSyncing(false);
  }

  // When selectedDate changes, load default detail
  useEffect(() => {
    if (selectedDate && selectedTemplateId) {
      setSourceTab("default");
      loadDetail(selectedDate, "default", selectedTemplateId);
    }
  }, [selectedDate, selectedTemplateId, loadDetail]);

  // When sourceTab changes, reload detail
  useEffect(() => {
    if (selectedDate && selectedTemplateId) {
      loadDetail(selectedDate, sourceTab, selectedTemplateId);
    }
  }, [sourceTab, selectedDate, selectedTemplateId, loadDetail]);

  // Initial calendar load
  useEffect(() => {
    loadCalendar();
  }, [loadCalendar]);

  // Reset selections when month/year changes
  useEffect(() => {
    setSelectedDate(null);
    setDetail(null);
    setSourceTab("default");
  }, [month, year]);

  // Month navigation
  function prevMonth() {
    if (month === 1) {
      setMonth(12);
      setYear((y) => y - 1);
    } else {
      setMonth((m) => m - 1);
    }
  }

  function nextMonth() {
    if (month === 12) {
      setMonth(1);
      setYear((y) => y + 1);
    } else {
      setMonth((m) => m + 1);
    }
  }

  function goToday() {
    setMonth(now.getMonth() + 1);
    setYear(now.getFullYear());
  }

  // Filter days for selected month
  const monthFilteredDays = allDays.filter((d) => {
    const dMonth = parseInt(d.date.slice(5, 7), 10);
    const dYear = parseInt(d.date.slice(0, 4), 10);
    return dMonth === month && dYear === year;
  });

  // Render calendar cell
  function renderDay(day: DailyReportCalendarDay, dayNum: number, isSelected: boolean) {
    const statusBadge = () => {
      if (day.is_finalized) {
        return <Badge variant="secondary" className="text-[8px] px-1">🔒</Badge>;
      }
      if (day.review_status === "approved") {
        return <Badge variant="success" className="text-[8px] px-1">✅</Badge>;
      }
      if (day.review_status === "rejected") {
        return <Badge variant="destructive" className="text-[8px] px-1">🚫</Badge>;
      }
      if (day.has_conflict) {
        return <Badge variant="warning" className="text-[8px] px-1">⚠️</Badge>;
      }
      if (day.has_manual_edits) {
        return <Badge variant="outline" className="text-[8px] px-1">✏️</Badge>;
      }
      return null;
    };

    return (
      <div className="flex flex-col items-center justify-center h-full">
        <span className="text-sm font-medium">{dayNum}</span>
        {statusBadge()}
      </div>
    );
  }

  function getCellClassName(day: DailyReportCalendarDay, isSelected: boolean) {
    let base = "border ";
    if (isSelected) {
      base += "bg-primary text-primary-foreground border-primary ";
    } else if (day.is_finalized) {
      base += "bg-secondary/20 border-secondary ";
    } else if (day.review_status === "approved") {
      base += "bg-green-50 dark:bg-green-950/20 border-green-200 dark:border-green-800 ";
    } else if (day.has_conflict) {
      base += "bg-yellow-50 dark:bg-yellow-950/20 border-yellow-200 dark:border-yellow-800 ";
    } else if (day.has_manual_edits) {
      base += "bg-blue-50 dark:bg-blue-950/20 border-blue-200 dark:border-blue-800 ";
    } else {
      base += "bg-muted/30 border-muted ";
    }
    return base;
  }

  function getCellTitle(day: DailyReportCalendarDay) {
    const parts = [day.date];
    if (day.review_status) parts.push(`Status: ${day.review_status}`);
    if (day.has_manual_edits) parts.push("Có chỉnh sửa thủ công");
    if (day.is_finalized) parts.push("Đã finalize");
    if (day.has_conflict) parts.push("Có xung đột");
    return parts.join(" | ");
  }

  async function handleSaveEdit() {
    if (!selectedDate || !selectedTemplateId) return;
    let parsed;
    try {
      parsed = JSON.parse(editJson);
    } catch (e) {
      toast.error("JSON không hợp lệ");
      return;
    }

    setSaving(true);
    const res = await api.dailyReports.saveEdit({
      date: selectedDate,
      templateId: selectedTemplateId,
      data: parsed,
      reason: editReason || undefined,
    });
    setSaving(false);

    if (res.ok) {
      toast.success("Đã lưu chỉnh sửa");
      setEditReason("");
      loadDetail(selectedDate, "default", selectedTemplateId);
      loadCalendar();
    } else {
      toast.error(`Lưu thất bại: ${res.error}`);
    }
  }

  async function handleApprove(source: "auto" | "manual") {
    if (!selectedDate || !selectedTemplateId) return;
    if (!window.confirm(`Approve ${source} version?`)) return;

    const res = await api.dailyReports.approve({
      date: selectedDate,
      templateId: selectedTemplateId,
      source,
      manualEditId: detail?.manual_edit_id,
      reason: undefined,
    });

    if (res.ok) {
      toast.success("Đã approve");
      loadDetail(selectedDate, "default", selectedTemplateId);
      loadCalendar();
    } else {
      toast.error(`Approve thất bại: ${res.error}`);
    }
  }

  async function handleReject() {
    if (!selectedDate || !selectedTemplateId || !detail?.manual_edit_id) return;
    if (!window.confirm("Reject manual edit?")) return;

    const res = await api.dailyReports.reject({
      date: selectedDate,
      templateId: selectedTemplateId,
      manualEditId: detail.manual_edit_id,
      reason: undefined,
    });

    if (res.ok) {
      toast.success("Đã reject");
      loadDetail(selectedDate, "default", selectedTemplateId);
      loadCalendar();
    } else {
      toast.error(`Reject thất bại: ${res.error}`);
    }
  }

  async function handleFinalize(source: "auto" | "manual") {
    if (!selectedDate || !selectedTemplateId) return;
    if (!window.confirm(`Finalize ${source} version? Không thể sửa sau khi finalize.`)) return;

    const res = await api.dailyReports.finalize({
      date: selectedDate,
      templateId: selectedTemplateId,
      source,
      manualEditId: detail?.manual_edit_id,
      reason: undefined,
    });

    if (res.ok) {
      toast.success("Đã finalize");
      loadDetail(selectedDate, "default", selectedTemplateId);
      loadCalendar();
    } else {
      toast.error(`Finalize thất bại: ${res.error}`);
    }
  }

  async function handleLoadDiff() {
    if (!selectedDate || !selectedTemplateId) return;
    setLoadingDiff(true);
    const res = await api.dailyReports.getDiff({ date: selectedDate, templateId: selectedTemplateId });
    setLoadingDiff(false);
    if (res.ok) {
      const payload = res.data as { changes?: DailyReportDiffChange[] };
      setDiff(payload.changes || []);
    } else {
      toast.error(`Lỗi tải diff: ${res.error}`);
    }
  }

  function renderDetailPanel() {
    if (!selectedDate) {
      return <p className="text-sm text-muted-foreground">Chọn một ngày trên lịch để xem chi tiết.</p>;
    }

    if (loadingDetail) {
      return <Skeleton className="h-32 w-full" />;
    }

    if (detailError) {
      return (
        <Alert variant="destructive">
          <AlertDescription>{detailError}</AlertDescription>
        </Alert>
      );
    }

    if (!detail) {
      return <p className="text-sm text-muted-foreground">Không có dữ liệu cho ngày này.</p>;
    }

    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="space-y-1">
            <p className="text-sm font-medium">Ngày: {selectedDate}</p>
            <p className="text-xs text-muted-foreground">
              Source: {detail.source} | Status: {detail.review_status || "N/A"}
            </p>
            {detail.is_finalized && <Badge variant="secondary">🔒 Finalized</Badge>}
            {detail.has_manual_edits && <Badge variant="outline">✏️ Có chỉnh sửa</Badge>}
          </div>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={() => setSourceTab("default")}>
              Default
            </Button>
            <Button size="sm" variant="outline" onClick={() => setSourceTab("auto")}>
              Auto
            </Button>
            <Button size="sm" variant="outline" onClick={() => setSourceTab("manual")}>
              Manual
            </Button>
          </div>
        </div>

        <div className="space-y-2">
          <Label>Dữ liệu (JSON)</Label>
          <Textarea
            value={editJson}
            onChange={(e) => setEditJson(e.target.value)}
            rows={12}
            className="font-mono text-xs"
            disabled={detail.is_finalized}
          />
        </div>

        {!detail.is_finalized && (
          <div className="space-y-2">
            <Label>Lý do chỉnh sửa (optional)</Label>
            <Input
              value={editReason}
              onChange={(e) => setEditReason(e.target.value)}
              placeholder="Ghi chú..."
            />
            <Button onClick={handleSaveEdit} disabled={saving}>
              {saving ? "Đang lưu..." : "Lưu chỉnh sửa"}
            </Button>
          </div>
        )}

        {detail.has_manual_edits && (
          <div className="flex gap-2 flex-wrap">
            <Button size="sm" variant="outline" onClick={handleLoadDiff} disabled={loadingDiff}>
              {loadingDiff ? "Đang tải..." : "Xem Diff"}
            </Button>
            {!detail.is_finalized && (
              <>
                <Button size="sm" onClick={() => handleApprove("auto")}>
                  Approve Auto
                </Button>
                <Button size="sm" onClick={() => handleApprove("manual")}>
                  Approve Manual
                </Button>
                <Button size="sm" variant="destructive" onClick={handleReject}>
                  Reject Manual
                </Button>
                <Button size="sm" onClick={() => handleFinalize("auto")}>
                  Finalize Auto
                </Button>
                <Button size="sm" onClick={() => handleFinalize("manual")}>
                  Finalize Manual
                </Button>
              </>
            )}
          </div>
        )}

        {diff.length > 0 && (
          <div className="space-y-2">
            <p className="text-sm font-medium">Diff (Auto vs Manual):</p>
            <div className="border rounded-md p-3 space-y-2 max-h-60 overflow-auto">
              {diff.map((change, i) => (
                <div key={i} className="text-xs space-y-1">
                  <p className="font-mono font-semibold">{change.path}</p>
                  <p>
                    <span className="text-red-600">Auto: {JSON.stringify(change.auto_value)}</span>
                    {" → "}
                    <span className="text-green-600">Manual: {JSON.stringify(change.review_value)}</span>
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  }

  if (!isLoggedIn || !tenantId) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold">📅 Báo cáo ngày</h1>
        <Alert variant="warning">
          <AlertDescription>Vui lòng đăng nhập và chọn tổ chức.</AlertDescription>
        </Alert>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">📅 Báo cáo ngày</h1>

      {/* Sync Panel */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">🔄 Đồng bộ báo cáo ngày từ Google Sheet KV30</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="sheet-url">Google Sheet URL</Label>
            <Input
              id="sheet-url"
              value={sheetUrl}
              onChange={(e) => setSheetUrl(e.target.value)}
              placeholder="https://docs.google.com/spreadsheets/d/..."
              disabled={syncing}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="template-select">Template</Label>
            {templates.length === 0 ? (
              <Alert variant="warning">
                <AlertDescription>
                  Chưa có template. Tạo template trước khi đồng bộ.
                </AlertDescription>
              </Alert>
            ) : (
              <Select value={selectedTemplateId} onValueChange={setSelectedTemplateId} disabled={syncing}>
                <SelectTrigger id="template-select">
                  <SelectValue placeholder="Chọn template" />
                </SelectTrigger>
                <SelectContent>
                  {templates.map((t) => (
                    <SelectItem key={t.id} value={t.id}>
                      {t.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>

          <Button onClick={handleSync} disabled={syncing || templates.length === 0}>
            {syncing ? "Đang đồng bộ..." : "Đồng bộ Google Sheet"}
          </Button>

          {syncProgress && (
            <Alert>
              <AlertDescription>{syncProgress}</AlertDescription>
            </Alert>
          )}
        </CardContent>
      </Card>

      {/* Calendar + Detail */}
      <div className="flex flex-col lg:flex-row gap-4">
        <div className="flex-1">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-base">Lịch báo cáo</CardTitle>
              <Button size="sm" variant="ghost" onClick={loadCalendar} disabled={loadingCalendar}>
                <RefreshCw className={`h-4 w-4 ${loadingCalendar ? "animate-spin" : ""}`} />
              </Button>
            </CardHeader>
            <CardContent>
              {calendarError && (
                <Alert variant="destructive" className="mb-4">
                  <AlertDescription>{calendarError}</AlertDescription>
                </Alert>
              )}
              {loadingCalendar ? (
                <Skeleton className="h-64 w-full" />
              ) : (
                <CalendarGrid
                  month={month}
                  year={year}
                  days={monthFilteredDays}
                  renderDay={renderDay}
                  selectedDay={selectedDate}
                  onSelectDay={setSelectedDate}
                  onPrevMonth={prevMonth}
                  onNextMonth={nextMonth}
                  onGoToday={goToday}
                  getCellClassName={getCellClassName}
                  getCellTitle={getCellTitle}
                />
              )}
            </CardContent>
          </Card>
        </div>

        <div className="w-full lg:w-96 shrink-0">
          <Card className="h-full min-h-96">
            <CardHeader>
              <CardTitle className="text-base">Chi tiết báo cáo</CardTitle>
            </CardHeader>
            <CardContent>{renderDetailPanel()}</CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
