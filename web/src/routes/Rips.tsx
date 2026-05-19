import { useState, useMemo } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { insightsApi, watchlistApi } from "../lib/api";
import type { RipRow } from "../lib/api";
import { money } from "../lib/fmt";
import FavoriteButton from "../components/FavoriteButton";

type SortKey = "save_pct" | "save_amount" | "case_price" | "tier";

function sortRows(rows: RipRow[], key: SortKey): RipRow[] {
  const copy = [...rows];
  switch (key) {
    case "save_pct":
      return copy.sort((a, b) => (b.effective_pct ?? 0) - (a.effective_pct ?? 0));
    case "save_amount":
      return copy.sort((a, b) => parseFloat(String(b.save_amount)) - parseFloat(String(a.save_amount)));
    case "case_price":
      return copy.sort((a, b) => parseFloat(String(a.case_price ?? "999999")) - parseFloat(String(b.case_price ?? "999999")));
    case "tier":
      return copy.sort((a, b) => a.tier_cases - b.tier_cases);
    default:
      return copy;
  }
}

export default function Rips() {
  const [search, setSearch] = useState("");
  const [minPct, setMinPct] = useState(0);
  const [tierMax, setTierMax] = useState<number | "">("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [stabilityFilter, setStabilityFilter] = useState<"" | "stable" | "rotating">("");
  const [sort, setSort] = useState<SortKey>("save_pct");

  const wlQ = useQuery({ queryKey: ["watchlist"], queryFn: () => watchlistApi.list() });
  const favCodes = useMemo(() => new Set((wlQ.data ?? []).map((w) => w.product_code)), [wlQ.data]);
  const favNotes = useMemo(() => {
    const m = new Map<string, string>();
    for (const w of wlQ.data ?? []) if (w.notes) m.set(w.product_code, w.notes);
    return m;
  }, [wlQ.data]);

  const ripsQ = useQuery({
    queryKey: ["rips", { minPct, tierMax }],
    queryFn: () =>
      insightsApi.rips({
        min_pct: minPct || undefined,
        tier_cases_max: typeof tierMax === "number" ? tierMax : undefined,
        limit: 500,
      }),
  });

  // Client-side filtering for search, category, stability
  const filteredRows = useMemo(() => {
    let rows = ripsQ.data ?? [];
    if (search) {
      const q = search.toLowerCase();
      rows = rows.filter(
        (r) =>
          r.code.toLowerCase().includes(q) ||
          (r.description ?? "").toLowerCase().includes(q) ||
          (r.brand_slug ?? "").toLowerCase().includes(q)
      );
    }
    if (categoryFilter) {
      rows = rows.filter((r) => r.category_slug === categoryFilter);
    }
    if (stabilityFilter === "stable") {
      rows = rows.filter((r) => r.stable === true);
    } else if (stabilityFilter === "rotating") {
      rows = rows.filter((r) => r.stable === false);
    }
    return sortRows(rows, sort);
  }, [ripsQ.data, search, categoryFilter, stabilityFilter, sort]);

  // Extract unique categories
  const categories = useMemo(() => {
    if (!ripsQ.data) return [];
    const set = new Set<string>();
    for (const r of ripsQ.data) if (r.category_slug) set.add(r.category_slug);
    return [...set].sort();
  }, [ripsQ.data]);

  // Summary stats
  const stats = useMemo(() => {
    const rows = filteredRows;
    if (rows.length === 0) return null;
    const totalSave = rows.reduce((s, r) => s + parseFloat(String(r.save_amount)), 0);
    const avgPct = rows.reduce((s, r) => s + (r.effective_pct ?? 0), 0) / rows.length;
    const stableCount = rows.filter((r) => r.stable === true).length;
    return { count: rows.length, totalSave, avgPct, stableCount };
  }, [filteredRows]);

  return (
    <div className="space-y-5">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">RIPs</h1>
        <p className="text-sm text-zinc-600">
          Retail Incentive Programs — ranked by savings. {stats && `${stats.count} RIPs shown.`}
        </p>
      </header>

      {/* Summary cards */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="rounded-lg border border-zinc-200 bg-white px-3 py-2">
            <div className="text-xs text-zinc-500">Total RIPs</div>
            <div className="text-lg font-semibold text-zinc-900">{stats.count}</div>
          </div>
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2">
            <div className="text-xs text-emerald-600">Avg Savings</div>
            <div className="text-lg font-semibold text-emerald-800">{stats.avgPct.toFixed(1)}%</div>
          </div>
          <div className="rounded-lg border border-zinc-200 bg-white px-3 py-2">
            <div className="text-xs text-zinc-500">Total Savings Pool</div>
            <div className="text-lg font-semibold text-zinc-900">{money(stats.totalSave)}</div>
          </div>
          <div className="rounded-lg border border-zinc-200 bg-white px-3 py-2">
            <div className="text-xs text-zinc-500">Stable RIPs</div>
            <div className="text-lg font-semibold text-zinc-900">{stats.stableCount} <span className="text-xs font-normal text-zinc-400">/ {stats.count}</span></div>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-3 items-center">
        <input
          type="text"
          placeholder="Search SKU, description, brand..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-64 rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm placeholder:text-zinc-400 focus:border-zinc-900 focus:outline-none"
        />
        <select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)} className="rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm">
          <option value="">All categories</option>
          {categories.map((c) => (<option key={c} value={c}>{c}</option>))}
        </select>
        <select value={stabilityFilter} onChange={(e) => setStabilityFilter(e.target.value as "" | "stable" | "rotating")} className="rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm">
          <option value="">Any stability</option>
          <option value="stable">Stable only</option>
          <option value="rotating">Rotating only</option>
        </select>
        <label className="text-sm text-zinc-700 flex items-center gap-2">
          Min %
          <input type="number" value={minPct} onChange={(e) => setMinPct(parseFloat(e.target.value) || 0)}
            min={0} max={100} step={1} className="w-16 rounded-md border border-zinc-300 bg-white px-2 py-1 text-sm" />
        </label>
        <select value={tierMax} onChange={(e) => setTierMax(e.target.value === "" ? "" : parseInt(e.target.value, 10))}
          className="rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm">
          <option value="">Any tier</option>
          <option value="1">1 case</option>
          <option value="3">3 cases</option>
          <option value="5">5 cases</option>
          <option value="10">10 cases</option>
          <option value="25">25 cases</option>
        </select>
        <select value={sort} onChange={(e) => setSort(e.target.value as SortKey)} className="rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm">
          <option value="save_pct">Sort by % saved</option>
          <option value="save_amount">Sort by $ saved</option>
          <option value="case_price">Sort by case price</option>
          <option value="tier">Sort by tier (low first)</option>
        </select>
      </div>

      <div className="rounded-lg border border-zinc-200 bg-white overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-zinc-200 text-sm">
            <thead className="bg-zinc-50 text-left text-xs uppercase tracking-wide text-zinc-500">
              <tr>
                <th className="px-3 py-2 w-8"></th>
                <th className="px-4 py-2">Code</th>
                <th className="px-4 py-2">Description</th>
                <th className="px-4 py-2">Size</th>
                <th className="px-4 py-2">Tier</th>
                <th className="px-4 py-2 text-right">Save</th>
                <th className="px-4 py-2 text-right">Case after</th>
                <th className="px-4 py-2 text-right">% Save</th>
                <th className="px-4 py-2">Stability</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {ripsQ.isLoading ? (
                <tr><td colSpan={9} className="px-4 py-6 text-center text-zinc-500">Loading...</td></tr>
              ) : filteredRows.length === 0 ? (
                <tr><td colSpan={9} className="px-4 py-6 text-center text-zinc-500">No RIPs match your filters.</td></tr>
              ) : (
                filteredRows.map((r, i) => (
                  <tr key={`${r.code}-${r.tier}-${i}`} className="hover:bg-zinc-50">
                    <td className="px-3 py-2">
                      <FavoriteButton code={r.code} isFavorite={favCodes.has(r.code)} note={favNotes.get(r.code)} showNote />
                    </td>
                    <td className="px-4 py-2 font-mono text-xs">
                      <Link to={`/catalog/${r.code}`} className="hover:underline">{r.code}</Link>
                    </td>
                    <td className="px-4 py-2">
                      <Link to={`/catalog/${r.code}`} className="hover:underline">{r.description ?? "\u2014"}</Link>
                    </td>
                    <td className="px-4 py-2 text-zinc-600">{r.size ?? "\u2014"}</td>
                    <td className="px-4 py-2 font-mono text-xs">{r.tier}</td>
                    <td className="px-4 py-2 text-right tabular-nums text-emerald-700 font-medium">{money(r.save_amount)}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{money(r.case_price)}</td>
                    <td className="px-4 py-2 text-right tabular-nums">
                      {r.effective_pct == null ? "\u2014" : (
                        <span className={r.effective_pct >= 5 ? "text-emerald-700 font-medium" : ""}>{r.effective_pct.toFixed(1)}%</span>
                      )}
                    </td>
                    <td className="px-4 py-2">
                      {r.stable === null ? (
                        <span className="text-xs text-zinc-400">unknown</span>
                      ) : r.stable ? (
                        <span className="inline-flex items-center rounded-md bg-emerald-50 border border-emerald-200 px-1.5 py-0.5 text-xs text-emerald-800">stable</span>
                      ) : (
                        <span className="inline-flex items-center rounded-md bg-amber-50 border border-amber-200 px-1.5 py-0.5 text-xs text-amber-800">rotating</span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
