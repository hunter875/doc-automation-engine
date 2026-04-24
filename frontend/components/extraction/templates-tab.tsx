"use client";

import { useEffect, useState, useCallback } from "react";
import { Plus, RefreshCw, Trash2, Paperclip, ChevronDown, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Separator } from "@/components/ui/separator";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import type { Template, TemplateField, ScanWordResult } from "@/lib/types";
import { toast } from "sonner";

const FIELD_TYPES = ["string", "number", "boolean", "array"];
const AGG_METHODS = ["", "SUM", "AVG", "MAX", "MIN", "COUNT", "CONCAT", "LAST"];
const NO_AGG_VALUE = "__none";

interface TemplatesTabProps {
  templates: Template[];
  onRefresh: () => void;
  loading: boolean;
}

interface FieldRow {
  selected: boolean;
  name: string;
  originalName: string;
  type: string;
  required: boolean;
  agg: string;
  desc: string;
}

function defaultAgg(type: string, name: string): string {
  const n = name.toLowerCase();
  if (["ngay_", "thang_", "nam_", "bao_cao", "ky_"].some((h) => n.includes(h))) return "";
  if (type === "number") return "SUM";
  if (type === "array") return "CONCAT";
  return "LAST";
}

export function TemplatesTab({ templates, onRefresh, loading }: TemplatesTabProps) {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  // Create form state
  const [createMode, setCreateMode] = useState<"scan" | "manual" | null>(null);
  const [scanFile, setScanFile] = useState<File | null>(null);
  const [scanning, setScanning] = useState(false);
  const [scanResult, setScanResult] = useState<ScanWordResult | null>(null);
  const [fieldRows, setFieldRows] = useState<FieldRow[]>([]);
  const [templateName, setTemplateName] = useState("");
  const [creating, setCreating] = useState(false);

  // Google Sheets config
  const [gsheetId, setGsheetId] = useState("");
  const [gsheetWorksheet, setGsheetWorksheet] = useState("");
  const [gsheetRange, setGsheetRange] = useState("");
  const [gsheetSchemaPath, setGsheetSchemaPath] = useState("");

  // Attach word dialog
  const [attachTarget, setAttachTarget] = useState<Template | null>(null);
  const [attachFile, setAttachFile] = useState<File | null>(null);
  const [attaching, setAttaching] = useState(false);

  async function handleDelete(tpl: Template) {
    if (!confirm(`Xoá mẫu "${tpl.name}"?`)) return;
    setDeleting(tpl.id);
    const res = await api.templates.delete(tpl.id);
    setDeleting(null);
    if (res.ok) {
      toast.success("Đã xoá mẫu.");
      onRefresh();
    } else {
      toast.error(`Xoá thất bại: ${res.error}`);
    }
  }

  async function handleScanWord() {
    if (!scanFile) return;
    setScanning(true);
    const fd = new FormData();
    fd.append("file", scanFile);
    const res = await api.templates.scanWord(fd);
    setScanning(false);
    if (!res.ok) {
      toast.error(`Scan thất bại: ${res.error}`);
      return;
    }
    const scanData = res.data as ScanWordResult;
    setScanResult(scanData);
    const schemaFields = scanData.schema_definition?.fields ?? [];
    const varMap: Record<string, string> = {};
    (scanData.variables ?? []).forEach((v) => { varMap[v.name] = v.original_name ?? v.name; });
    const aggMap: Record<string, string> = {};
    (scanData.aggregation_rules?.rules ?? []).forEach((r) => { aggMap[r.output_field] = r.method; });
    setFieldRows(
      schemaFields.map((f) => ({
        selected: true,
        name: f.name,
        originalName: varMap[f.name] ?? f.name,
        type: f.type,
        required: f.required ?? true,
        agg: aggMap[f.name] ?? defaultAgg(f.type, f.name),
        desc: f.description ?? "",
      }))
    );
    setTemplateName(scanFile.name.replace(/\.docx$/i, ""));
    toast.success(`Scan xong — phát hiện ${schemaFields.length} trường.`);
  }

  async function handleCreate() {
    if (!templateName.trim()) { toast.warning("Nhập tên mẫu."); return; }
    const selectedRows = fieldRows.filter((r) => r.selected && r.name.trim());
    if (selectedRows.length === 0) { toast.warning("Chọn ít nhất 1 trường."); return; }

    const schemaFields: TemplateField[] = selectedRows.map((r) => ({
      name: r.name,
      type: r.type as TemplateField["type"],
      description: r.desc,
      required: r.required,
    }));
    const aggRules = selectedRows
      .filter((r) => r.agg)
      .map((r) => ({
        output_field: r.name,
        source_field: r.name,
        method: r.agg,
        label: r.desc || r.name.replace(/_/g, " "),
      }));

    const payload: any = {
      name: templateName.trim(),
      schema_definition: { fields: schemaFields },
      aggregation_rules: { rules: aggRules },
      extraction_mode: "block",
      ...(scanResult?.word_template_s3_key
        ? { word_template_s3_key: scanResult.word_template_s3_key }
        : {}),
    };

    // Add Google Sheets config if provided
    if (gsheetId.trim()) payload.google_sheet_id = gsheetId.trim();
    if (gsheetWorksheet.trim()) payload.google_sheet_worksheet = gsheetWorksheet.trim();
    if (gsheetRange.trim()) payload.google_sheet_range = gsheetRange.trim();
    if (gsheetSchemaPath.trim()) payload.google_sheet_schema_path = gsheetSchemaPath.trim();

    setCreating(true);
    const res = await api.templates.create(payload);
    setCreating(false);
    if (res.ok) {
      toast.success(`Đã tạo mẫu "${res.data.name}".`);
      setCreateMode(null);
      setScanResult(null);
      setFieldRows([]);
      setTemplateName("");
      setScanFile(null);
      // Reset Google Sheets config
      setGsheetId("");
      setGsheetWorksheet("");
      setGsheetRange("");
      setGsheetSchemaPath("");
      onRefresh();
    } else {
      toast.error(`Tạo thất bại: ${res.error}`);
    }
  }

  async function handleAttach() {
    if (!attachTarget || !attachFile) return;
    setAttaching(true);
    const fd = new FormData();
    fd.append("file", attachFile);
    const scanRes = await api.templates.scanWord(fd);
    if (!scanRes.ok) {
      setAttaching(false);
      toast.error(`Scan thất bại: ${scanRes.error}`);
      return;
    }
    const key = scanRes.data.word_template_s3_key;
    if (!key) {
      setAttaching(false);
      toast.error("Upload S3 thất bại.");
      return;
    }
    const patchRes = await api.templates.patch(attachTarget.id, { word_template_s3_key: key });
    setAttaching(false);
    if (patchRes.ok) {
      toast.success("Đã gắn Word template!");
      setAttachTarget(null);
      setAttachFile(null);
      onRefresh();
    } else {
      toast.error(`Gắn thất bại: ${patchRes.error}`);
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold">Quản lý Mẫu</h2>
          <p className="text-sm text-muted-foreground mt-1">
            Tạo mẫu bằng cách quét file Word hoặc nhập thủ công.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={onRefresh} disabled={loading}>
            <RefreshCw className={`h-4 w-4 mr-2 ${loading ? "animate-spin" : ""}`} />
            Làm mới
          </Button>
          <Button size="sm" onClick={() => setCreateMode("scan")}>
            <Plus className="h-4 w-4 mr-2" /> Tạo mẫu mới
          </Button>
        </div>
      </div>

      {/* Template list */}
      {templates.length === 0 ? (
        <p className="text-sm text-muted-foreground">Chưa có mẫu nào. Nhấn "Tạo mẫu mới" để bắt đầu.</p>
      ) : (
        <div className="space-y-2">
          {templates.map((tpl) => {
            const fields = tpl.schema_definition?.fields ?? [];
            const aggCount = tpl.aggregation_rules?.rules?.length ?? 0;
            const isOpen = expandedId === tpl.id;
            return (
              <div key={tpl.id} className="rounded-lg border bg-background">
                <button
                  className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-muted/40 transition-colors"
                  onClick={() => setExpandedId(isOpen ? null : tpl.id)}
                >
                  <div className="flex items-center gap-3 min-w-0">
                    {isOpen ? <ChevronDown className="h-4 w-4 shrink-0" /> : <ChevronRight className="h-4 w-4 shrink-0" />}
                    <span className="font-medium truncate">{tpl.name}</span>
                    <div className="flex gap-1.5 shrink-0">
                      <Badge variant="secondary">{fields.length} trường</Badge>
                      {aggCount > 0 && <Badge variant="info">{aggCount} luật</Badge>}
                      {tpl.word_template_s3_key && <Badge variant="success">📝 Word</Badge>}
                      {tpl.filename_pattern && <Badge variant="purple">🎯 Auto</Badge>}
                    </div>
                  </div>
                  <span className="text-xs text-muted-foreground shrink-0 ml-4">{formatDate(tpl.created_at)}</span>
                </button>

                {isOpen && (
                  <div className="px-4 pb-4 space-y-3 border-t pt-3">
                    {fields.length > 0 ? (
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>Tên trường</TableHead>
                            <TableHead>Loại</TableHead>
                            <TableHead>Tổng hợp</TableHead>
                            <TableHead>Mô tả</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {fields.map((f) => {
                            const aggMethod = tpl.aggregation_rules?.rules?.find(
                              (r) => r.output_field === f.name
                            )?.method ?? "";
                            return (
                              <TableRow key={f.name}>
                                <TableCell className="font-mono text-sm">{f.name}</TableCell>
                                <TableCell>
                                  <Badge variant="outline">{f.type}</Badge>
                                </TableCell>
                                <TableCell>{aggMethod || "—"}</TableCell>
                                <TableCell className="text-muted-foreground text-sm">
                                  {f.description || "—"}
                                </TableCell>
                              </TableRow>
                            );
                          })}
                        </TableBody>
                      </Table>
                    ) : (
                      <p className="text-sm text-muted-foreground">Không có trường nào.</p>
                    )}
                    {!tpl.word_template_s3_key && (
                      <Alert variant="warning">
                        <AlertDescription className="text-sm">
                          ⚠️ Chưa có Word template — chưa thể export Word
                        </AlertDescription>
                      </Alert>
                    )}
                    <div className="flex gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setAttachTarget(tpl)}
                      >
                        <Paperclip className="h-4 w-4 mr-1.5" />
                        {tpl.word_template_s3_key ? "Thay Word template" : "Gắn Word template"}
                      </Button>
                      <Button
                        variant="destructive"
                        size="sm"
                        onClick={() => handleDelete(tpl)}
                        disabled={deleting === tpl.id}
                      >
                        <Trash2 className="h-4 w-4 mr-1.5" />
                        {deleting === tpl.id ? "Đang xoá…" : "Xoá"}
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Create Dialog */}
      <Dialog open={createMode !== null} onOpenChange={(open) => !open && setCreateMode(null)}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Tạo mẫu mới</DialogTitle>
            <DialogDescription>
              Quét từ file Word (.docx) có chứa các trường dạng {"{{tên_trường}}"} 
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            {/* Scan step */}
            {!scanResult ? (
              <div className="space-y-3">
                <div>
                  <Label>Chọn file Word (.docx)</Label>
                  <div className="flex gap-2 mt-1.5">
                    <Input
                      type="file"
                      accept=".docx"
                      onChange={(e) => setScanFile(e.target.files?.[0] ?? null)}
                      className="flex-1"
                    />
                    <Button
                      onClick={handleScanWord}
                      disabled={!scanFile || scanning}
                    >
                      {scanning ? "Đang quét…" : "🔍 Scan"}
                    </Button>
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">
                    File Word phải chứa các trường dạng {"{{tên_trường}}"} 
                  </p>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                {/* Stats */}
                <div className="grid grid-cols-4 gap-3">
                  {[
                    { label: "Trường đơn", val: scanResult.stats?.unique_variables ?? 0 },
                    { label: "Danh sách", val: scanResult.stats?.array_with_object_schema ?? 0 },
                    { label: "Tổng trường", val: scanResult.stats?.total_holes ?? 0 },
                    { label: "Vòng lặp", val: scanResult.stats?.loop_count ?? 0 },
                  ].map(({ label, val }) => (
                    <div key={label} className="rounded-md border p-3 text-center">
                      <div className="text-xl font-bold">{val}</div>
                      <div className="text-xs text-muted-foreground">{label}</div>
                    </div>
                  ))}
                </div>

                {/* Template name */}
                <div>
                  <Label>Tên mẫu</Label>
                  <Input
                    value={templateName}
                    onChange={(e) => setTemplateName(e.target.value)}
                    placeholder="Nhập tên mẫu…"
                    className="mt-1.5"
                  />
                </div>

                {/* Field editor */}
                <div>
                  <Label>Tinh chỉnh cấu trúc</Label>
                  <div className="mt-1.5 rounded-md border overflow-auto max-h-80">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead className="w-8">✓</TableHead>
                          <TableHead>Tên trường</TableHead>
                          <TableHead>Loại</TableHead>
                          <TableHead>Phương thức TH</TableHead>
                          <TableHead>Mô tả</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {fieldRows.map((row, i) => (
                          <TableRow key={row.name} className={!row.selected ? "opacity-50" : ""}>
                            <TableCell>
                              <input
                                type="checkbox"
                                checked={row.selected}
                                onChange={(e) => {
                                  const next = [...fieldRows];
                                  next[i] = { ...next[i], selected: e.target.checked };
                                  setFieldRows(next);
                                }}
                              />
                            </TableCell>
                            <TableCell className="font-mono text-sm">{row.name}</TableCell>
                            <TableCell>
                              <Select
                                value={row.type}
                                onValueChange={(v) => {
                                  const next = [...fieldRows];
                                  next[i] = { ...next[i], type: v };
                                  setFieldRows(next);
                                }}
                              >
                                <SelectTrigger className="h-8 w-24">
                                  <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                  {FIELD_TYPES.map((t) => (
                                    <SelectItem key={t} value={t}>{t}</SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            </TableCell>
                            <TableCell>
                              <Select
                                value={row.agg || NO_AGG_VALUE}
                                onValueChange={(v) => {
                                  const next = [...fieldRows];
                                  next[i] = { ...next[i], agg: v === NO_AGG_VALUE ? "" : v };
                                  setFieldRows(next);
                                }}
                              >
                                <SelectTrigger className="h-8 w-24">
                                  <SelectValue placeholder="—" />
                                </SelectTrigger>
                                <SelectContent>
                                  {AGG_METHODS.map((m) => (
                                    <SelectItem key={m || NO_AGG_VALUE} value={m || NO_AGG_VALUE}>{m || "—"}</SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            </TableCell>
                            <TableCell>
                              <Input
                                value={row.desc}
                                onChange={(e) => {
                                  const next = [...fieldRows];
                                  next[i] = { ...next[i], desc: e.target.value };
                                  setFieldRows(next);
                                }}
                                className="h-8 text-sm"
                                placeholder="Mô tả…"
                              />
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                </div>

                {/* Google Sheets config */}
                <details className="rounded-lg border bg-background p-4">
                  <summary className="font-semibold cursor-pointer hover:underline">
                    📥 Google Sheets Integration (Advanced)
                  </summary>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mt-3">
                    <div>
                      <Label className="text-xs">Sheet ID or URL</Label>
                      <Input
                        type="text"
                        value={gsheetId}
                        onChange={(e) => setGsheetId(e.target.value)}
                        placeholder="e.g., 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs"
                        className="h-9 text-sm"
                      />
                    </div>
                    <div>
                      <Label className="text-xs">Worksheet name</Label>
                      <Input
                        type="text"
                        value={gsheetWorksheet}
                        onChange={(e) => setGsheetWorksheet(e.target.value)}
                        placeholder="e.g., Sheet1"
                        className="h-9 text-sm"
                      />
                    </div>
                    <div>
                      <Label className="text-xs">Range (A1 notation)</Label>
                      <Input
                        type="text"
                        value={gsheetRange}
                        onChange={(e) => setGsheetRange(e.target.value)}
                        placeholder="e.g., A1:ZZZ or Sheet1!A1:C100"
                        className="h-9 text-sm"
                      />
                    </div>
                    <div>
                      <Label className="text-xs">Schema path (YAML)</Label>
                      <Input
                        type="text"
                        value={gsheetSchemaPath}
                        onChange={(e) => setGsheetSchemaPath(e.target.value)}
                        placeholder="/path/to/schema.yaml"
                        className="h-9 text-sm md:col-span-2"
                      />
                    </div>
                  </div>
                  <p className="text-xs text-muted-foreground mt-2">
                    Optional: Configure to enable "Ingest from Google Sheets" button in Jobs tab. Leave empty if not needed.
                  </p>
                </details>

                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => { setScanResult(null); setScanFile(null); setFieldRows([]); }}
                >
                  ← Quét lại
                </Button>
              </div>
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => { setCreateMode(null); setScanResult(null); setFieldRows([]); }}>
              Huỷ
            </Button>
            {scanResult && (
              <Button onClick={handleCreate} disabled={creating || !templateName.trim()}>
                {creating ? "Đang tạo…" : "✅ Tạo mẫu"}
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Attach Word Dialog */}
      <Dialog open={!!attachTarget} onOpenChange={(open) => !open && setAttachTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Gắn Word Template</DialogTitle>
            <DialogDescription>
              {attachTarget?.name} — chọn file .docx làm template xuất báo cáo
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label>File Word (.docx)</Label>
            <Input
              type="file"
              accept=".docx"
              onChange={(e) => setAttachFile(e.target.files?.[0] ?? null)}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAttachTarget(null)}>Huỷ</Button>
            <Button onClick={handleAttach} disabled={!attachFile || attaching}>
              {attaching ? "Đang upload…" : "📤 Upload & Gắn"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
