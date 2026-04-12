"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  FileText, RefreshCw, Clock, CheckCircle2,
  BarChart3, AlertTriangle, Settings2, TrendingUp,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAuth } from "@/components/providers";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import type { DashboardData } from "@/lib/types";

interface MetricCardProps {
  title: string;
  value: number | string;
  icon: React.ReactNode;
  description?: string;
  highlight?: boolean;
}

function MetricCard({ title, value, icon, description, highlight }: MetricCardProps) {
  return (
    <Card className={highlight ? "border-primary/50 bg-primary/5" : ""}>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{title}</CardTitle>
        <span className="text-muted-foreground">{icon}</span>
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
        {description && <p className="text-xs text-muted-foreground mt-1">{description}</p>}
      </CardContent>
    </Card>
  );
}

export default function DashboardPage() {
  const { isLoggedIn, tenantId } = useAuth();
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function fetchDashboard() {
    if (!tenantId) return;
    setLoading(true);
    setError("");
    const res = await api.dashboard.get();
    setLoading(false);
    if (res.ok) {
      setData(res.data);
    } else {
      setError(res.error);
    }
  }

  useEffect(() => {
    if (isLoggedIn && tenantId) fetchDashboard();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoggedIn, tenantId]);

  if (!isLoggedIn) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">📄 Doc Automation Engine</h1>
        <div className="grid gap-4 md:grid-cols-3">
          {[
            { title: "Engine 2 — Trích xuất dữ liệu", desc: "Trích xuất thông tin từ hóa đơn, báo cáo, hợp đồng… theo mẫu định nghĩa sẵn.", href: "/extraction", icon: <Settings2 className="h-8 w-8 text-primary" /> },
            { title: "Tài liệu", desc: "Xem và quản lý tài liệu đã upload lên hệ thống.", href: "/documents", icon: <FileText className="h-8 w-8 text-primary" /> },
            { title: "Báo cáo tổng hợp", desc: "Gom nhiều hồ sơ đã duyệt, tổng hợp tự động và xuất Excel / Word.", href: "/extraction?tab=export", icon: <BarChart3 className="h-8 w-8 text-primary" /> },
          ].map((item) => (
            <Card key={item.href} className="hover:shadow-md transition-shadow">
              <CardHeader>
                {item.icon}
                <CardTitle className="text-lg">{item.title}</CardTitle>
                <CardDescription>{item.desc}</CardDescription>
              </CardHeader>
              <CardContent>
                <Link href="/login">
                  <Button variant="outline" size="sm">Đăng nhập để sử dụng →</Button>
                </Link>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  const jobs = data?.jobs_by_status ?? {};
  const awaiting = jobs.awaiting_review ?? jobs.ready_for_review ?? 0;
  const approved = (jobs.approved ?? 0) + (jobs.aggregated ?? 0);
  const processing = (jobs.processing ?? 0) + (jobs.pending ?? 0) + (jobs.enriching ?? 0) + (jobs.extracted ?? 0);
  const failed = jobs.failed ?? 0;
  const total = jobs.total ?? 0;
  const recentReports = data?.recent_reports ?? [];
  const newReports = recentReports.filter((r) => r.status !== "finalized");

  const progressPct = total > 0 ? Math.round((approved / total) * 100) : 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <Button variant="outline" size="sm" onClick={fetchDashboard} disabled={loading}>
          <RefreshCw className={`h-4 w-4 mr-2 ${loading ? "animate-spin" : ""}`} />
          Làm mới
        </Button>
      </div>

      {/* Notifications */}
      {newReports.length > 0 && (
        <Alert variant="success">
          <BarChart3 className="h-4 w-4" />
          <AlertDescription>
            <strong>Báo cáo mới sẵn sàng:</strong> {newReports[0].name} ({newReports[0].total_jobs} hồ sơ) —{" "}
            <Link href="/extraction?tab=export" className="underline underline-offset-2">
              Tải về tại đây
            </Link>
          </AlertDescription>
        </Alert>
      )}
      {awaiting > 0 && (
        <Alert variant="warning">
          <Clock className="h-4 w-4" />
          <AlertDescription>
            <strong>{awaiting} hồ sơ</strong> đang chờ duyệt —{" "}
            <Link href="/extraction?tab=review" className="underline underline-offset-2">
              Duyệt ngay
            </Link>
          </AlertDescription>
        </Alert>
      )}

      {error && (
        <Alert variant="destructive">
          <AlertDescription>Không tải được dữ liệu: {error}</AlertDescription>
        </Alert>
      )}

      {/* 6 Metric cards */}
      <div className="grid gap-4 md:grid-cols-3 lg:grid-cols-6">
        <MetricCard title="Tài liệu" value={data?.total_documents ?? "—"} icon={<FileText className="h-4 w-4" />} />
        <MetricCard title="Đang xử lý" value={processing} icon={<RefreshCw className="h-4 w-4" />} />
        <MetricCard title="Chờ duyệt" value={awaiting} icon={<Clock className="h-4 w-4" />} highlight={awaiting > 0} />
        <MetricCard title="Đã duyệt" value={approved} icon={<CheckCircle2 className="h-4 w-4" />} />
        <MetricCard title="Báo cáo" value={data?.reports_count ?? "—"} icon={<BarChart3 className="h-4 w-4" />} />
        <MetricCard
          title="TB xử lý"
          value={data?.avg_processing_minutes ? `${data.avg_processing_minutes} ph` : "—"}
          icon={<TrendingUp className="h-4 w-4" />}
        />
      </div>

      {/* Pipeline funnel */}
      {data && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Tổng quan pipeline</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-5 gap-4 text-center">
              {[
                { label: "Tổng hồ sơ", value: total, color: "text-foreground" },
                { label: "Đang xử lý", value: processing, color: "text-blue-600" },
                { label: "Chờ duyệt", value: awaiting, color: "text-amber-600" },
                { label: "Đã duyệt", value: approved, color: "text-green-600" },
                { label: "Cần xem lại", value: failed, color: "text-red-600" },
              ].map(({ label, value, color }) => (
                <div key={label}>
                  <div className={`text-2xl font-bold ${color}`}>{value}</div>
                  <div className="text-xs text-muted-foreground">{label}</div>
                </div>
              ))}
            </div>
            {total > 0 && (
              <div className="space-y-1">
                <Progress value={progressPct} className="h-2" />
                <p className="text-xs text-muted-foreground text-right">
                  Tỷ lệ hoàn thành: {approved}/{total} ({progressPct}%) · Tỷ lệ duyệt: {data.approval_rate}%
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Recent reports */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">Báo cáo gần đây</CardTitle>
          <Link href="/extraction?tab=export">
            <Button variant="ghost" size="sm">Xem tất cả →</Button>
          </Link>
        </CardHeader>
        <CardContent>
          {recentReports.length === 0 ? (
            <p className="text-sm text-muted-foreground">Chưa có báo cáo nào.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Tên báo cáo</TableHead>
                  <TableHead>Số hồ sơ</TableHead>
                  <TableHead>Tạo lúc</TableHead>
                  <TableHead>Trạng thái</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {recentReports.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell className="font-medium">{r.name}</TableCell>
                    <TableCell>{r.total_jobs}</TableCell>
                    <TableCell>{formatDate(r.created_at)}</TableCell>
                    <TableCell>
                      <Badge variant={r.status === "finalized" ? "success" : "info"}>
                        {r.status === "finalized" ? "✅ Đã hoàn tất" : "📊 Sẵn sàng"}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Quick nav */}
      <div className="grid gap-3 md:grid-cols-2">
        <Link href="/extraction">
          <Card className="cursor-pointer hover:shadow-md transition-shadow">
            <CardContent className="flex items-center gap-3 pt-4 pb-4">
              <Settings2 className="h-8 w-8 text-primary" />
              <div>
                <div className="font-semibold">⚙️ Trích xuất dữ liệu</div>
                <div className="text-sm text-muted-foreground">Quản lý mẫu, hồ sơ và duyệt kết quả</div>
              </div>
            </CardContent>
          </Card>
        </Link>
        <Link href="/documents">
          <Card className="cursor-pointer hover:shadow-md transition-shadow">
            <CardContent className="flex items-center gap-3 pt-4 pb-4">
              <FileText className="h-8 w-8 text-primary" />
              <div>
                <div className="font-semibold">📄 Tài liệu</div>
                <div className="text-sm text-muted-foreground">Xem và quản lý tài liệu đã upload</div>
              </div>
            </CardContent>
          </Card>
        </Link>
      </div>
    </div>
  );
}
