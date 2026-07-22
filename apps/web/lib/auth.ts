"use client";

import { useEffect, useState } from "react";

export const AUTH_STORAGE_KEY = "bus-booking-auth-session";

type AuthUser = {
  id: string;
  full_name: string;
  email: string | null;
  is_platform_staff: boolean;
  office: { id: string; name: string } | null;
};

export type AuthSession = {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  session_id: string;
  landing_path: string;
  user: AuthUser;
};

export function storeAuthSession(session: AuthSession): void {
  localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(session));
  window.dispatchEvent(new Event("bus-booking-auth-changed"));
}

export function readAuthSession(): AuthSession | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(AUTH_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<AuthSession>;
    if (!parsed.access_token || !parsed.user || !parsed.landing_path) return null;
    return parsed as AuthSession;
  } catch {
    localStorage.removeItem(AUTH_STORAGE_KEY);
    return null;
  }
}

export function clearAuthSession(): void {
  localStorage.removeItem(AUTH_STORAGE_KEY);
  window.dispatchEvent(new Event("bus-booking-auth-changed"));
}

export function useStoredAccessToken(): [string, (token: string) => void] {
  const [token, setToken] = useState("");
  useEffect(() => {
    const refresh = () => setToken(readAuthSession()?.access_token ?? "");
    refresh();
    window.addEventListener("bus-booking-auth-changed", refresh);
    window.addEventListener("storage", refresh);
    return () => {
      window.removeEventListener("bus-booking-auth-changed", refresh);
      window.removeEventListener("storage", refresh);
    };
  }, []);
  return [token, setToken];
}

export function useAuthSession(): AuthSession | null {
  const [session, setSession] = useState<AuthSession | null>(null);
  useEffect(() => {
    const refresh = () => setSession(readAuthSession());
    refresh();
    window.addEventListener("bus-booking-auth-changed", refresh);
    window.addEventListener("storage", refresh);
    return () => {
      window.removeEventListener("bus-booking-auth-changed", refresh);
      window.removeEventListener("storage", refresh);
    };
  }, []);
  return session;
}
