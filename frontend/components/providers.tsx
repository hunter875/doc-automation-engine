"use client";

import React, { createContext, useContext, useEffect, useState, useCallback, ReactNode } from "react";
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

export function AuthProvider({ children }: { children: ReactNode }) {
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
      setState({ token, email: email || "", tenantId: tenantId || "", tenantList, isLoggedIn: true });
    }
  }, []);

  useEffect(() => {
    if (state.token) {
      setToken(state.token);
    }
  }, [state.token]);

  const extractAccessToken = (payload: any): string => {
    const token = payload?.access_token ?? payload?.token ?? payload?.data?.access_token ?? payload?.data?.token;
    return typeof token === "string" ? token : "";
  };

  const reloadTenants = useCallback(async () => {
    const res = await api.tenants.list();
    if (res.ok && res.data) {
      const list = Array.isArray(res.data) ? res.data : [];
      const tid = list[0]?.id ?? "";
      setTenantId(tid);
      setTenantList(list);
      setState((prev: AuthState) => ({ ...prev, tenantList: list, tenantId: tid }));
    }
  }, []);

  const login = useCallback(async (email: string, password: string): Promise<string | null> => {
    const res = await api.auth.login({ email, password });
    if (!res.ok) return res.error || "Login failed";
    const token = extractAccessToken(res.data);
    if (!token) return "Invalid response from server";
    setToken(token);
    setUserEmail(email);
    // Auto-load tenants
    const tres = await api.tenants.list();
    if (tres.ok && tres.data && tres.data.length > 0) {
      const list = tres.data;
      setTenantList(list);
      const tid = list[0].id;
      setTenantId(tid);
      setState((prev: AuthState) => ({ ...prev, token, email, isLoggedIn: true, tenantList: list, tenantId: tid }));
    } else {
      // No tenants - keep tenantId empty but still logged in
      setTenantList([]);
      setState((prev: AuthState) => ({ ...prev, token, email, isLoggedIn: true, tenantList: [], tenantId: "" }));
    }
    return null;
  }, []);

  const register = useCallback(async (email: string, password: string): Promise<string | null> => {
    const res = await api.auth.register({ email, password, full_name: email.split("@")[0] });
    if (!res.ok) return res.error || "Registration failed";
    return null;
  }, []);

  const logout = useCallback(() => {
    clearAuth();
    setState({ token: "", email: "", tenantId: "", tenantList: [], isLoggedIn: false });
  }, []);

  const selectTenant = useCallback((id: string) => {
    setTenantId(id);
    setState((prev: AuthState) => ({ ...prev, tenantId: id }));
  }, []);

  const createTenant = useCallback(async (name: string): Promise<string | null> => {
    const res = await api.tenants.create({ name });
    if (!res.ok) return res.error || "Failed to create tenant";
    const newTenant = res.data;
    if (!newTenant?.id) return "Invalid response from server";
    setTenantId(newTenant.id);
    setState((prev: AuthState) => {
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
