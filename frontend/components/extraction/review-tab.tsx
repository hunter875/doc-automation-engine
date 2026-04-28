"use client";

import { useState, useEffect } from "react";
import { RefreshCw, CheckCircle2, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { TableSkeleton } from "@/components/ui/table-skeleton";
import { VirtualTable } from "@/components/ui/virtual-table";
import { Checkbox } from "@/components/ui/checkbox";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import type { Template, ExtractionJob } from "@/lib/types";
import { toast } from "sonner";
import { STATUS_VI, statusBadgeVariant } from "@/lib/constants";

/** Render extracted_data as a smart visual layout */
function RenderExtractedData({ data }: { data: Record<string, unknown> }) {
  if (!data || Object.keys(data).length === 0) {
    return <p className="text-sm text-muted-foreground">Không có dữ liệu trích xuất.</p>;
  }

  const entries = Object.entries(data);
  const scalars = entries.filter(([, v]) => v !== null && typeof v !== "object");
  const arrays = entries.filter(([, v]) => Array.isArray(v)) as [string, unknown[]][];
  const objects = entries.filter(([, v]) => v !== null && typeof v === "object" && !Array.isArray(v)) as [string, Record<string, unknown>][];

  return (
    <div className="space-y-4 text-sm">
      {/* Scalar fields */}
      {scalars.length > 0 && (
        <div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
            {scalars.map(([k, v]) => (
              <div key={k} className="rounded-md border p-2">
                <div className="text-xs text-muted-foreground">{k}</div>
                <div className="font-medium truncate">{String(v ?? "—")}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Object fields (header, sections) */}
      {objects.map(([k, obj]) => (
        <div key={k}>
          <h4 className="font-semibold text-xs uppercase text-muted-foreground mb-2">{k}</h4>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
            {Object.entries(obj).filter(([, v]) => typeof v !== "object").map(([fk, fv]) => (
              <div key={fk} className="rounded-md border p-2">
                <div className="text-xs text-muted-foreground">{fk}</div>
                <div className="font-medium truncate">{String(fv ?? "—")}</div>
              </div>
            ))}
          </div>
        </div>
      ))}

      {/* Array fields — as table */}
      {arrays.map(([k, arr]) => (
        <div key={k}>
          <h4 className="font-semibold text-xs uppercase text-muted-foreground mb-2">{k} ({arr.length})</h4>
          {arr.length > 0 && typeof arr[0] === "object" ? (
            <div className="overflow-auto rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    {Object.keys(arr[0] as object).map((col) => (
                      <TableHead key={col}>{col}</TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(arr as Record<string, unknown>[]).map((row, i) => (
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
              {arr.map((item, i) => <li key={i}>{String(item)}</li>)}
            </ul>
          )}
        </div>
      ))}
    </div>
  );
}

interface ReviewTabProps {
  templates: Template[];
  jobs: ExtractionJob[];
  onRefreshJobs: () => void;
  loadingJobs: boolean;
}

export function ReviewTab({ templates, jobs, onRefreshJobs, loadingJobs }: ReviewTabProps) {
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [tplFilter, setTplFilter] = useState("__all");
  const [search, setSearch] = useState("");
  const [selectedJobId, setSelectedJobId] = useState<string>("");
  const [detail, setDetail] = useState<ExtractionJob | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [editJson, setEditJson] = useState("");
  const [parsedJson, setParsedJson] = useState<Record<string, unknown> | null>(null);
  const [notes, setNotes] = useState("");
  const [approving, setApproving] = useState(false);
  const [rejecting, setRejecting] = useState(false);

  // Bulk actions
  const [selectedJobIds, setSelectedJobIds] = useState<Set<string>>(new Set());
  const [bulkApproving, setBulkApproving] = useState(false);
  const [bulkRejecting, setBulkRejecting] = useState(false);
  const [bulkNotes, setBulkNotes] = useState("");

  const tplMap: Record<string, string> = {};
  templates.forEach((t) => { tplMap[t.id] = t.name; });

  const sc: Record<string, number> = {};
  jobs.forEach((j) => { sc[j.status] = (sc[j.status] ?? 0) + 1; });
  const processing = (sc.processing ?? 0) + (sc.pending ?? 0) + (sc.enriching ?? 0) + (sc.extracted ?? 0);

  // Filter
  const filtered = jobs.filter((j) => {
    if (statusFilter === "ready_for_review" && j.status !== "ready_for_review") return false;
    if (statusFilter === "approved" && j.status !== "approved") return false;
    if (statusFilter === "failed" && !["failed", "rejected"].includes(j.status)) return false;
    if (tplFilter !== "__all" && j.template_id !== tplFilter) return false;
    const fname = (j.file_name ?? j.display_name ?? "").toLowerCase();
    if (search && !fname.includes(search.toLowerCase())) return false;
    return true;
  });

  // Bulk actions: compute approvable job IDs (only these can be selected)
  const approvableIds = new Set(
    filtered.filter((j) => ["ready_for_review", "extracted"].includes(j.status)).map((j) => j.id)
  );
  const allSelected = approvableIds.size > 0 && selectedJobIds.size === approvableIds.size;

  function toggleJobSelection(jobId: string) {
    setSelectedJobIds((prev) => {
      const next = new Set(prev);
      if (next.has(jobId)) next.delete(jobId);
      else next.add(jobId);
      return next;
    });
  }

  function toggleSelectAll() {
    setSelectedJobIds((prev) => {
      if (prev.size === approvableIds.size) return new Set(); // clear
      return new Set(approvableIds);
    });
  }

  async function handleBulkApprove() {
    const idsToApprove = Array.from(selectedJobIds).filter((id) => approvableIds.has(id));
    if (idsToApprove.length === 0) return;
    if (!confirm(`Duyệt ${idsToApprove.length} hồ sơ?`)) return;
    setBulkApproving(true);
    const results = await Promise.all(
      idsToApprove.map(async (id) => {
        const job = jobs.find((j) => j.id === id)!;
        const finalData = job.reviewed_data ?? job.extracted_data ?? {};
        const res = await api.review.approve(id, { reviewed_data: finalData, notes: bulkNotes || null });
        return res.ok;
      })
    );
    const successCount = results.filter(Boolean).length;
    const failCount = results.length - successCount;
    setBulkApproving(false);
    setSelectedJobIds(new Set());
    setBulkNotes("");
    onRefreshJobs();
    toast.success(`Đã duyệt ${successCount} hồ sơ.${failCount > 0 ? ` ${failCount} thất bại.` : ""}`);
  }

  async function handleBulkReject() {
    if (!bulkNotes.trim()) {
      toast.warning("Bắt buộc nhập ghi chú lý do từ chối.");
      return;
    }
    const idsToReject = Array.from(selectedJobIds).filter((id) => approvableIds.has(id));
    if (idsToReject.length === 0) return;
    if (!confirm(`Từ chối ${idsToReject.length} hồ sơ?`)) return;
    setBulkRejecting(true);
    const results = await Promise.all(
      idsToReject.map(async (id) => {
        const res = await api.review.reject(id, { notes: bulkNotes });
        return res.ok;
      })
    );
    const successCount = results.filter(Boolean).length;
    const failCount = results.length - successCount;
    setBulkRejecting(false);
    setSelectedJobIds(new Set());
    setBulkNotes("");
    onRefreshJobs();
    toast.success(`Đã từ chối ${successCount} hồ sơ.${failCount > 0 ? ` ${failCount} thất bại.` : ""}`);
  }

  // Virtual table columns configuration
  const virtualColumns = [
    {
      key: "checkbox",
      header: (
        <div className="flex items-center justify-center">
          <Checkbox
            checked={allSelected}
            onCheckedChange={toggleSelectAll}
            aria-label="Chọn tất cả"
          />
        </div>
      ),
      width: "48px",
      renderCell: (j: ExtractionJob) => (
        <div onClick={(e) => e.stopPropagation()}>
          <Checkbox
            checked={selectedJobIds.has(j.id)}
            onCheckedChange={() => toggleJobSelection(j.id)}
            disabled={!approvableIds.has(j.id)}
          />
        </div>
      ),
    },
    {
      key: "file_name",
      header: "Tên file",
      width: "30%",
      renderCell: (j: ExtractionJob) => (
        <span className="font-medium max-w-xs truncate block">{j.file_name ?? j.display_name ?? "(no name)"}</span>
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
  ];

  // Load detail when job is selected
  useEffect(() => {
    if (!selectedJobId) return;
    setLoadingDetail(true);
    api.jobs.get(selectedJobId).then((res) => {
      setLoadingDetail(false);
      if (res.ok) {
        setDetail(res.data);
        const dataToShow = res.data.reviewed_data ?? res.data.extracted_data ?? {};
        setEditJson(JSON.stringify(dataToShow, null, 2));
        setParsedJson(null);
        setNotes(res.data.review_notes ?? "");
      } else {
        toast.error(`Không tải được chi tiết: ${res.error}`);
      }
    });
  }, [selectedJobId]);

  function validateJson() {
    try {
      const parsed = JSON.parse(editJson) as Record<string, unknown>;
      setParsedJson(parsed);
      toast.success(`JSON hợp lệ — ${Object.keys(parsed).length} mục.`);
    } catch (e) {
      toast.error(`JSON lỗi: ${String(e)}`);
      setParsedJson(null);
    }
  }

  async function handleApprove() {
    if (!detail) return;
    let finalData = parsedJson ?? detail.reviewed_data ?? detail.extracted_data ?? {};
    if (!parsedJson) {
      try { finalData = JSON.parse(editJson) as Record<string, unknown>; } catch { /* use existing */ }
    }
    setApproving(true);
    const res = await api.review.approve(detail.id, { reviewed_data: finalData, notes: notes || null });
    setApproving(false);
    if (res.ok) {
      toast.success("✅ Đã duyệt hồ sơ thành công!");
      setParsedJson(null);
      onRefreshJobs();
      setDetail(null);
      setSelectedJobId("");
    } else {
      toast.error(`Duyệt thất bại: ${res.error}`);
    }
  }

  async function handleReject() {
    if (!detail) return;
    if (!notes.trim()) { toast.warning("Bắt buộc phải có ghi chú lý do từ chối."); return; }
    setRejecting(true);
    const res = await api.review.reject(detail.id, { notes });
    setRejecting(false);
    if (res.ok) {
      toast.success("Đã từ chối hồ sơ.");
      onRefreshJobs();
      setDetail(null);
      setSelectedJobId("");
    } else {
      toast.error(`Từ chối thất bại: ${res.error}`);
    }
  }

  const canAct = detail && ["ready_for_review", "extracted"].includes(detail.status);

  return (
    <div className="space-y-4">
      {/* Header + stats */}
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Duyệt hồ sơ trích xuất</h2>
        <Button variant="outline" size="sm" onClick={onRefreshJobs} disabled={loadingJobs}>
          <RefreshCw className={`h-4 w-4 mr-2 ${loadingJobs ? "animate-spin" : ""}`} />
          Làm mới
        </Button>
      </div>

      {jobs.length > 0 && (
        <div className="grid grid-cols-5 gap-3">
          {[
            { label: "Tổng hồ sơ", val: jobs.length },
            { label: "Sẵn sàng duyệt", val: sc.ready_for_review ?? 0 },
            { label: "Đã duyệt", val: sc.approved ?? 0 },
            { label: "Đang xử lý", val: processing },
            { label: "Cần xem lại", val: sc.failed ?? 0 },
          ].map(({ label, val }) => (
            <div key={label} className="rounded-md border p-3 text-center">
              <div className="text-xl font-bold">{val}</div>
              <div className="text-xs text-muted-foreground">{label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Filters */}
      <div className="flex gap-2 flex-wrap">
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-48">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Tất cả</SelectItem>
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
        <Input
          placeholder="🔎 Tìm theo tên file…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-64"
        />
      </div>

      {/* Job table */}
      {loadingJobs ? (
        <TableSkeleton rows={10} columns={5} />
      ) : filtered.length === 0 ? (
        <p className="text-sm text-muted-foreground">Không tìm thấy hồ sơ nào.</p>
      ) : (
        <>
          {selectedJobIds.size > 0 && (
            <div className="bg-accent/50 border rounded-md p-3 mb-3 flex items-center gap-3">
              <Checkbox
                checked={allSelected}
                onCheckedChange={toggleSelectAll}
                aria-label="Chọn tất cả"
              />
              <span className="font-medium text-sm">{selectedJobIds.size} hồ sơ được chọn</span>
              <Input
                placeholder="Ghi chú (bắt buộc cho từ chối)"
                value={bulkNotes}
                onChange={(e) => setBulkNotes(e.target.value)}
                className="max-w-xs h-8 text-sm"
              />
              <Button size="sm" onClick={handleBulkApprove} disabled={bulkApproving}>
                {bulkApproving ? "Đang duyệt…" : "✅ Duyệt"}
              </Button>
              <Button size="sm" variant="destructive" onClick={handleBulkReject} disabled={bulkRejecting}>
                {bulkRejecting ? "Đang từ chối…" : "❌ Từ chối"}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setSelectedJobIds(new Set())} aria-label="Xoá chọn">
                ✕
              </Button>
            </div>
          )}
          <VirtualTable
            data={filtered}
            columns={virtualColumns}
            containerHeight="288px"
            className="rounded-md border"
            getRowClassName={(j) => `cursor-pointer ${selectedJobId === j.id ? "bg-accent" : ""}`}
            onRowClick={(j) => setSelectedJobId(j.id)}
            caption="Danh sách hồ sơ, chọn để duyệt hoặc từ chối"
          />
        </>
      )}

      {/* Detail panel */}
      {selectedJobId && (
        <>
          <Separator />
          {loadingDetail ? (
            <p className="text-sm text-muted-foreground">Đang tải chi tiết…</p>
          ) : detail ? (
            <div className="space-y-4">
              {/* Job header */}
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="text-lg font-semibold">
                    📄 {detail.file_name ?? detail.display_name}
                  </h3>
                  <p className="text-sm text-muted-foreground">
                    Mẫu: <strong>{tplMap[detail.template_id ?? ""] ?? "—"}</strong>
                    {detail.processing_time_ms && (
                      <span> · Xử lý: {(detail.processing_time_ms / 1000).toFixed(1)}s</span>
                    )}
                  </p>
                </div>
                <Badge variant={statusBadgeVariant(detail.status)} role="status">
                  {STATUS_VI[detail.status] ?? detail.status}
                </Badge>
              </div>

              {detail.error_message && (
                <Alert variant="warning">
                  <AlertDescription>Ghi chú hệ thống: {detail.error_message.slice(0, 200)}</AlertDescription>
                </Alert>
              )}

              {/* View / Edit tabs */}
              <Tabs defaultValue="view">
                <TabsList>
                  <TabsTrigger value="view">👁️ Dữ liệu trích xuất</TabsTrigger>
                  <TabsTrigger value="edit">✏️ Chỉnh sửa JSON</TabsTrigger>
                </TabsList>
                <TabsContent value="view" className="pt-3">
                  {detail.reviewed_data && (
                    <Alert variant="success" className="mb-3">
                      <AlertDescription>ℹ️ Đang hiển thị bản đã chỉnh sửa.</AlertDescription>
                    </Alert>
                  )}
                  <RenderExtractedData
                    data={(detail.reviewed_data ?? detail.extracted_data ?? {}) as Record<string, unknown>}
                  />
                </TabsContent>
                <TabsContent value="edit" className="pt-3 space-y-2">
                  <Textarea
                    value={editJson}
                    onChange={(e) => { setEditJson(e.target.value); setParsedJson(null); }}
                    className="font-mono text-xs"
                    rows={14}
                  />
                  <Button variant="outline" size="sm" onClick={validateJson}>
                    ✅ Kiểm tra JSON
                  </Button>
                  {parsedJson && (
                    <span className="text-xs text-green-600 ml-2">JSON hợp lệ ✓</span>
                  )}
                </TabsContent>
              </Tabs>

              {/* Approve/Reject */}
              <Separator />
              <div className="space-y-3">
                <h4 className="font-semibold">🛂 Xử lý hồ sơ</h4>
                {detail.status === "approved" && (
                  <Alert variant="success">
                    <AlertDescription>
                      ✅ Hồ sơ đã được duyệt. Bạn vẫn có thể duyệt lại để cập nhật.
                      {detail.review_notes && (
                        <span className="ml-1">Ghi chú: {detail.review_notes}</span>
                      )}
                    </AlertDescription>
                  </Alert>
                )}
                <Textarea
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="Ghi chú (không bắt buộc với Duyệt, bắt buộc với Từ chối)"
                  rows={2}
                />
                <div className="flex gap-2">
                  <Button
                    onClick={handleApprove}
                    disabled={!canAct || approving}
                    className="flex-1"
                  >
                    <CheckCircle2 className="h-4 w-4 mr-2" />
                    {approving ? "Đang duyệt…" : "✅ DUYỆT HỒ SƠ"}
                  </Button>
                  <Button
                    variant="destructive"
                    onClick={handleReject}
                    disabled={!canAct || rejecting}
                    className="flex-1"
                  >
                    <XCircle className="h-4 w-4 mr-2" />
                    {rejecting ? "Đang từ chối…" : "❌ TỪ CHỐI"}
                  </Button>
                </div>
                {!canAct && detail.status !== "approved" && (
                  <p className="text-xs text-muted-foreground">
                    💡 Trạng thái hiện tại là <strong>{STATUS_VI[detail.status] ?? detail.status}</strong> — chưa thể duyệt/từ chối cho đến khi AI xử lý xong.
                  </p>
                )}
              </div>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}
