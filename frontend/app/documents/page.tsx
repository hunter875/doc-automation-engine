"use client";

import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAuth } from "@/components/providers";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import type { Document } from "@/lib/types";
import Link from "next/link";

export default function DocumentsPage() {
  const { isLoggedIn, tenantId } = useAuth();
  const [docs, setDocs] = useState<Document[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function fetchDocs() {
    if (!tenantId) return;
    setLoading(true);
    setError("");
    const res = await api.documents.list(50);
    setLoading(false);
    if (res.ok) {
      const list = Array.isArray(res.data)
        ? res.data
        : (res.data as { items?: Document[]; total?: number }).items ?? [];
      const t = Array.isArray(res.data)
        ? list.length
        : (res.data as { total?: number }).total ?? list.length;
      setDocs(list);
      setTotal(t);
    } else {
      setError(res.error);
    }
  }

  useEffect(() => {
    if (isLoggedIn && tenantId) fetchDocs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoggedIn, tenantId]);

  if (!isLoggedIn) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold">📄 Tài liệu</h1>
        <Alert variant="warning">
          <AlertDescription>
            Hãy{" "}
            <Link href="/login" className="underline underline-offset-2">
              đăng nhập
            </Link>{" "}
            để xem tài liệu.
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">📄 Tài liệu</h1>
          {total > 0 && (
            <p className="text-sm text-muted-foreground mt-0.5">
              {total} tài liệu trong hệ thống
            </p>
          )}
        </div>
        <Button variant="outline" size="sm" onClick={fetchDocs} disabled={loading}>
          <RefreshCw className={`h-4 w-4 mr-2 ${loading ? "animate-spin" : ""}`} />
          Làm mới
        </Button>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>Không tải được danh sách: {error}</AlertDescription>
        </Alert>
      )}

      {!loading && docs.length === 0 && !error ? (
        <p className="text-sm text-muted-foreground">Chưa có tài liệu nào.</p>
      ) : (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Tên file</TableHead>
                <TableHead>Tags</TableHead>
                <TableHead>Tạo lúc</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {docs.map((doc) => {
                const fname = doc.filename ?? doc.file_name ?? "(no name)";
                return (
                  <TableRow key={doc.id}>
                    <TableCell className="font-medium">{fname}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {doc.tags || "—"}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {formatDate(doc.created_at)}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
