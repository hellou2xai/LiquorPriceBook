import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { insightsApi } from "../lib/api";
import { useAuth } from "../lib/auth";
import { money, pct, pctClass } from "../lib/fmt";
import type { MoverRow } from "../lib/api";

function KpiCard({ label, value, sub, accent }: { label: string; value: string | number; sub?: string; accent?: "emerald" | "red" | "amber" | "sky" }) {
  const border = accent ? `border-${accent}-200` : "border-zinc-200";
  const bg = accent ? `bg-${accent}-50` : "bg-white";
  const labelColor = accent ? `text-${accent}-600` : "text-zinc-500";
  const valueColor = accent ? `text-${accent}-800` : "text-zinc-900";
  return (
    <div className={`rounded-lg border ${border} ${bg} px-4 py-3`}>
      <div className={`text-xs font-medium ${labelColor}`}>{label}</div>
      <div className={`text-xl font-bold ${valueColor} tabular-nums mt-0.5`}>{value}</div>
      {sub && <div className="text-[10px] text-zinc-400 mt-0.5">{sub}</div>}
    </div>
  );
}

function MoverPanel({ title, subtitle, rows, loading, emptyHint, limit = 10 }: {
  title: string; subtitle: string; rows: MoverRow[] | undefined; loading: boolean; emptyHint: string; limit?: number;
}) {
  const displayed = (rows ?? []).slice(0, limit);
  return (
    <section className="rounded-lg border border-zinc-200 bg-white">
      <header className="border-b border-zinc-200 px-4 py-2">
        <h2 className="text-sm font-medium text-zinc-700">{title}</h2>
        <p className="text-xs text-zinc-500">{subtitle}</p>
      </header>
      <ul className="divide-y divide-zinc-100">
        {loading ? (
          <li className="px-4 py-3 text-sm text-zinc-500">Loading...</li>
        ) : displayed.length === 0 ? (
          <li className="px-4 py-3 text-sm text-zinc-500">{emptyHint}</li>
        ) : (
          displayed.map((m) => {
            const change = parseFloat(String(m.case_cost_pct ?? "0"));
            return (
              <li key={m.code} className="px-4 py-2 text-sm flex items-center gap-3 hover:bg-zinc-50">
                <span className={`w-5 text-center ${change < 0 ? "text-emerald-600" : change > 0 ? "text-red-500" : "text-zinc-400"}`}>
                  {change < 0 ? "\u2193" : change > 0 ? "\u2191" : "\u2192"}
                </span>
                <Link to={`/catalog/${m.code}`} className="font-mono text-xs hover:underline w-20 shrink-0">{m.code}</Link>
                <span className="flex-1 truncate text-zinc-700">{m.description ?? "\u2014"}</span>
                <span className="tabular-nums text-zinc-600 w-20 text-right">{money(m.case_cost)}</span>
                <span className={`tabular-nums w-16 text-right font-medium ${pctClass(m.case_cost_pct)}`}>{pct(m.case_cost_pct)}</span>
              </li>
            );
          })
        )}
      </ul>
    </section>
  );
}

export default function Dashboard() {
  const { username } = useAuth();

  const summaryQ = useQuery({
    queryKey: ["dashboard-summary"],
    queryFn: () => insightsApi.summary(),
    staleTime: 60_000,
  });

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

  const ripsQ = useQuery({
    queryKey: ["rips-top", { limit: 5 }],
    queryFn: () => insightsApi.rips({ limit: 5 }),
  });

  const closeoutsQ = useQuery({
    queryKey: ["closeouts-top"],
    queryFn: () => insightsApi.closeouts({ limit: 5 }),
  });

  const s = summaryQ.data;

  // Price movers split
  const priceDrops = (moversQ.data ?? []).filter((m) => parseFloat(String(m.case_cost_pct ?? "0")) < 0).slice(0, 8);
  const priceIncreases = (moversQ.data ?? []).filter((m) => parseFloat(String(m.case_cost_pct ?? "0")) > 0).slice(0, 8);

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        <p className="text-sm text-zinc-600">
          Welcome{username ? `, ${username}` : ""}.
          {s ? ` ${s.edition_label} edition loaded.` : " Loading..."}
        </p>
      </header>

      {/* KPI Cards */}
      {s && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
          <KpiCard label="Total Products" value={s.total_products.toLocaleString()} sub={s.edition_label} />
          <KpiCard label="Active RIPs" value={s.total_rips} accent="emerald" sub={`${money(s.rip_total_potential_savings)} savings pool`} />
          <KpiCard label="Closeouts" value={s.total_closeouts} accent="amber" sub="last chance items" />
          <KpiCard label="Price Drops" value={s.products_price_down} accent="emerald" sub="vs last month" />
          <KpiCard label="Price Increases" value={s.products_price_up} accent="red" sub="vs last month" />
          <KpiCard label="Your Watchlist" value={s.watchlist_count} accent="sky"
            sub={s.watchlist_buy_now > 0 ? `${s.watchlist_buy_now} buy-now signals!` : "items tracked"} />
        </div>
      )}

      {/* Buy-now alert banner */}
      {s && s.watchlist_buy_now > 0 && (
        <div className="rounded-lg border border-emerald-300 bg-emerald-50 px-4 py-3 flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-emerald-800">
              {s.watchlist_buy_now} watchlist item{s.watchlist_buy_now > 1 ? "s" : ""} have BUY NOW signals
            </p>
            <p className="text-xs text-emerald-600 mt-0.5">These products are at favorable pricing — act before the next edition.</p>
          </div>
          <Link to="/watchlist" className="rounded-md bg-emerald-700 px-3 py-1.5 text-xs text-white font-medium hover:bg-emerald-800">
            View Order List
          </Link>
        </div>
      )}

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Price Drops */}
        <MoverPanel
          title="Biggest Price Drops"
          subtitle="Products with largest case cost decreases this month."
          rows={priceDrops}
          loading={moversQ.isLoading}
          emptyHint="No price drops this month."
        />

        {/* Your Watchlist Movers */}
        <MoverPanel
          title="Your Watchlist Movers"
          subtitle="Price changes on your tracked products."
          rows={wlMoversQ.data}
          loading={wlMoversQ.isLoading}
          emptyHint="Star products to track their price movements."
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Top RIP Opportunities */}
        <section className="rounded-lg border border-zinc-200 bg-white">
          <header className="border-b border-zinc-200 px-4 py-2 flex items-center justify-between">
            <div>
              <h2 className="text-sm font-medium text-zinc-700">Top RIP Opportunities</h2>
              <p className="text-xs text-zinc-500">Best savings % on retail incentive programs.</p>
            </div>
            <Link to="/rips" className="text-xs text-zinc-500 hover:text-zinc-900">See all →</Link>
          </header>
          <ul className="divide-y divide-zinc-100">
            {ripsQ.isLoading ? (
              <li className="px-4 py-3 text-sm text-zinc-500">Loading...</li>
            ) : (ripsQ.data ?? []).length === 0 ? (
              <li className="px-4 py-3 text-sm text-zinc-500">No RIPs in current edition.</li>
            ) : (
              ripsQ.data!.slice(0, 5).map((r, i) => (
                <li key={`${r.code}-${i}`} className="px-4 py-2 text-sm flex items-center gap-3 hover:bg-zinc-50">
                  <Link to={`/catalog/${r.code}`} className="font-mono text-xs hover:underline w-20 shrink-0">{r.code}</Link>
                  <span className="flex-1 truncate text-zinc-700">{r.description ?? "\u2014"}</span>
                  <span className="inline-flex items-center rounded-md bg-amber-50 border border-amber-200 px-1.5 py-0.5 text-[10px] font-medium text-amber-800">{r.tier}</span>
                  <span className="tabular-nums text-emerald-700 font-medium w-16 text-right">{money(r.save_amount)}</span>
                  <span className="tabular-nums text-emerald-700 font-medium w-12 text-right">
                    {r.effective_pct != null ? `${r.effective_pct.toFixed(1)}%` : "\u2014"}
                  </span>
                </li>
              ))
            )}
          </ul>
        </section>

        {/* Closeout Opportunities */}
        <section className="rounded-lg border border-zinc-200 bg-white">
          <header className="border-b border-zinc-200 px-4 py-2 flex items-center justify-between">
            <div>
              <h2 className="text-sm font-medium text-zinc-700">Closeout Deals</h2>
              <p className="text-xs text-zinc-500">Inventory reduction items — buy before they're gone.</p>
            </div>
            <Link to="/closeouts" className="text-xs text-zinc-500 hover:text-zinc-900">See all →</Link>
          </header>
          <ul className="divide-y divide-zinc-100">
            {closeoutsQ.isLoading ? (
              <li className="px-4 py-3 text-sm text-zinc-500">Loading...</li>
            ) : (closeoutsQ.data ?? []).length === 0 ? (
              <li className="px-4 py-3 text-sm text-zinc-500">No closeouts in current edition.</li>
            ) : (
              closeoutsQ.data!.slice(0, 5).map((r) => (
                <li key={r.code} className="px-4 py-2 text-sm flex items-center gap-3 hover:bg-zinc-50">
                  <Link to={`/catalog/${r.code}`} className="font-mono text-xs hover:underline w-20 shrink-0">{r.code}</Link>
                  <span className="flex-1 truncate text-zinc-700">{r.description ?? "\u2014"}</span>
                  <span className="tabular-nums line-through text-zinc-400 w-16 text-right">{money(r.original_case)}</span>
                  <span className="tabular-nums text-emerald-700 font-medium w-16 text-right">{money(r.best_case)}</span>
                  <span className={`text-xs w-10 text-right ${r.days_on_list > 30 ? "text-amber-700" : "text-zinc-500"}`}>{r.days_on_list}d</span>
                </li>
              ))
            )}
          </ul>
        </section>
      </div>

      {/* Price Increases + Category Breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <MoverPanel
          title="Price Increases"
          subtitle="Products with largest cost increases."
          rows={priceIncreases}
          loading={moversQ.isLoading}
          emptyHint="No price increases this month."
          limit={8}
        />

        {/* Category Distribution */}
        {s && s.top_rip_categories.length > 0 && (
          <section className="rounded-lg border border-zinc-200 bg-white">
            <header className="border-b border-zinc-200 px-4 py-2">
              <h2 className="text-sm font-medium text-zinc-700">RIPs by Category</h2>
              <p className="text-xs text-zinc-500">Where the savings are concentrated.</p>
            </header>
            <ul className="divide-y divide-zinc-100">
              {s.top_rip_categories.map((c) => (
                <li key={c.category} className="px-4 py-2 text-sm flex items-center gap-3">
                  <span className="flex-1 text-zinc-700">{c.category}</span>
                  <span className="text-xs text-zinc-500">{c.count} RIPs</span>
                  <span className="tabular-nums text-emerald-700 font-medium w-20 text-right">avg {money(c.avg_save)}</span>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>

      {/* Alerts */}
      <section className="rounded-lg border border-zinc-200 bg-white">
        <header className="border-b border-zinc-200 px-4 py-2 flex items-center justify-between">
          <h2 className="text-sm font-medium text-zinc-700">Recent Alerts</h2>
          <Link to="/alerts" className="text-xs text-zinc-500 hover:text-zinc-900">See all →</Link>
        </header>
        <ul className="divide-y divide-zinc-100">
          {alertsQ.isLoading ? (
            <li className="px-4 py-3 text-sm text-zinc-500">Loading...</li>
          ) : (alertsQ.data ?? []).length === 0 ? (
            <li className="px-4 py-3 text-sm text-zinc-500">
              No alerts yet. They fire after each new edition is ingested.
            </li>
          ) : (
            alertsQ.data!.map((a) => (
              <li key={a.id} className="px-4 py-2 text-sm flex items-center gap-2 hover:bg-zinc-50">
                <span className="inline-flex items-center rounded-md border px-1.5 py-0.5 text-xs font-medium bg-zinc-50 border-zinc-200 text-zinc-700">
                  {a.rule_type}
                </span>
                {a.product_code && (
                  <Link to={`/catalog/${a.product_code}`} className="font-mono text-xs hover:underline">{a.product_code}</Link>
                )}
                <span className="text-zinc-600 flex-1 truncate">
                  {String((a.payload as Record<string, unknown>).description ?? "")}
                </span>
                <span className="text-xs text-zinc-500">{new Date(a.fired_at).toLocaleString()}</span>
              </li>
            ))
          )}
        </ul>
      </section>

      {/* Quick Nav */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Link to="/catalog" className="rounded-lg border border-zinc-200 bg-white px-4 py-3 hover:border-zinc-400 transition-colors">
          <div className="text-sm font-medium text-zinc-700">Catalog</div>
          <div className="text-xs text-zinc-500">Browse all products</div>
        </Link>
        <Link to="/rips" className="rounded-lg border border-zinc-200 bg-white px-4 py-3 hover:border-zinc-400 transition-colors">
          <div className="text-sm font-medium text-zinc-700">RIPs</div>
          <div className="text-xs text-zinc-500">Retail incentive programs</div>
        </Link>
        <Link to="/closeouts" className="rounded-lg border border-zinc-200 bg-white px-4 py-3 hover:border-zinc-400 transition-colors">
          <div className="text-sm font-medium text-zinc-700">Closeouts</div>
          <div className="text-xs text-zinc-500">Last chance inventory</div>
        </Link>
        <Link to="/watchlist" className="rounded-lg border border-zinc-200 bg-white px-4 py-3 hover:border-zinc-400 transition-colors">
          <div className="text-sm font-medium text-zinc-700">My Order List</div>
          <div className="text-xs text-zinc-500">Build your order</div>
        </Link>
      </div>
    </div>
  );
}
