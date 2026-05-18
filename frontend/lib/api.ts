import { getTenantId, getToken } from "./auth";
import type {
  AggregationReport,
  CalendarDay,
  DashboardData,
  Document,
  ExtractionJob,
  ScanWordResult,
  Template,
  Tenant,
} from "./types";

export type ApiResult<T> =
  | { ok: true; data: T; status: number }
  | { ok: false; error: string; status: number };

type RequestOptions = Omit<RequestInit, "body" | "headers"> & {
  body?: BodyInit | Record<string, unknown> | null;
  headers?: HeadersInit;
  blob?: boolean;
};

function buildHeaders(body: RequestOptions["body"], extra?: HeadersInit): Headers {
  const headers = new Headers(extra);
  const token = getToken();
  const tenantId = getTenantId();

  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (tenantId) headers.set("X-Tenant-ID", tenantId);
  if (!(body instanceof FormData) && body !== undefined && body !== null) {
    headers.set("Content-Type", "application/json");
  }

  return headers;
}

function endpoint(path: string): string {
  return path.startsWith("/") ? path : `/${path}`;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<ApiResult<T>> {
  const { body, blob, ...rest } = options;
  const headers = buildHeaders(body, rest.headers);
  const payload =
    body instanceof FormData || body instanceof Blob || typeof body === "string" || body == null
      ? body ?? undefined
      : JSON.stringify(body);

  try {
    const res = await fetch(endpoint(path), {
      ...rest,
      headers,
      body: payload,
    });

    if (!res.ok) {
      return { ok: false, error: await readError(res), status: res.status };
    }

    if (blob) {
      return { ok: true, data: (await res.blob()) as T, status: res.status };
    }

    if (res.status === 204) {
      return { ok: true, data: undefined as T, status: res.status };
    }

    return { ok: true, data: (await res.json()) as T, status: res.status };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : String(error), status: 0 };
  }
}

async function readError(res: Response): Promise<string> {
  try {
    const payload = await res.json();
    const detail = payload?.detail ?? payload?.message ?? payload?.error;
    if (Array.isArray(detail)) return detail.map((item) => item?.msg ?? JSON.stringify(item)).join("; ");
    if (typeof detail === "string") return detail;
    if (detail) return JSON.stringify(detail);
    return JSON.stringify(payload);
  } catch {
    return `${res.status} ${res.statusText}`;
  }
}

export const api = {
  auth: {
    login: (body: { email: string; password: string }) =>
      request<{ access_token: string; token_type: string; expires_in: number }>("/api/v1/auth/login", {
        method: "POST",
        body,
      }),
    register: (body: { email: string; password: string; full_name?: string }) =>
      request("/api/v1/auth/register", { method: "POST", body }),
  },

  tenants: {
    list: () => request<Tenant[]>("/api/v1/tenants"),
    create: (body: { name: string; description?: string }) =>
      request<Tenant>("/api/v1/tenants", { method: "POST", body }),
  },

  documents: {
    list: (pageSize = 20) =>
      request<{ items: Document[]; total: number; page: number; page_size: number }>(
        `/api/v1/documents?page_size=${pageSize}`,
      ),
  },

  templates: {
    list: () => request<{ items: Template[]; total: number }>("/api/v1/extraction/templates"),
    create: (body: Record<string, unknown>) =>
      request<Template>("/api/v1/extraction/templates", { method: "POST", body }),
    patch: (id: string, body: Record<string, unknown>) =>
      request<Template>(`/api/v1/extraction/templates/${id}`, { method: "PATCH", body }),
    delete: (id: string) =>
      request<void>(`/api/v1/extraction/templates/${id}`, { method: "DELETE" }),
    scanWord: (body: FormData) =>
      request<ScanWordResult>("/api/v1/extraction/templates/scan-word", { method: "POST", body }),
  },

  jobs: {
    list: () => request<{ items: ExtractionJob[]; total: number }>("/api/v1/extraction/jobs"),
    get: (id: string) => request<ExtractionJob>(`/api/v1/extraction/jobs/${id}`),
    smartUpload: (body: FormData) =>
      request<{ batch_id: string; total_files: number; jobs: Array<{ job_id: string; file_name: string; status: string }> }>(
        "/api/v1/extraction/jobs/smart-upload",
        { method: "POST", body },
      ),
    retry: (id: string) =>
      request<ExtractionJob>(`/api/v1/extraction/jobs/${id}/retry`, { method: "POST" }),
    delete: (id: string) =>
      request<void>(`/api/v1/extraction/jobs/${id}`, { method: "DELETE" }),
    byDate: (month: number, year: number) =>
      request<CalendarDay[]>(`/api/v1/extraction/jobs/by-date?month=${month}&year=${year}`),
  },

  review: {
    approve: (id: string, body: { reviewed_data?: Record<string, unknown> | null; notes?: string | null }) =>
      request<ExtractionJob>(`/api/v1/extraction/review/${id}/approve`, { method: "POST", body }),
    reject: (id: string, body: { notes: string }) =>
      request<ExtractionJob>(`/api/v1/extraction/review/${id}/reject`, { method: "POST", body }),
  },

  reports: {
    list: () => request<{ items: AggregationReport[]; total: number }>("/api/v1/extraction/aggregate"),
    get: (id: string) => request<AggregationReport>(`/api/v1/extraction/aggregate/${id}`),
    create: (body: { template_id: string; job_ids: string[]; report_name: string; description?: string }) =>
      request<AggregationReport>("/api/v1/extraction/aggregate", { method: "POST", body }),
    createByDate: (body: { report_date: string; template_id?: string; report_name?: string; description?: string }) =>
      request<AggregationReport>("/api/v1/extraction/reports/create-by-date", { method: "POST", body }),
    delete: (id: string) =>
      request<void>(`/api/v1/extraction/aggregate/${id}`, { method: "DELETE" }),
    exportExcel: (id: string) =>
      request<Blob>(`/api/v1/extraction/aggregate/${id}/export?format=excel`, { blob: true }),
    exportWordAuto: (id: string) =>
      request<Blob>(`/api/v1/extraction/aggregate/${id}/export-word-auto`, { blob: true }),
    exportWordUpload: (id: string, body: FormData) =>
      request<Blob>(`/api/v1/extraction/aggregate/${id}/export-word`, { method: "POST", body, blob: true }),
  },

  dashboard: {
    get: () => request<DashboardData>("/api/v1/extraction/dashboard"),
  },
};
