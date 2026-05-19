import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import type { ReactNode } from "react";

/**
 * Auth context — interim static-credential auth for MVP.
 *
 * The frontend calls POST /api/v1/auth/login with {username, password}.
 * The backend currently checks against a hardcoded admin/admin pair and
 * returns a fixed bearer token. Token persists in localStorage so the
 * session survives reloads.
 *
 * This module is the only place auth state lives; the rest of the app
 * imports `useAuth` and treats Clerk-replacement as a one-file swap later.
 */

const STORAGE_KEY = "lpb_auth_token";
const STORAGE_USER = "lpb_auth_user";

const API_BASE: string =
  (import.meta.env.VITE_API_URL as string | undefined) ?? "";

type AuthState = {
  token: string | null;
  username: string | null;
  isAuthed: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
};

const AuthCtx = createContext<AuthState | null>(null);

function readToken(): { token: string | null; username: string | null } {
  try {
    return {
      token: localStorage.getItem(STORAGE_KEY),
      username: localStorage.getItem(STORAGE_USER),
    };
  } catch {
    return { token: null, username: null };
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [{ token, username }, setState] = useState(readToken);

  useEffect(() => {
    const sync = () => setState(readToken());
    window.addEventListener("storage", sync);
    return () => window.removeEventListener("storage", sync);
  }, []);

  const login = useCallback(async (u: string, p: string) => {
    const res = await fetch(`${API_BASE}/api/v1/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: u, password: p }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: "Login failed" }));
      throw new Error(body.detail ?? "Login failed");
    }
    const data: { token: string } = await res.json();
    localStorage.setItem(STORAGE_KEY, data.token);
    localStorage.setItem(STORAGE_USER, u);
    setState({ token: data.token, username: u });
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem(STORAGE_USER);
    setState({ token: null, username: null });
  }, []);

  const value = useMemo<AuthState>(
    () => ({ token, username, isAuthed: !!token, login, logout }),
    [token, username, login, logout],
  );

  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthCtx);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

/** Convenience for the API client: returns Authorization header value or null. */
export function getAuthHeader(): string | null {
  const { token } = readToken();
  return token ? `Bearer ${token}` : null;
}
