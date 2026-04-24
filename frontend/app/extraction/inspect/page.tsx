"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { SheetInspector } from "@/components/extraction/sheet-inspector";
import { useAuth } from "@/components/providers";
import Link from "next/link";
import { Button } from "@/components/ui/button";

function InspectContent() {
  const { isLoggedIn, tenantId } = useAuth();
  const searchParams = useSearchParams();

  const month = parseInt(searchParams.get("month") ?? String(new Date().getMonth() + 1), 10);
  const year = parseInt(searchParams.get("year") ?? String(new Date().getFullYear()), 10);
  const documentId = searchParams.get("document_id") ?? undefined;
  const sheet = searchParams.get("sheet") ?? "BC NGÀY";

  if (!isLoggedIn) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold">🔍 Sheet Inspector</h1>
        <Alert variant="warning">
          <AlertDescription>
            Bạn cần{" "}
            <Link href="/login" className="underline underline-offset-2">
              đăng nhập
            </Link>{" "}
            để sử dụng tính năng này.
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  if (!tenantId) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold">🔍 Sheet Inspector</h1>
        <Alert variant="warning">
          <AlertDescription>
            Hãy chọn hoặc tạo <strong>tổ chức</strong> ở thanh bên trái để tiếp tục.
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold">🔍 Sheet Inspector</h1>
          <span className="text-sm text-muted-foreground">
            · <span className="font-medium">{sheet}</span>
            {documentId && (
              <span className="ml-1 text-xs font-mono text-muted-foreground">
                doc={documentId.slice(0, 8)}…
              </span>
            )}
          </span>
        </div>
        <Button variant="outline" size="sm" asChild>
          <Link href="/extraction">← Quay lại Trích xuất</Link>
        </Button>
      </div>

      <SheetInspector month={month} year={year} documentId={documentId} />
    </div>
  );
}

export default function InspectPage() {
  return (
    <Suspense>
      <InspectContent />
    </Suspense>
  );
}