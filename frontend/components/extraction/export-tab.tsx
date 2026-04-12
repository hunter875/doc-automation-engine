"use client";

import { useEffect, useState } from "react";
import { RefreshCw, Download, Trash2, FileSpreadsheet, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Separator } from "@/components/ui/separator";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import { formatDate, downloadBlob } from "@/lib/utils";
import type { Template, ExtractionJob, AggregationReport } from "@/lib/types";
import { toast } from "sonner";

interface ExportTabProps {
  templates: Template[];
  jobs: ExtractionJob[];
}

function RenderAggPreview({ data }: { data: Record<string, unknown> }) {
  const SKIP = new Set(["records", "_source_records", "_flat_records", "_metadata", "metrics"]);
  const scalars = Object.entries(data).filter(
    ([k, v]) => !SKIP.has(k) && !k.startsWith("_") && typeof v !== "object"
  );
  const arrays = Object.entries(data).filter(
    ([k, v]) => !SKIP.has(k) && !k.startsWith("_") && Array.isArray(v)
  ) as [string, unknown[]][];

  return (
    <div className="space-y-4 text-sm">
      {scalars.length > 0 && (
        <div>
          <p className="font-semibold text-xs text-muted-foreground mb-2">Chỉ số tổng hợp:</p>
          <div className="grid grid-cols-3 md:grid-cols-5 gap-2">
            {scalars.map(([k, v]) => (
              <div key={k} className="rounded-md border p-2 text-center">
                <div className="font-bold">{String(v ?? 0)}</div>
                <div className="text-xs text-muted-foreground truncate">{k}</div>
              </div>
            ))}
          </div>
        </div>
      )}
      {arrays.map(([k, arr]) => (
        <div key={k}>
          <p className="font-semibold text-xs text-muted-foreground mb-2">
            {k} ({arr.length} phần tử):
          </p>
          {arr.length > 0 && typeof arr[0] === "object" ? (
            <div className="overflow-auto rounded-md border max-h-60">
              <Table>
                <TableHeader>
                  <TableRow>
                    {Object.keys(arr[0] as object).map((col) => (
                      <TableHead key={col}>{col}</TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(arr as Record<string, unknown>[]).slice(0, 50).map((row, i) => (
                    <TableRow key={i}>
                      {Object.values(row).map((val, ci) => (
                        <TableCell key={ci}>{String(val ?? "—")}</TableCell>
                      ))}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          ) : (
            <ul className="list-disc list-inside space-y-0.5">
              {arr.slice(0, 20).map((item, i) => <li key={i}>{String(item)}</li>)}
            </ul>
          )}
        </div>
      ))}
    </div>
  );
}

export function ExportTab({ templates, jobs }: ExportTabProps) {
  const [reports, setReports] = useState<AggregationReport[]>([]);
  const [loadingReports, setLoadingReports] = useState(false);
  const [selectedReportId, setSelectedReportId] = useState<string>("");
  const [reportDetail, setReportDetail] = useState<AggregationReport | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  // Create report form
  const [selTplId, setSelTplId] = useState<string>("");
  const [reportName, setReportName] = useState(
    `Báo cáo ${new Date().toLocaleDateString("vi-VN")}`
  );
  const [selectedJobIds, setSelectedJobIds] = useState<Set<string>>(new Set());
  const [creating, setCreating] = useState(false);

  // Export state
  const [exporting, setExporting] = useState<string | null>(null);
  const [wordUploadFile, setWordUploadFile] = useState<File | null>(null);
  const [deleting, setDeleting] = useState(false);

  const tplMap: Record<string, string> = {};
  templates.forEach((t) => { tplMap[t.id] = t.name; });

  async function loadReports() {
    setLoadingReports(true);
    const res = await api.reports.list();
    setLoadingReports(false);
    if (res.ok) {
      const list = Array.isArray(res.data)
        ? res.data
        : (res.data as { items?: AggregationReport[] }).items ?? [];
      setReports(list);
    } else {
      toast.error(`Lỗi tải báo cáo: ${res.error}`);
    }
  }

  useEffect(() => { loadReports(); }, []);

  useEffect(() => {
    if (!selectedReportId) { setReportDetail(null); return; }
    setLoadingDetail(true);
    api.reports.get(selectedReportId).then((res) => {
      setLoadingDetail(false);
      if (res.ok) setReportDetail(res.data);
    });
  }, [selectedReportId]);

  const approvedJobs = jobs.filter((j) => j.status === "approved");
  const tplsWithJobs = Array.from(new Set(approvedJobs.map((j) => j.template_id ?? "").filter(Boolean)));
  const jobsForTpl = approvedJobs.filter((j) => j.template_id === selTplId);

  function toggleJob(id: string) {
    setSelectedJobIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  async function handleCreateReport() {
    if (!selTplId || selectedJobIds.size === 0) {
      toast.warning("Chọn mẫu và ít nhất 1 hồ sơ.");
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
      toast.success(`✅ Đã tạo báo cáo "${res.data.name}"!`);
      setSelectedJobIds(new Set());
      loadReports();
      setSelectedReportId(res.data.id);
    } else {
      toast.error(`Tổng hợp thất bại: ${res.error}`);
    }
  }

  async function handleExportExcel() {
    if (!selectedReportId) return;
    setExporting("excel");
    const res = await api.reports.exportExcel(selectedReportId);
    setExporting(null);
    if (res.ok) {
      const report = reports.find((r) => r.id === selectedReportId);
      downloadBlob(res.data, `${report?.name ?? "Report"}_${selectedReportId.slice(-6)}.xlsx`);
      toast.success("Đã tải Excel!");
    } else {
      toast.error(`Lỗi Excel: ${res.error}`);
    }
  }

  async function handleExportWordAuto() {
    if (!selectedReportId) return;
    setExporting("word-auto");
    const res = await api.reports.exportWordAuto(selectedReportId);
    setExporting(null);
    if (res.ok) {
      const report = reports.find((r) => r.id === selectedReportId);
      downloadBlob(res.data, `${report?.name ?? "Report"}.docx`);
      toast.success("Đã tải Word!");
    } else {
      toast.error(`Lỗi Word: ${res.error}`);
    }
  }

  async function handleExportWordUpload() {
    if (!selectedReportId || !wordUploadFile) return;
    setExporting("word-upload");
    const fd = new FormData();
    fd.append("file", wordUploadFile);
    fd.append("record_index", "0");
    const res = await api.reports.exportWordUpload(selectedReportId, fd);
    setExporting(null);
    if (res.ok) {
      const report = reports.find((r) => r.id === selectedReportId);
      downloadBlob(res.ok ? res.data as unknown as Blob : new Blob(), `${report?.name ?? "Report"}_custom.docx`);
      toast.success("Đã tải Word (mẫu upload)!");
    } else {
      toast.error(`Lỗi Word upload: ${res.error}`);
    }
  }

  async function handleDelete() {
    if (!selectedReportId || !confirm("Xoá báo cáo này? Hành động không thể hoàn tác.")) return;
    setDeleting(true);
    const res = await api.reports.delete(selectedReportId);
    setDeleting(false);
    if (res.ok) {
      toast.success("Đã xoá báo cáo.");
      setSelectedReportId("");
      setReportDetail(null);
      loadReports();
    } else {
      toast.error(`Xoá thất bại: ${res.error}`);
    }
  }

  function handleExportJson() {
    if (!reportDetail?.aggregated_data) return;
    const clean = Object.fromEntries(
      Object.entries(reportDetail.aggregated_data).filter(([k]) => !k.startsWith("_") && k !== "metrics")
    );
    downloadBlob(
      new Blob([JSON.stringify(clean, null, 2)], { type: "application/json" }),
      `${reports.find((r) => r.id === selectedReportId)?.name ?? "Report"}.json`
    );
    toast.success("Đã tải JSON!");
  }

  return (
    <div className="space-y-6">
      {/* Section 1 — Create */}
      <div>
        <h3 className="font-semibold text-base mb-3">1️⃣ Tạo báo cáo mới</h3>
        {approvedJobs.length === 0 ? (
          <Alert variant="warning">
            <AlertDescription>
              Chưa có hồ sơ nào được duyệt. Hãy duyệt hồ sơ trong tab <strong>📥 Duyệt</strong> trước.
            </AlertDescription>
          </Alert>
        ) : (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Mẫu báo cáo</Label>
                <Select value={selTplId} onValueChange={(v) => { setSelTplId(v); setSelectedJobIds(new Set()); }}>
                  <SelectTrigger className="mt-1.5">
                    <SelectValue placeholder="Chọn mẫu…" />
                  </SelectTrigger>
                  <SelectContent>
                    {tplsWithJobs.map((tid) => (
                      <SelectItem key={tid} value={tid}>{tplMap[tid] ?? tid.slice(0, 8)}</SelectItem>
                    ))}
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

            {selTplId && jobsForTpl.length === 0 && (
              <p className="text-sm text-muted-foreground">Mẫu này chưa có hồ sơ nào được duyệt.</p>
            )}

            {selTplId && jobsForTpl.length > 0 && (
              <>
                <p className="text-sm text-muted-foreground">
                  {jobsForTpl.length} hồ sơ đã duyệt · đã chọn {selectedJobIds.size}
                </p>
                <div className="flex gap-2">
                  <Button variant="outline" size="sm"
                    onClick={() => setSelectedJobIds(new Set(jobsForTpl.map((j) => j.id)))}>
                    ☑️ Chọn tất cả
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => setSelectedJobIds(new Set())}>
                    ⬜ Bỏ chọn
                  </Button>
                </div>
                <div className="rounded-md border overflow-auto max-h-48">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-8">✓</TableHead>
                        <TableHead>Tên file</TableHead>
                        <TableHead>Thời gian</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {jobsForTpl.map((j) => {
                        const fname = j.file_name ?? j.display_name ?? "(no name)";
                        return (
                          <TableRow
                            key={j.id}
                            className="cursor-pointer"
                            onClick={() => toggleJob(j.id)}
                          >
                            <TableCell>
                              <input type="checkbox" checked={selectedJobIds.has(j.id)} readOnly />
                            </TableCell>
                            <TableCell className="font-medium">{fname}</TableCell>
                            <TableCell className="text-sm text-muted-foreground">
                              {formatDate(j.created_at)}
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </div>
                <Button
                  onClick={handleCreateReport}
                  disabled={creating || selectedJobIds.size === 0}
                  className="w-full"
                >
                  {creating ? (
                    <><RefreshCw className="h-4 w-4 mr-2 animate-spin" />Đang tổng hợp…</>
                  ) : (
                    `📊 Tổng hợp ${selectedJobIds.size} hồ sơ → ${reportName}`
                  )}
                </Button>
              </>
            )}
          </div>
        )}
      </div>

      <Separator />

      {/* Section 2 — Report list + export */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold text-base">2️⃣ Danh sách báo cáo</h3>
          <Button variant="outline" size="sm" onClick={loadReports} disabled={loadingReports}>
            <RefreshCw className={`h-4 w-4 mr-2 ${loadingReports ? "animate-spin" : ""}`} />
            Làm mới
          </Button>
        </div>

        {reports.length === 0 ? (
          <p className="text-sm text-muted-foreground">Chưa có báo cáo nào.</p>
        ) : (
          <div className="space-y-3">
            <Select value={selectedReportId} onValueChange={setSelectedReportId}>
              <SelectTrigger>
                <SelectValue placeholder="Chọn báo cáo để xuất…" />
              </SelectTrigger>
              <SelectContent>
                {reports.map((r) => (
                  <SelectItem key={r.id} value={r.id}>
                    📑 {r.name} ({r.total_jobs ?? 0} hồ sơ · {formatDate(r.created_at)})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            {selectedReportId && (
              <>
                {/* Info row */}
                {reportDetail && (
                  <div className="grid grid-cols-4 gap-3">
                    {[
                      { label: "Hồ sơ gom", val: reportDetail.total_jobs ?? 0 },
                      { label: "Đã duyệt", val: reportDetail.approved_jobs ?? 0 },
                      {
                        label: "Luật đã áp",
                        val: (reportDetail.aggregated_data?.["_metadata"] as Record<string, unknown>)?.rules_applied ?? "—",
                      },
                      { label: "Tạo lúc", val: formatDate(reportDetail.created_at) },
                    ].map(({ label, val }) => {
                      const displayVal = typeof val === "string" || typeof val === "number"
                        ? val
                        : val == null
                          ? "—"
                          : JSON.stringify(val);

                      return (
                      <div key={label} className="rounded-md border p-3 text-center">
                        <div className="text-lg font-bold">{displayVal}</div>
                        <div className="text-xs text-muted-foreground">{label}</div>
                      </div>
                      );
                    })}
                  </div>
                )}

                {/* Aggregated data preview */}
                {loadingDetail ? (
                  <p className="text-sm text-muted-foreground">Đang tải…</p>
                ) : reportDetail?.aggregated_data && (
                  <div className="rounded-md border p-4">
                    <p className="text-sm font-semibold mb-3">🔍 Dữ liệu tổng hợp:</p>
                    <RenderAggPreview data={reportDetail.aggregated_data as Record<string, unknown>} />
                  </div>
                )}

                {/* Export buttons */}
                <div>
                  <Label className="text-sm font-semibold">📤 Xuất file</Label>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-2">
                    <Button
                      variant="outline"
                      onClick={handleExportExcel}
                      disabled={exporting === "excel"}
                    >
                      <FileSpreadsheet className="h-4 w-4 mr-2" />
                      {exporting === "excel" ? "Đang build…" : "Excel"}
                    </Button>
                    <Button
                      variant="outline"
                      onClick={handleExportWordAuto}
                      disabled={exporting === "word-auto"}
                    >
                      <FileText className="h-4 w-4 mr-2" />
                      {exporting === "word-auto" ? "Đang render…" : "Word (auto)"}
                    </Button>
                    <Button
                      variant="outline"
                      onClick={handleExportJson}
                    >
                      <Download className="h-4 w-4 mr-2" />
                      JSON
                    </Button>

                    {/* Word upload */}
                    <div className="space-y-1">
                      <Input
                        type="file"
                        accept=".docx"
                        className="h-9 text-xs"
                        onChange={(e) => setWordUploadFile(e.target.files?.[0] ?? null)}
                      />
                      {wordUploadFile && (
                        <Button
                          variant="outline"
                          size="sm"
                          className="w-full"
                          onClick={handleExportWordUpload}
                          disabled={exporting === "word-upload"}
                        >
                          <FileText className="h-4 w-4 mr-2" />
                          {exporting === "word-upload" ? "Đang render…" : "Word (mẫu upload)"}
                        </Button>
                      )}
                    </div>
                  </div>
                </div>

                {/* Danger zone */}
                <div className="rounded-md border-destructive/30 border p-3 space-y-2">
                  <p className="text-xs text-muted-foreground">
                    ⚠️ Hành động không thể hoàn tác. Chỉ xoá báo cáo, không xoá hồ sơ gốc.
                  </p>
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={handleDelete}
                    disabled={deleting}
                  >
                    <Trash2 className="h-4 w-4 mr-1.5" />
                    {deleting ? "Đang xoá…" : "Xoá báo cáo này"}
                  </Button>
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
