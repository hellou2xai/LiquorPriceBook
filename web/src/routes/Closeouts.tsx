import { useState, useMemo } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { insightsApi, watchlistApi } from "../lib/api";
import type { CloseoutRow } from "../lib/api";
import { money } from "../lib/fmt";
import FavoriteButton from "../components/FavoriteButton";

type SortKey = "pct_off" | "case_save" | "best_case" | "days";

function sortRows(rows: CloseoutRow[], key: SortKey): CloseoutRow[] {
  const copy = [...rows];
  switch (key) {
    case "pct_off":
      return copy.sort((a, b) => (b.pct_off ?? 0) - (a.pct_off ?? 0));
    case "case_save":
      return copy.sort((a, b) => parseFloat(String(b.case_save ?? "0")) - parseFloat(String(a.case_save ?? "0")));
    case "best_case":
      return copy.sort((a, b) => parseFloat(String(a.best_case ?? "999999")) - parseFloat(String(b.best_case ?? "999999")));
    case "days":
      return copy.sort((a, b) => b.days_on_list - a.days_on_list);
    default:
      return copy;
  }
}

export default function Closeouts() {
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortKey>("pct_off");
  const [minPct, setMinPct] = useState(0);
  const [daysFilter, setDaysFilter] = useState<"" | "new" | "aging">("");

  const wlQ = useQuery({ queryKey: ["watchlist"], queryFn: () => watchlistApi.list() });
  const favCodes = useMemo(() => new Set((wlQ.data ?? []).map((w) => w.product_code)), [wlQ.data]);
  const favNotes = useMemo(() => {
    const m = new Map<string, string>();
    for (const w of wlQ.data ?? []) if (w.notes) m.set(w.product_code, w.notes);
    return m;
  }, [wlQ.data]);

  const q = useQuery({
    queryKey: ["closeouts"],
    queryFn: () => insightsApi.closeouts({ limit: 500 }),
  });

  const filteredRows = useMemo(() => {
    let rows = q.data ?? [];
    if (search) {
      const s = search.toLowerCase();
      rows = rows.filter(
        (r) => r.code.toLowerCase().includes(s) || (r.description ?? "").toLowerCase().includes(s)
      );
    }
    if (minPct > 0) {
      rows = rows.filter((r) => (r.pct_off ?? 0) >= minPct);
    }
    if (daysFilter === "new") {
      rows = rows.filter((r) => r.days_on_list <= 30);
    } else if (daysFilter === "aging") {
      rows = rows.filter((r) => r.days_on_list > 30);
    }
    return sortRows(rows, sort);
  }, [q.data, search, minPct, daysFilter, sort]);

  const stats = useMemo(() => {
    const rows = filteredRows;
    if (rows.length === 0) return null;
    const totalSave = rows.reduce((s, r) => s + parseFloat(String(r.case_save ?? "0")), 0);
    const avgPct = rows.reduce((s, r) => s + (r.pct_off ?? 0), 0) / rows.length;
    const newCount = rows.filter((r) => r.days_on_list <= 30).length;
    return { count: rows.length, totalSave, avgPct, newCount };
  }, [filteredRows]);

  return (
    <div className="space-y-5">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Closeouts</h1>
        <p className="text-sm text-zinc-600">
          Inventory Reduction items — terminal listings, last chance to buy. {stats && `${stats.count} shown.`}
        </p>
      </header>

      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="rounded-lg border border-zinc-200 bg-white px-3 py-2">
            <div className="text-xs text-zinc-500">Total Closeouts</div>
            <div className="text-lg font-semibold text-zinc-900">{stats.count}</div>
          </div>
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2">
            <div className="text-xs text-emerald-600">Avg Discount</div>
            <div className="text-lg font-semibold text-emerald-800">{stats.avgPct.toFixed(1)}%</div>
          </div>
          <div className="rounded-lg border border-zinc-200 bg-white px-3 py-2">
            <div className="text-xs text-zinc-500">Total Savings</div>
            <div className="text-lg font-semibold text-zinc-900">{money(stats.totalSave)}</div>
          </div>
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
            <div className="text-xs text-amber-600">New This Month</div>
            <div className="text-lg font-semibold text-amber-800">{stats.newCount}</div>
          </div>
        </div>
      )}

      <div className="flex flex-wrap gap-3 items-center">
        <input type="text" placeholder="Search SKU or description..." value={search} onChange={(e) => setSearch(e.target.value)}
          className="w-64 rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm placeholder:text-zinc-400 focus:border-zinc-900 focus:outline-none" />
        <select value={daysFilter} onChange={(e) => setDaysFilter(e.target.value as "" | "new" | "aging")} className="rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm">
          <option value="">All items</option>
          <option value="new">New (≤30 days)</option>
          <option value="aging">Aging (&gt;30 days)</option>
        </select>
        <label className="text-sm text-zinc-700 flex items-center gap-2">
          Min %
          <input type="number" value={minPct} onChange={(e) => setMinPct(parseFloat(e.target.value) || 0)}
            min={0} max={100} step={1} className="w-16 rounded-md border border-zinc-300 bg-white px-2 py-1 text-sm" />
        </label>
        <select value={sort} onChange={(e) => setSort(e.target.value as SortKey)} className="rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm">
          <option value="pct_off">Sort by % off</option>
          <option value="case_save">Sort by $ saved</option>
          <option value="best_case">Sort by best case price</option>
          <option value="days">Sort by days on list</option>
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
                <th className="px-4 py-2 text-right">Original case</th>
                <th className="px-4 py-2 text-right">Best case</th>
                <th className="px-4 py-2 text-right">Save</th>
                <th className="px-4 py-2 text-right">% off</th>
                <th className="px-4 py-2 text-right">Days on list</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {q.isLoading ? (
                <tr><td colSpan={9} className="px-4 py-6 text-center text-zinc-500">Loading...</td></tr>
              ) : filteredRows.length === 0 ? (
                <tr><td colSpan={9} className="px-4 py-6 text-center text-zinc-500">No closeouts match your filters.</td></tr>
              ) : (
                filteredRows.map((r) => (
                  <tr key={r.code} className={`hover:bg-zinc-50 ${r.days_on_list > 60 ? "bg-red-50/30" : ""}`}>
                    <td className="px-3 py-2">
                      <FavoriteButton code={r.code} isFavorite={favCodes.has(r.code)} note={favNotes.get(r.code)} showNote />
                    </td>
                    <td className="px-4 py-2 font-mono text-xs">
                      <Link to={`/catalog/${r.code}`} className="hover:underline">{r.code}</Link>
                    </td>
                    <td className="px-4 py-2">{r.description ?? "\u2014"}</td>
                    <td className="px-4 py-2 text-zinc-600">{r.size ?? "\u2014"}</td>
                    <td className="px-4 py-2 text-right tabular-nums line-through text-zinc-400">{money(r.original_case)}</td>
                    <td className="px-4 py-2 text-right tabular-nums font-medium text-emerald-700">{money(r.best_case)}</td>
                    <td className="px-4 py-2 text-right tabular-nums text-emerald-700">{money(r.case_save)}</td>
                    <td className="px-4 py-2 text-right tabular-nums">
                      {r.pct_off == null ? "\u2014" : (
                        <span className={r.pct_off >= 10 ? "text-emerald-700 font-medium" : ""}>{r.pct_off.toFixed(1)}%</span>
                      )}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">
                      {r.days_on_list > 60 ? (
                        <span className="text-red-600 font-medium">{r.days_on_list}d</span>
                      ) : r.days_on_list > 30 ? (
                        <span className="text-amber-700">{r.days_on_list}d</span>
                      ) : (
                        <span className="text-zinc-600">{r.days_on_list}d</span>
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
