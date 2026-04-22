"use client";

import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import {
  getToken, setToken, clearAuth,
  getTenantId, setTenantId,
  getUserEmail, setUserEmail,
  getTenantList, setTenantList,
} from "@/lib/auth";
import type { Tenant } from "@/lib/types";

interface AuthState {
  token: string;
  email: string;
  tenantId: string;
  tenantList: Tenant[];
  isLoggedIn: boolean;
}

interface AuthContextValue extends AuthState {
  login: (email: string, password: string) => Promise<string | null>;
  register: (email: string, password: string) => Promise<string | null>;
  logout: () => void;
  selectTenant: (id: string) => void;
  reloadTenants: () => Promise<void>;
  createTenant: (name: string) => Promise<string | null>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({
    token: "",
    email: "",
    tenantId: "",
    tenantList: [],
    isLoggedIn: false,
  });

  // Hydrate from localStorage on mount (client only)
  useEffect(() => {
    const token = getToken();
    const email = getUserEmail();
    const tenantId = getTenantId();
    const tenantList = getTenantList();
    if (token) {
      setState({ token, email, tenantId, tenantList, isLoggedIn: true });
    }
  }, []);

  const reloadTenants = useCallback(async () => {
    const res = await api.tenants.list();
    if (res.ok) {
      const list = Array.isArray(res.data)
        ? res.data
        : (res.data as { items?: Tenant[] }).items ?? [];
      setTenantList(list);
      setState((prev) => {
        const tid = prev.tenantId || (list[0]?.id ?? "");
        setTenantId(tid);
        return { ...prev, tenantList: list, tenantId: tid };
      });
    }
  }, []);

  const login = useCallback(async (email: string, password: string): Promise<string | null> => {
    const res = await api.auth.login({ email, password });
    if (!res.ok) return res.error;
    const token = res.data.access_token;
    setToken(token);
    setUserEmail(email);
    setState((prev) => ({ ...prev, token, email, isLoggedIn: true }));
    // Auto-load tenants
    const tres = await api.tenants.list();
    if (tres.ok) {
      const list = Array.isArray(tres.data)
        ? tres.data
        : (tres.data as { items?: Tenant[] }).items ?? [];
      setTenantList(list);
      const tid = list[0]?.id ?? "";
      setTenantId(tid);
      setState((prev) => ({ ...prev, tenantList: list, tenantId: tid }));
    }
    return null;
  }, []);

  const register = useCallback(async (email: string, password: string): Promise<string | null> => {
    const res = await api.auth.register({ email, password, full_name: email.split("@")[0] });
    if (!res.ok) return res.error;
    return null;
  }, []);

  const logout = useCallback(() => {
    clearAuth();
    setState({ token: "", email: "", tenantId: "", tenantList: [], isLoggedIn: false });
  }, []);

  const selectTenant = useCallback((id: string) => {
    setTenantId(id);
    setState((prev) => ({ ...prev, tenantId: id }));
  }, []);

  const createTenant = useCallback(async (name: string): Promise<string | null> => {
    const res = await api.tenants.create({ name });
    if (!res.ok) return res.error;
    const newTenant = res.data;
    setTenantId(newTenant.id);
    setState((prev) => {
      const list = [...prev.tenantList, newTenant];
      setTenantList(list);
      return { ...prev, tenantList: list, tenantId: newTenant.id };
    });
    return null;
  }, []);

  return (
    <AuthContext.Provider value={{ ...state, login, register, logout, selectTenant, reloadTenants, createTenant }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
