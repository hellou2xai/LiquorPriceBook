import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../lib/auth";

type LocationState = { from?: { pathname: string } } | undefined;

export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as LocationState)?.from?.pathname ?? "/";
  const { login } = useAuth();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(username, password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-brand-gradient flex items-center justify-center">
      <div className="min-h-[80vh] flex items-center justify-center w-full">
        <form
          onSubmit={onSubmit}
          className="w-full max-w-sm bg-white rounded-2xl p-8 shadow-2xl"
        >
          <div className="flex items-center gap-3 mb-5">
            <div className="h-10 w-10 rounded-xl bg-brand-gradient-warm flex items-center justify-center shadow-md">
              <span className="text-white font-bold text-lg">C</span>
            </div>
            <div>
              <h1 className="text-xl font-semibold tracking-tight text-brand-navy">Sign in</h1>
              <p className="text-sm text-zinc-500">CELR Liquor Price Book</p>
            </div>
          </div>

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-brand-navy">
                Username
              </label>
              <input
                type="text"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="mt-1 block w-full rounded-md border border-zinc-200 px-3 py-2 text-sm focus:border-brand-orange focus:ring-1 focus:ring-brand-orange/30 focus:outline-none"
                placeholder="admin"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-brand-navy">
                Password
              </label>
              <input
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="mt-1 block w-full rounded-md border border-zinc-200 px-3 py-2 text-sm focus:border-brand-orange focus:ring-1 focus:ring-brand-orange/30 focus:outline-none"
                placeholder="admin"
                required
              />
            </div>

            {error ? (
              <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
                {error}
              </div>
            ) : null}

            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-lg bg-brand-orange px-3 py-2.5 text-sm font-medium text-white hover:bg-brand-orange-dark disabled:opacity-60 transition-colors shadow-sm"
            >
              {busy ? "Signing in…" : "Sign in"}
            </button>
          </div>

          <p className="mt-4 text-xs text-zinc-500">
            Default credentials: admin / admin. Real auth (Clerk) lands in a later release.
          </p>
        </form>
      </div>
    </div>
  );
}
