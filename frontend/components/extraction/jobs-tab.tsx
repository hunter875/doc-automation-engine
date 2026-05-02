
"use client";

import { useState, useRef } from "react";
import { RefreshCw, Upload, RotateCcw, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { TableSkeleton } from "@/components/ui/table-skeleton";
import { VirtualTable } from "@/components/ui/virtual-table";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import type { Template, ExtractionJob } from "@/lib/types";
import { toast } from "sonner";
import { STATUS_VI, statusBadgeVariant } from "@/lib/constants";

interface JobsTabProps {
  templates: Template[];
  jobs: ExtractionJob[];
  onRefreshJobs: () => void;
  loadingJobs: boolean;
}

type StatusFilter = "all" | "processing" | "ready_for_review" | "approved" | "failed";

// Helper function outside component to avoid parser issues
async function waitForIngestionTask(
  taskId: string,
  setSheetProgress: (v: string) => void,
  onRefreshJobs: () => void
): Promise<void> {
  const maxAttempts = 120;
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 2000));
    const statusRes = await api.jobs.getIngestionStatus(taskId);
    if (!statusRes.ok) {
      setSheetProgress("Lỗi đọc trạng thái ingestion");
      return;
    }

    const payload = statusRes.data;
    const status = payload.status;
    const state = payload.state;

    // Check for completion
    if (status === "completed" && payload.summary) {
      const summary = payload.summary;
      const inserted = Number(summary.rows_inserted || 0);
      const failed = Number(summary.rows_failed || 0);
      const processed = Number(summary.rows_processed || 0);

      if (failed > 0) {
        toast.warning(`Đồng bộ hoàn tất có lỗi: ${inserted} thành công, ${failed} lỗi.`);
      } else {
        toast.success(`✅ Đồng bộ xong: ${inserted} bản ghi.`);
      }
      setSheetProgress(`Hoàn tất: ${inserted} bản ghi (${processed} rows fetched)`);
      onRefreshJobs();
      return;
    }

    if (status === "failed") {
      toast.error(`Đồng bộ thất bại: ${payload.error || "Unknown error"}`);
      setSheetProgress("Thất bại");
      return;
    }

    // Running/queued - show intermediate state
    if (status === "running" || state === "STARTED") {
      setSheetProgress(`Đang xử lý... (${state})`);
    } else if (status === "queued") {
      setSheetProgress(`Đang chờ... (${state})`);
    }
  }
  toast.warning("Đồng bộ vẫn đang chạy, vui lòng kiểm tra lại sau.");
  setSheetProgress("Đang chạy nền…");
}

export function JobsTab({ templates, jobs, onRefreshJobs, loadingJobs }: JobsTabProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [overrideTplId, setOverrideTplId] = useState<string>("__auto");
  const [uploading, setUploading] = useState(false);

  // Google Sheets ingestion from template config
  const [sheetIngesting, setSheetIngesting] = useState(false);
  const [sheetProgress, setSheetProgress] = useState<string>("");

  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [tplFilter, setTplFilter] = useState<string>("__all");

  const [retrying, setRetrying] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const tplMap: Record<string, string> = {};
  templates.forEach((t) => { tplMap[t.id] = t.name; });

  async function handleUpload() {
    if (selectedFiles.length === 0) { toast.warning("Chọn ít nhất 1 file PDF."); return; }
    const fd = new FormData();
    selectedFiles.forEach((f) => fd.append("files", f));
    if (overrideTplId !== "__auto") fd.append("template_id", overrideTplId);
    setUploading(true);
    const res = await api.jobs.smartUpload(fd);
    setUploading(false);
    if (res.ok) {
      type SmartUploadJob = { status?: string; file_name?: string };
      const payload = res.data as { jobs?: SmartUploadJob[] };
      const jobList: SmartUploadJob[] = Array.isArray(payload.jobs) ? payload.jobs : [];
      const errors = jobList.filter((j) => j.status?.includes("error"));
      const ok = jobList.length - errors.length;
      if (ok > 0) toast.success(`✅ ${ok} file đã gửi — AI đang xử lý.`);
      errors.forEach((j) => toast.warning(`⚠️ ${j.file_name}: ${j.status}`));
      setSelectedFiles([]);
      if (fileInputRef.current) fileInputRef.current.value = "";
      onRefreshJobs();
    } else {
      toast.error(`Gửi thất bại: ${res.error}`);
    }
  }

  async function handleRetry(jobId: string) {
    setRetrying(true);
    const res = await api.jobs.retry(jobId);
    setRetrying(false);
    if (res.ok) {
      toast.success("Đã đưa lại vào hàng xử lý.");
      onRefreshJobs();
    } else {
      toast.error(`Retry thất bại: ${res.error}`);
    }
  }

  async function handleDelete(jobId: string) {
    if (!confirm("Xoá hồ sơ này?")) return;
    setDeletingId(jobId);
    const res = await api.jobs.delete(jobId);
    setDeletingId(null);
    if (res.ok) {
      onRefreshJobs();
    } else {
      toast.error(`Xoá thất bại: ${res.error}`);
    }
  }

  // Filter jobs
  const PROCESSING_STATUSES = new Set(["pending", "processing", "extracted", "enriching"]);
  const filtered = jobs.filter((j) => {
    if (statusFilter === "processing" && !PROCESSING_STATUSES.has(j.status)) return false;
    if (statusFilter === "ready_for_review" && j.status !== "ready_for_review") return false;
    if (statusFilter === "approved" && !["approved", "aggregated"].includes(j.status)) return false;
    if (statusFilter === "failed" && !["failed", "rejected"].includes(j.status)) return false;
    if (tplFilter !== "__all" && j.template_id !== tplFilter) return false;
    return true;
  });

  // Stats
  const sc: Record<string, number> = {};
  jobs.forEach((j) => { sc[j.status] = (sc[j.status] ?? 0) + 1; });
  const processing = (sc.processing ?? 0) + (sc.pending ?? 0) + (sc.enriching ?? 0) + (sc.extracted ?? 0);

  async function handleSheetIngestionFromTemplate(templateId: string) {
    const selectedTpl = templates.find(t => t.id === templateId);
    if (!selectedTpl) return;

    if (!selectedTpl.google_sheet_id) {
      toast.warning("Template chưa được cấu hình Google Sheets (thiếu Sheet ID).");
      return;
    }

    // Check for multi-config or legacy single config
    const hasConfigs = selectedTpl.google_sheet_configs && selectedTpl.google_sheet_configs.length > 0;
    const hasLegacy = selectedTpl.google_sheet_worksheet && selectedTpl.google_sheet_schema_path;

    if (!hasConfigs && !hasLegacy) {
      toast.warning("Template chưa được cấu hình Google Sheets (thiếu worksheet hoặc schema path).");
      return;
    }

    setSheetIngesting(true);
    setSheetProgress("Đang đưa vào hàng đợi…");

    const payload: any = { template_id: templateId };
    if (hasConfigs) {
      payload.configs = selectedTpl.google_sheet_configs;
    }
    // If legacy only, no configs field; backend will use template's old fields

    const res = await api.jobs.ingestGoogleSheet(payload);

    if (!res.ok) {
      setSheetIngesting(false);
      setSheetProgress("");
      toast.error(`Không thể đồng bộ sheet: ${res.error}`);
      return;
    }

    setSheetProgress("Đã nhận task, đang theo dõi tiến độ…");
    await waitForIngestionTask(res.data.batch_id || res.data.task_id, setSheetProgress, onRefreshJobs);
    setSheetIngesting(false);
  }

  return (
    <div className="space-y-6">
      {/* Upload section */}
      <div className="rounded-lg border bg-background p-4 space-y-3">
        <h3 className="font-semibold">📤 Nạp tài liệu</h3>
        {templates.length === 0 && (
          <Alert variant="warning">
            <AlertDescription>
              Chưa có mẫu nào. Hãy tạo mẫu trong tab <strong>⚙️ Mẫu</strong> trước.
            </AlertDescription>
          </Alert>
        )}
        <div className="space-y-2">
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf"
            multiple
            className="block w-full text-sm file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-medium file:bg-primary file:text-primary-foreground hover:file:bg-primary/90 cursor-pointer"
            onChange={(e) => setSelectedFiles(Array.from(e.target.files ?? []))}
          />
          {selectedFiles.length > 0 && (
            <p className="text-sm text-muted-foreground">
              {selectedFiles.length} file đã chọn ({(selectedFiles.reduce((a, f) => a + f.size, 0) / 1024).toFixed(0)} KB)
            </p>
          )}
          <Select value={overrideTplId} onValueChange={setOverrideTplId}>
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__auto">🔄 Tự phát hiện mẫu</SelectItem>
              {templates.map((t) => (
                <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>

          {/* Google Sheets quick ingest button */}
          {overrideTplId !== "__auto" && (() => {
            const selectedTpl = templates.find(t => t.id === overrideTplId);
            const hasSheetConfig = selectedTpl?.google_sheet_id;
            if (hasSheetConfig) {
              return (
                <>
                  <Button
                    variant="outline"
                    onClick={() => handleSheetIngestionFromTemplate(overrideTplId)}
                    disabled={sheetIngesting}
                    className="w-full"
                  >
                    {sheetIngesting ? (
                      <><RefreshCw className="h-4 w-4 mr-2 animate-spin" />Đang đồng bộ…</>
                    ) : (
                      <>📥 Đồng bộ từ Google Sheets</>
                    )}
                  </Button>
                  {sheetProgress && <p className="text-sm text-muted-foreground mt-1">{sheetProgress}</p>}
                </>
              );
            }
            return null;
          })()}

          <Button onClick={handleUpload} disabled={uploading || selectedFiles.length === 0} className="w-full">
            {uploading ? (
              <><RefreshCw className="h-4 w-4 mr-2 animate-spin" />Đang gửi…</>
            ) : (
              <><Upload className="h-4 w-4 mr-2" />🚀 Nộp hồ sơ</>
            )}
          </Button>
        </div>
      </div>

      {/* Job list */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold">📋 Danh sách hồ sơ</h3>
          <Button variant="outline" size="sm" onClick={onRefreshJobs} disabled={loadingJobs}>
            <RefreshCw className={`h-4 w-4 mr-2 ${loadingJobs ? "animate-spin" : ""}`} />
            Làm mới
          </Button>
        </div>

        {/* Stats */}
        {jobs.length > 0 && (
          <div className="grid grid-cols-5 gap-3">
            {[
              { label: "Tổng", val: jobs.length },
              { label: "Đang xử lý", val: processing },
              { label: "Chờ duyệt", val: sc.ready_for_review ?? 0 },
              { label: "Đã duyệt", val: (sc.approved ?? 0) + (sc.aggregated ?? 0) },
              { label: "Cần xem lại", val: (sc.failed ?? 0) + (sc.rejected ?? 0) },
            ].map(({ label, val }) => (
              <div key={label} className="rounded-md border p-3 text-center">
                <div className="text-xl font-bold">{val}</div>
                <div className="text-xs text-muted-foreground">{label}</div>
              </div>
            ))}
          </div>
        )}

        {/* Filters */}
        <div className="flex gap-2">
          <Select value={statusFilter} onValueChange={(v) => setStatusFilter(v as StatusFilter)}>
            <SelectTrigger className="w-48">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Tất cả trạng thái</SelectItem>
              <SelectItem value="processing">🔄 Đang xử lý</SelectItem>
              <SelectItem value="ready_for_review">✅ Sẵn sàng duyệt</SelectItem>
              <SelectItem value="approved">✅ Đã duyệt</SelectItem>
              <SelectItem value="failed">⚠️ Cần xem lại</SelectItem>
            </SelectContent>
          </Select>
          <Select value={tplFilter} onValueChange={setTplFilter}>
            <SelectTrigger className="w-48">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__all">Tất cả mẫu</SelectItem>
              {templates.map((t) => (
                <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {loadingJobs ? (
          <TableSkeleton rows={10} columns={5} />
        ) : jobs.length === 0 ? (
          <p className="text-sm text-muted-foreground">Chưa có hồ sơ nào.</p>
        ) : filtered.length === 0 ? (
          <p className="text-sm text-muted-foreground">Không có hồ sơ nào phù hợp bộ lọc.</p>
        ) : (
          <div className="rounded-md border overflow-auto">
            <VirtualTable
              data={filtered}
              columns={[
                {
                  key: "file_name",
                  header: "Tên file",
                  width: "30%",
                  renderCell: (j: ExtractionJob) => (
                    <span className="font-medium max-w-xs truncate block" title={j.file_name ?? j.display_name ?? "(no name)"}>
                      {j.file_name ?? j.display_name ?? "(no name)"}
                    </span>
                  ),
                },
                {
                  key: "template",
                  header: "Mẫu",
                  width: "25%",
                  renderCell: (j: ExtractionJob) => (
                    <span className="text-sm text-muted-foreground">{tplMap[j.template_id ?? ""] ?? "—"}</span>
                  ),
                },
                {
                  key: "status",
                  header: "Trạng thái",
                  width: "20%",
                  renderCell: (j: ExtractionJob) => (
                    <Badge variant={statusBadgeVariant(j.status)} role="status">
                      {STATUS_VI[j.status] ?? j.status}
                    </Badge>
                  ),
                },
                {
                  key: "time",
                  header: "Thời gian",
                  width: "15%",
                  renderCell: (j: ExtractionJob) => (
                    <span className="text-sm text-muted-foreground">{formatDate(j.created_at)}</span>
                  ),
                },
                {
                  key: "actions",
                  header: "Thao tác",
                  width: "10%",
                  renderCell: (j: ExtractionJob) => {
                    const fname = j.file_name ?? j.display_name ?? "(no name)";
                    return (
                      <div className="flex gap-1">
                        {j.status === "failed" && (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handleRetry(j.id)}
                            disabled={retrying}
                          >
                            <RotateCcw className="h-3.5 w-3.5" />
                          </Button>
                        )}
                        {!["processing", "pending"].includes(j.status) && (
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => handleDelete(j.id)}
                            disabled={deletingId === j.id}
                            aria-label="Xoá hồ sơ"
                          >
                            <Trash2 className="h-3.5 w-3.5 text-destructive" />
                          </Button>
                        )}
                      </div>
                    );
                  },
                },
              ]}
              containerHeight="500px"
              rowHeight={45}
            />
          </div>
        )}
      </div>
    </div>
  );
}
