"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { TemplatesTab } from "@/components/extraction/templates-tab";
import { JobsTab } from "@/components/extraction/jobs-tab";
import { ReviewTab } from "@/components/extraction/review-tab";
import { ExportTab } from "@/components/extraction/export-tab";
import { useAuth } from "@/components/providers";
import { api } from "@/lib/api";
import type { Template, ExtractionJob } from "@/lib/types";
import Link from "next/link";
import { Button } from "@/components/ui/button";

function ExtractionContent() {
  const { isLoggedIn, tenantId } = useAuth();
  const searchParams = useSearchParams();
  const defaultTab = searchParams.get("tab") ?? "templates";

  const [templates, setTemplates] = useState<Template[]>([]);
  const [loadingTemplates, setLoadingTemplates] = useState(false);

  const [jobs, setJobs] = useState<ExtractionJob[]>([]);
  const [loadingJobs, setLoadingJobs] = useState(false);

  async function fetchTemplates() {
    if (!tenantId) return;
    setLoadingTemplates(true);
    const res = await api.templates.list();
    setLoadingTemplates(false);
    if (res.ok) {
      const list = Array.isArray(res.data)
        ? res.data
        : (res.data as { items?: Template[] }).items ?? [];
      setTemplates(list);
    }
  }

  async function fetchJobs() {
    if (!tenantId) return;
    setLoadingJobs(true);
    const res = await api.jobs.list();
    setLoadingJobs(false);
    if (res.ok) {
      const list = Array.isArray(res.data)
        ? res.data
        : (res.data as { items?: ExtractionJob[] }).items ?? [];
      setJobs(list);
    }
  }

  useEffect(() => {
    if (isLoggedIn && tenantId) {
      fetchTemplates();
      fetchJobs();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoggedIn, tenantId]);

  if (!isLoggedIn) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold">⚙️ Trích xuất dữ liệu</h1>
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
        <h1 className="text-2xl font-bold">⚙️ Trích xuất dữ liệu</h1>
        <Alert variant="warning">
          <AlertDescription>
            Hãy chọn hoặc tạo <strong>tổ chức</strong> ở thanh bên trái để tiếp tục.
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  const validTabs = ["templates", "jobs", "review", "export"];
  const initialTab = validTabs.includes(defaultTab) ? defaultTab : "templates";

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">⚙️ Engine 2 — Trích xuất dữ liệu</h1>

      <Tabs defaultValue={initialTab}>
        <TabsList className="grid grid-cols-4 w-full max-w-xl">
          <TabsTrigger value="templates">⚙️ Mẫu</TabsTrigger>
          <TabsTrigger value="jobs">📤 Hồ sơ</TabsTrigger>
          <TabsTrigger value="review">🔍 Duyệt</TabsTrigger>
          <TabsTrigger value="export">📊 Báo cáo</TabsTrigger>
        </TabsList>

        <TabsContent value="templates" className="mt-4">
          <TemplatesTab
            templates={templates}
            onRefresh={fetchTemplates}
            loading={loadingTemplates}
          />
        </TabsContent>

        <TabsContent value="jobs" className="mt-4">
          <JobsTab
            templates={templates}
            jobs={jobs}
            onRefreshJobs={fetchJobs}
            loadingJobs={loadingJobs}
          />
        </TabsContent>

        <TabsContent value="review" className="mt-4">
          <ReviewTab
            templates={templates}
            jobs={jobs}
            onRefreshJobs={fetchJobs}
            loadingJobs={loadingJobs}
          />
        </TabsContent>

        <TabsContent value="export" className="mt-4">
          <ExportTab templates={templates} jobs={jobs} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

export default function ExtractionPage() {
  return (
    <Suspense>
      <ExtractionContent />
    </Suspense>
  );
}
