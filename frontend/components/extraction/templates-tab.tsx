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
import { formatDate, cn } from "@/lib/utils";
import type { Template, TemplateField, ScanWordResult, GoogleSheetWorksheetConfig } from "@/lib/types";
import { toast } from "sonner";

const FIELD_TYPES = ["string", "number", "boolean", "array"];
const AGG_METHODS = ["", "SUM", "AVG", "MAX", "MIN", "COUNT", "CONCAT", "LAST"];
const NO_AGG_VALUE = "__none";
const DEFAULT_GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1vfWhL4ZFRiwlrhjEAlCemE9sPlNHvuxFiT_1hA5NDYI/edit?usp=sharing";

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
  const [gsheetId, setGsheetId] = useState(DEFAULT_GOOGLE_SHEET_URL);
  const [aggregationGroup, setAggregationGroup] = useState("");
  // Multi-worksheet configs (new approach)
  const [worksheetConfigs, setWorksheetConfigs] = useState<GoogleSheetWorksheetConfig[]>([]);
  // Quick-add inputs
  const [newWsName, setNewWsName] = useState("");
  const [newSchemaPath, setNewSchemaPath] = useState("");
  const [newRange, setNewRange] = useState("A1:ZZZ");

  // Ingest state for templates list
  const [ingestingTplId, setIngestingTplId] = useState<string | null>(null);
  const [ingestProgress, setIngestProgress] = useState<Record<string, string>>({});

  // Attach word dialog
  const [attachTarget, setAttachTarget] = useState<Template | null>(null);
  const [attachFile, setAttachFile] = useState<File | null>(null);
  const [attaching, setAttaching] = useState(false);

  // Wizard step: 1=scan, 2=fields, 3=sheets, 4=review
  const [wizardStep, setWizardStep] = useState<1 | 2 | 3 | 4>(1);

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
    const res = await api.templates.scanWord(scanFile);
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
    setWizardStep(2); // Move to fields step
    toast.success(`Scan xong — phát hiện ${schemaFields.length} trường.`);
  }

  function goToStep(step: 1 | 2 | 3 | 4) {
    setWizardStep(step);
  }

  function resetWizard() {
    setWizardStep(1);
    setScanResult(null);
    setScanFile(null);
    setFieldRows([]);
    setTemplateName("");
    setGsheetId(DEFAULT_GOOGLE_SHEET_URL);
    setWorksheetConfigs([]);
    setAggregationGroup("");
  }

  // Helper for multi-worksheet config
  function addWorksheetConfig() {
    setWorksheetConfigs([...worksheetConfigs, { worksheet: "", schema_path: "", range: "A1:ZZZ" }]);
  }
  function removeWorksheetConfig(idx: number) {
    setWorksheetConfigs(worksheetConfigs.filter((_cfg: GoogleSheetWorksheetConfig, i: number) => i !== idx));
  }
  function updateWorksheetConfig(idx: number, field: keyof GoogleSheetWorksheetConfig, value: string) {
    setWorksheetConfigs(worksheetConfigs.map((cfg: GoogleSheetWorksheetConfig, i: number) =>
      i === idx ? { ...cfg, [field]: value } : cfg
    ));
  }

  function handleQuickAdd() {
    if (!newWsName.trim()) {
      toast.warning("Vui lòng nhập Worksheet name");
      return;
    }
    // Schema path có thể để trống tạm, user sẽ upload schema lên MinIO sau
    setWorksheetConfigs([...worksheetConfigs, {
      worksheet: newWsName.trim(),
      schema_path: newSchemaPath.trim() || `/app/app/domain/templates/sheet_mapping.yaml`,
      range: newRange.trim() || "A1:ZZZ"
    }]);
    setNewWsName("");
    setNewSchemaPath("");
    setNewRange("A1:ZZZ");
    toast.success(`Đã thêm worksheet "${newWsName.trim()}"`);
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

    // Use multi-worksheet configs if available
    const validConfigs = worksheetConfigs.filter((cfg: GoogleSheetWorksheetConfig) => cfg.worksheet.trim() && cfg.schema_path.trim());
    if (validConfigs.length > 0) {
      payload.google_sheet_configs = validConfigs.map(cfg => ({
        worksheet: cfg.worksheet.trim(),
        schema_path: cfg.schema_path.trim(),
        range: cfg.range.trim() || "A1:ZZZ"
      }));
    }

    if (aggregationGroup.trim()) payload.aggregation_group = aggregationGroup.trim();

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
      setGsheetId(DEFAULT_GOOGLE_SHEET_URL);
      setWorksheetConfigs([]);
      setAggregationGroup("");
      onRefresh();
    } else {
      toast.error(`Tạo thất bại: ${res.error}`);
    }
  }

  async function handleAttach() {
    if (!attachTarget || !attachFile) return;
    setAttaching(true);
    const scanRes = await api.templates.scanWord(attachFile);
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

  // Ingest from Google Sheets for a template in the list
  async function handleIngestTemplate(templateId: string) {
    const selectedTpl = templates.find(t => t.id === templateId);
    if (!selectedTpl?.google_sheet_id) {
      toast.warning("Template chưa được cấu hình Google Sheets (thiếu Sheet ID).");
      return;
    }
    if (!selectedTpl?.google_sheet_worksheet) {
      toast.warning("Template chưa được cấu hình Google Sheets (thiếu worksheet name).");
      return;
    }
    if (!selectedTpl?.google_sheet_schema_path) {
      toast.warning("Template chưa được cấu hình Google Sheets (thiếu schema path).");
      return;
    }

    setIngestingTplId(templateId);
    setIngestProgress((prev: Record<string, string>) => ({ ...prev, [templateId]: "Đang đưa vào hàng đợi…" }));

    const res = await api.jobs.ingestGoogleSheet({
      template_id: templateId,
    });

    if (!res.ok) {
      setIngestingTplId(null);
      setIngestProgress((prev: Record<string, string>) => ({ ...prev, [templateId]: "" }));
      toast.error(`Không thể đồng bộ sheet: ${res.error}`);
      return;
    }

    const batchId = res.data.batch_id || res.data.task_id;
    setIngestProgress((prev: Record<string, string>) => ({ ...prev, [templateId]: "Đang theo dõi tiến độ…" }));

    // Poll for completion
    const maxAttempts = 120;
    for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
      await new Promise(resolve => setTimeout(resolve, 2000));
      const statusRes = await api.jobs.getBatchStatus(batchId);
      if (!statusRes.ok) {
        setIngestProgress((prev: Record<string, string>) => ({ ...prev, [templateId]: "Lỗi đọc trạng thái" }));
        setIngestingTplId(null);
        return;
      }

      const payload = statusRes.data;
      const total = Number(payload.total || 0);
      const processed = Math.max(0, total - Number(payload.pending || 0) - Number(payload.processing || 0));
      setIngestProgress((prev: Record<string, string>) => ({ ...prev, [templateId]: `Đang chạy: ${processed}/${total || 1} (${payload.progress_percent}%)` }));

      if (Number(payload.progress_percent || 0) >= 100) {
        const inserted = Number(payload.ready_for_review || 0);
        const failed = Number(payload.failed || 0);
        if (failed > 0) {
          toast.warning(`Đồng bộ hoàn tất có lỗi: ${inserted} thành công, ${failed} lỗi.`);
        } else {
          toast.success(`✅ Đồng bộ xong: ${inserted} bản ghi.`);
        }
        setIngestProgress((prev: Record<string, string>) => ({ ...prev, [templateId]: `Hoàn tất: ${inserted} bản ghi` }));
        setIngestingTplId(null);
        onRefresh();
        return;
      }
    }
    toast.warning("Đồng bộ vẫn đang chạy, vui lòng kiểm tra lại sau.");
    setIngestProgress((prev: Record<string, string>) => ({ ...prev, [templateId]: "Đang chạy nền…" }));
    setIngestingTplId(null);
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
                      {tpl.aggregation_group && (
                        <Badge variant="outline" className="border-blue-500 text-blue-600">
                          🏷️ {tpl.aggregation_group}
                        </Badge>
                      )}
                      {tpl.google_sheet_id && (
                        <Badge variant="secondary">📊 Sheets</Badge>
                      )}
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
                      {/* Ingest from Google Sheets button - chỉ hiện nếu có config */}
                      {tpl.google_sheet_id && tpl.google_sheet_worksheet && tpl.google_sheet_schema_path && (
                        <div className="flex flex-col gap-1">
                          <Button
                            variant="secondary"
                            size="sm"
                            onClick={() => handleIngestTemplate(tpl.id)}
                            disabled={ingestingTplId === tpl.id}
                          >
                            {ingestingTplId === tpl.id ? (
                              "⏳ Đang đồng bộ…"
                            ) : (
                              "📥 Đồng bộ GG Sheets"
                            )}
                          </Button>
                          {ingestProgress[tpl.id] && (
                            <span className="text-xs text-muted-foreground ml-1">
                              {ingestProgress[tpl.id]}
                            </span>
                          )}
                        </div>
                      )}
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
            {/* Wizard Progress */}
            <div className="flex items-center justify-between mb-4">
              {[1, 2, 3, 4].map((step) => (
                <div key={step} className="flex items-center">
                  <div
                    className={cn(
                      "w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium",
                      wizardStep === step
                        ? "bg-primary text-primary-foreground"
                        : wizardStep > step
                        ? "bg-green-500 text-white"
                        : "bg-muted text-muted-foreground"
                    )}
                  >
                    {wizardStep > step ? "✓" : step}
                  </div>
                  {step < 4 && (
                    <div
                      className={cn(
                        "w-12 h-1 mx-1",
                        wizardStep > step ? "bg-green-500" : "bg-muted"
                      )}
                    />
                  )}
                </div>
              ))}
            </div>

            {/* Step 1: Upload */}
            {wizardStep === 1 && (
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
                    <Button onClick={handleScanWord} disabled={!scanFile || scanning}>
                      {scanning ? "Đang quét…" : "🔍 Scan"}
                    </Button>
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">
                    File Word phải chứa các trường dạng {"{{tên_trường}}"}
                  </p>
                </div>
              </div>
            )}

            {/* Step 2: Fields */}
            {wizardStep === 2 && scanResult && (
              <div className="space-y-4">
                <div className="bg-muted/30 p-3 rounded-md">
                  <h4 className="font-semibold mb-2">📊 Thống kê</h4>
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
                </div>

                <div>
                  <Label>Tên mẫu</Label>
                  <Input
                    value={templateName}
                    onChange={(e) => setTemplateName(e.target.value)}
                    placeholder="Nhập tên mẫu…"
                    className="mt-1.5"
                  />
                </div>

                <div>
                  <div className="flex items-center justify-between mb-2">
                    <Label>Tinh chỉnh cấu trúc</Label>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setFieldRows(fieldRows.map(r => ({ ...r, selected: true })))}
                    >
                      Chọn tất cả
                    </Button>
                  </div>
                  <div className="rounded-md border overflow-auto max-h-80">
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

                <div className="flex gap-2">
                  <Button variant="outline" onClick={() => goToStep(1)}>← Quét lại</Button>
                  <Button onClick={() => goToStep(3)} className="ml-auto">Tiếp →</Button>
                </div>
              </div>
            )}

            {/* Step 3: Google Sheets */}
            {wizardStep === 3 && (
              <div className="space-y-3">
                <Alert variant="info">
                  <AlertDescription>
                    Bỏ qua nếu không cần tích hợp Google Sheets. Chỉ cần thiết cho ingest tự động.
                  </AlertDescription>
                </Alert>
                <details className="rounded-lg border bg-background p-4">
                  <summary className="font-semibold cursor-pointer hover:underline">
                    🔧 Cấu hình Google Sheets Integration
                  </summary>
                  <div className="mt-3 space-y-3">
                    <div>
                      <Label className="text-xs">Sheet ID or URL</Label>
                      <Input
                        type="text"
                        value={gsheetId}
                        onChange={(e) => setGsheetId(e.target.value)}
                        placeholder="e.g., 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs"
                        className="h-9 text-sm"
                      />
                      <p className="text-xs text-muted-foreground mt-1">
                        Một Sheet ID có thể chứa nhiều worksheet. Thêm từng worksheet bên dưới.
                      </p>
                    </div>

                    <Alert variant="warning" className="bg-amber-50 border-amber-200">
                      <AlertDescription className="text-xs">
                        <strong>Lưu ý:</strong> Schema Path phải là S3 key của file YAML đã upload lên MinIO.
                        Sau khi tạo mẫu, vào tab <strong>Settings</strong> để upload Word template và Schema YAML.
                        Schema YAML sẽ được lưu tại: <code>word_templates/&lt;template-id&gt;/schema.yaml</code>
                      </AlertDescription>
                    </Alert>

                    {/* Multi-worksheet config table */}
                    <div className="rounded-md border overflow-auto">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead className="w-48">Worksheet name</TableHead>
                            <TableHead className="w-64">Schema path (YAML)</TableHead>
                            <TableHead className="w-32">Range (A1)</TableHead>
                            <TableHead className="w-16"></TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {worksheetConfigs.length === 0 ? (
                            <TableRow>
                              <TableCell colSpan={4} className="text-center text-muted-foreground py-4">
                                Chưa có worksheet nào. Nhập thông tin ở trên và nhấn "+" để thêm.
                              </TableCell>
                            </TableRow>
                          ) : (
                            worksheetConfigs.map((cfg, idx) => (
                              <TableRow key={idx}>
                                <TableCell>
                                  <Input
                                    type="text"
                                    value={cfg.worksheet}
                                    onChange={(e) => updateWorksheetConfig(idx, "worksheet", e.target.value)}
                                    placeholder="e.g., BC NGÀY"
                                    className="h-8 text-sm"
                                  />
                                </TableCell>
                                <TableCell>
                                  <Input
                                    type="text"
                                    value={cfg.schema_path}
                                    onChange={(e) => updateWorksheetConfig(idx, "schema_path", e.target.value)}
                                    placeholder="word_templates/.../schema.yaml"
                                    className="h-8 text-sm"
                                  />
                                </TableCell>
                                <TableCell>
                                  <Input
                                    type="text"
                                    value={cfg.range}
                                    onChange={(e) => updateWorksheetConfig(idx, "range", e.target.value)}
                                    placeholder="A1:ZZZ"
                                    className="h-8 text-sm"
                                  />
                                </TableCell>
                                <TableCell>
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => removeWorksheetConfig(idx)}
                                    className="h-8 w-8 p-0 text-destructive"
                                  >
                                    ✕
                                  </Button>
                                </TableCell>
                              </TableRow>
                            ))
                          )}
                        </TableBody>
                      </Table>
                    </div>

                    {/* Quick-add form for single worksheet */}
                    <div className="rounded-md border p-3 bg-muted/20">
                      <h5 className="text-sm font-semibold mb-2">Thêm Worksheet</h5>
                      <div className="grid grid-cols-12 gap-2 items-end">
                        <div className="col-span-4">
                          <Label className="text-xs">Tên Worksheet</Label>
                          <Input
                            type="text"
                            value={newWsName}
                            onChange={(e) => setNewWsName(e.target.value)}
                            placeholder="e.g., BC NGÀY"
                            className="h-8 text-sm"
                          />
                        </div>
                        <div className="col-span-5">
                          <Label className="text-xs">Schema Path (S3 key)</Label>
                          <Input
                            type="text"
                            value={newSchemaPath}
                            onChange={(e) => setNewSchemaPath(e.target.value)}
                            placeholder="word_templates/.../schema.yaml"
                            className="h-8 text-sm"
                          />
                        </div>
                        <div className="col-span-2">
                          <Label className="text-xs">Range</Label>
                          <Input
                            type="text"
                            value={newRange}
                            onChange={(e) => setNewRange(e.target.value)}
                            placeholder="A1:ZZZ"
                            className="h-8 text-sm"
                          />
                        </div>
                        <div className="col-span-1">
                          <Button
                            type="button"
                            size="sm"
                            className="h-8 w-full"
                            onClick={handleQuickAdd}
                          >
                            +
                          </Button>
                        </div>
                      </div>
                      <p className="text-xs text-muted-foreground mt-1.5">
                        Schema Path là S3 key của file YAML (upload lên MinIO). Ví dụ: <code>word_templates/&lt;template-id&gt;/schema.yaml</code>
                      </p>
                    </div>

                    <p className="text-xs text-muted-foreground mt-2">
                      Sau khi thêm, upload Schema YAML lên MinIO với key: <code>word_templates/&lt;template-id&gt;/schema.yaml</code>
                    </p>

                    <div className="md:col-span-2">
                      <Label className="text-xs">Aggregation Group (Optional)</Label>
                      <Input
                        type="text"
                        value={aggregationGroup}
                        onChange={(e) => setAggregationGroup(e.target.value)}
                        placeholder="e.g., daily_operational"
                        className="h-9 text-sm mt-1"
                      />
                      <p className="text-xs text-muted-foreground mt-1">
                        Templates with the same group name can be aggregated together in daily reports.
                      </p>
                    </div>
                  </div>
                  <p className="text-xs text-muted-foreground mt-2">
                    Optional: Configure to enable "Ingest from Google Sheets" button in Jobs tab.
                  </p>
                </details>

                <div className="flex gap-2">
                  <Button variant="outline" onClick={() => goToStep(2)}>← Quay lại</Button>
                  <Button onClick={() => goToStep(4)} className="ml-auto">Tiếp →</Button>
                </div>
              </div>
            )}

            {/* Step 4: Review */}
            {wizardStep === 4 && scanResult && (
              <div className="space-y-4">
                <div className="bg-muted/30 p-4 rounded-md">
                  <h4 className="font-semibold mb-2">📋 Tóm tắt mẫu</h4>
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    <div>
                      <span className="text-muted-foreground">Tên mẫu:</span>
                      <p className="font-medium">{templateName || "(chưa đặt)"}</p>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Số trường:</span>
                      <p className="font-medium">{fieldRows.filter(r => r.selected).length} được chọn</p>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Google Sheets:</span>
                      <p className="font-medium">
                        {gsheetId ? (
                          (worksheetConfigs as GoogleSheetWorksheetConfig[]).filter((cfg: GoogleSheetWorksheetConfig) => cfg.worksheet.trim() && cfg.schema_path.trim()).length > 0
                            ? `✅ Cấu hình (${worksheetConfigs.length} worksheet${worksheetConfigs.length > 1 ? 's' : ''})`
                            : "✅ Cấu hình (legacy)"
                        ) : "❌ Chưa cấu hình"}
                      </p>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Aggregation Group:</span>
                      <p className="font-medium">{aggregationGroup || "Không có"}</p>
                    </div>
                  </div>
                </div>

                <div>
                  <Label>Các trường đã chọn</Label>
                  <div className="mt-2 rounded-md border overflow-auto max-h-48">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Tên</TableHead>
                          <TableHead>Loại</TableHead>
                          <TableHead>Phương thức TH</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {fieldRows.filter(r => r.selected).map((row) => (
                          <TableRow key={row.name}>
                            <TableCell className="font-mono text-sm">{row.name}</TableCell>
                            <TableCell>{row.type}</TableCell>
                            <TableCell>{row.agg || "—"}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                </div>

                <div className="flex gap-2">
                  <Button variant="outline" onClick={() => goToStep(2)}>← Quay lại</Button>
                  <Button onClick={handleCreate} disabled={creating || !templateName.trim()} className="ml-auto">
                    {creating ? "Đang tạo…" : "✅ Tạo mẫu"}
                  </Button>
                </div>
              </div>
            )}
          </div>

          {/* Step navigation is handled within each step's content. Footer only has Cancel. */}
          <DialogFooter>
            <Button variant="outline" onClick={() => { setCreateMode(null); resetWizard(); }}>
              Huỷ
            </Button>
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
