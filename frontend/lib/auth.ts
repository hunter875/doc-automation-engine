import type { Tenant } from "./types";

const TOKEN_KEY = "doc_automation_token";
const USER_EMAIL_KEY = "doc_automation_user_email";
const TENANT_ID_KEY = "doc_automation_tenant_id";
const TENANT_LIST_KEY = "doc_automation_tenant_list";

function storage(): Storage | null {
  if (typeof window === "undefined") return null;
  return window.localStorage;
}

export function getToken(): string {
  return storage()?.getItem(TOKEN_KEY) ?? "";
}

export function setToken(token: string): void {
  storage()?.setItem(TOKEN_KEY, token);
}

export function getUserEmail(): string {
  return storage()?.getItem(USER_EMAIL_KEY) ?? "";
}

export function setUserEmail(email: string): void {
  storage()?.setItem(USER_EMAIL_KEY, email);
}

export function getTenantId(): string {
  return storage()?.getItem(TENANT_ID_KEY) ?? "";
}

export function setTenantId(tenantId: string): void {
  storage()?.setItem(TENANT_ID_KEY, tenantId);
}

export function getTenantList(): Tenant[] {
  const raw = storage()?.getItem(TENANT_LIST_KEY);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function setTenantList(tenants: Tenant[]): void {
  storage()?.setItem(TENANT_LIST_KEY, JSON.stringify(tenants));
}

export function clearAuth(): void {
  const s = storage();
  if (!s) return;
  s.removeItem(TOKEN_KEY);
  s.removeItem(USER_EMAIL_KEY);
  s.removeItem(TENANT_ID_KEY);
  s.removeItem(TENANT_LIST_KEY);
}
