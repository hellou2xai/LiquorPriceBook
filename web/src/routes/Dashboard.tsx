import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { insightsApi } from "../lib/api";
import { useAuth } from "../lib/auth";
import { money, pct, pctClass } from "../lib/fmt";
import type { MoverRow } from "../lib/api";

export default function Dashboard() {
  const { username } = useAuth();

  const moversQ = useQuery({
    queryKey: ["movers"],
    queryFn: () => insightsApi.movers({ limit: 15 }),
  });
  const wlMoversQ = useQuery({
    queryKey: ["watchlist-movers"],
    queryFn: () => insightsApi.watchlistMovers(),
  });
  const alertsQ = useQuery({
    queryKey: ["alerts", { dashboard: true }],
    queryFn: () => insightsApi.alerts({ limit: 10 }),
  });

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        <p className="text-sm text-zinc-600">
          Welcome{username ? `, ${username}` : ""}. Here's what moved in the current edition.
        </p>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <MoverPanel
          title="What moved this month"
          subtitle="Top absolute % changes in case cost vs the prior edition."
          rows={moversQ.data}
          loading={moversQ.isLoading}
          emptyHint="No prior edition yet. Movers will appear once a second book is ingested."
        />
        <MoverPanel
          title="Your watchlist movers"
          subtitle="Only the SKUs you're tracking."
          rows={wlMoversQ.data}
          loading={wlMoversQ.isLoading}
          emptyHint="Add products to your watchlist to see their movements here."
        />
      </div>

      <section className="rounded-lg border border-zinc-200 bg-white">
        <header className="border-b border-zinc-200 px-4 py-2 flex items-center justify-between">
          <h2 className="text-sm font-medium text-zinc-700">Recent alerts</h2>
          <Link to="/alerts" className="text-xs text-zinc-500 hover:text-zinc-900">
            See all →
          </Link>
        </header>
        <ul className="divide-y divide-zinc-100">
          {alertsQ.isLoading ? (
            <li className="px-4 py-3 text-sm text-zinc-500">Loading…</li>
          ) : (alertsQ.data ?? []).length === 0 ? (
            <li className="px-4 py-3 text-sm text-zinc-500">
              No alerts yet. They fire after each new edition is ingested.
            </li>
          ) : (
            alertsQ.data!.map((a) => (
              <li key={a.id} className="px-4 py-2 text-sm flex items-center gap-2">
                <span className="inline-flex items-center rounded-md border px-1.5 py-0.5 text-xs font-medium bg-zinc-50 border-zinc-200 text-zinc-700">
                  {a.rule_type}
                </span>
                {a.product_code ? (
                  <Link to={`/catalog/${a.product_code}`} className="font-mono text-xs hover:underline">
                    {a.product_code}
                  </Link>
                ) : null}
                <span className="text-zinc-600 flex-1 truncate">
                  {String((a.payload as any).description ?? "")}
                </span>
                <span className="text-xs text-zinc-500">
                  {new Date(a.fired_at).toLocaleString()}
                </span>
              </li>
            ))
          )}
        </ul>
      </section>
    </div>
  );
}

function MoverPanel({
  title,
  subtitle,
  rows,
  loading,
  emptyHint,
}: {
  title: string;
  subtitle: string;
  rows: MoverRow[] | undefined;
  loading: boolean;
  emptyHint: string;
}) {
  return (
    <section className="rounded-lg border border-zinc-200 bg-white">
      <header className="border-b border-zinc-200 px-4 py-2">
        <h2 className="text-sm font-medium text-zinc-700">{title}</h2>
        <p className="text-xs text-zinc-500">{subtitle}</p>
      </header>
      <ul className="divide-y divide-zinc-100">
        {loading ? (
          <li className="px-4 py-3 text-sm text-zinc-500">Loading…</li>
        ) : (rows ?? []).length === 0 ? (
          <li className="px-4 py-3 text-sm text-zinc-500">{emptyHint}</li>
        ) : (
          rows!.map((m) => (
            <li key={m.code} className="px-4 py-2 text-sm flex items-center gap-3">
              <Link to={`/catalog/${m.code}`} className="font-mono text-xs hover:underline">
                {m.code}
              </Link>
              <span className="flex-1 truncate">{m.description ?? "—"}</span>
              <span className="tabular-nums text-zinc-600">{money(m.case_cost)}</span>
              <span className={`tabular-nums w-16 text-right ${pctClass(m.case_cost_pct)}`}>
                {pct(m.case_cost_pct)}
              </span>
            </li>
          ))
        )}
      </ul>
    </section>
  );
}
