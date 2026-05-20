import { Link, useNavigate } from "react-router-dom";

import { useAuth } from "../lib/auth";

export default function Settings() {
  const { username, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="space-y-8 max-w-4xl">
      <div>
        <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-brand-navy">Settings</h1>
        <p className="text-sm text-zinc-500 mt-1">Account and app preferences.</p>
      </div>

      {/* Account section */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-500">Account</h2>
        <div className="bg-white rounded-xl shadow-sm border border-zinc-200/80 p-4 space-y-3">
          <div className="text-zinc-700">
            Signed in as <span className="font-medium text-brand-navy">{username ?? "—"}</span>
          </div>
          <button
            type="button"
            onClick={() => {
              logout();
              navigate("/login", { replace: true });
            }}
            className="rounded-lg border border-zinc-300 bg-brand-tan text-brand-navy px-3 py-1.5 text-sm font-medium hover:bg-zinc-200 transition-colors"
          >
            Sign out
          </button>
        </div>
      </section>

      {/* Quick links */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-500">Manage</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Link
            to="/sales-reps"
            className="rounded-xl border border-zinc-200/80 bg-white shadow-sm p-4 hover:border-brand-orange hover:shadow-md transition-all group"
          >
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-lg bg-brand-orange/10 flex items-center justify-center">
                <svg className="h-5 w-5 text-brand-orange" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
                </svg>
              </div>
              <div>
                <div className="text-sm font-medium text-brand-navy group-hover:text-brand-orange">Sales Representatives</div>
                <div className="text-xs text-zinc-500">Manage distributor contacts by division</div>
              </div>
            </div>
          </Link>
          <Link
            to="/alerts"
            className="rounded-xl border border-zinc-200/80 bg-white shadow-sm p-4 hover:border-brand-orange hover:shadow-md transition-all group"
          >
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-lg bg-brand-navy/10 flex items-center justify-center">
                <svg className="h-5 w-5 text-brand-navy" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
                </svg>
              </div>
              <div>
                <div className="text-sm font-medium text-brand-navy group-hover:text-brand-orange">Alert Preferences</div>
                <div className="text-xs text-zinc-500">Price drops, new RIPs, closeout notifications</div>
              </div>
            </div>
          </Link>
        </div>
      </section>

      {/* App info */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-500">About</h2>
        <div className="bg-white rounded-xl shadow-sm border border-zinc-200/80 p-4 text-sm text-zinc-600 space-y-1">
          <div>CELR Liquor Price Book v0.1</div>
          <div className="text-xs text-zinc-400">Built for NJ liquor retailers · Powered by U2xAI</div>
        </div>
      </section>
    </div>
  );
}
