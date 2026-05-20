import { useState, useMemo } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { insightsApi, watchlistApi } from "../lib/api";
import type { CloseoutRow } from "../lib/api";
import { money } from "../lib/fmt";
import FavoriteButton from "../components/FavoriteButton";
import SortableTable, { useSort, Column } from "../components/SortableTable";

export default function Closeouts() {
  const [search, setSearch] = useState("");
  const [minPct, setMinPct] = useState(0);
  const [daysFilter, setDaysFilter] = useState<"" | "new" | "aging">("");

  const { sort, toggle, sorted } = useSort<CloseoutRow>({ key: "pct_off", direction: "desc" });

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
    return rows;
  }, [q.data, search, minPct, daysFilter]);

  const stats = useMemo(() => {
    const rows = filteredRows;
    if (rows.length === 0) return null;
    const totalSave = rows.reduce((s, r) => s + parseFloat(String(r.case_save ?? "0")), 0);
    const avgPct = rows.reduce((s, r) => s + (r.pct_off ?? 0), 0) / rows.length;
    const newCount = rows.filter((r) => r.days_on_list <= 30).length;
    return { count: rows.length, totalSave, avgPct, newCount };
  }, [filteredRows]);

  const columns: Column<CloseoutRow>[] = [
    {
      key: "fav",
      label: "",
      thClassName: "w-8",
      render: (r) => (
        <FavoriteButton code={r.code} isFavorite={favCodes.has(r.code)} note={favNotes.get(r.code)} showNote />
      ),
    },
    {
      key: "code",
      label: "Code",
      sortable: true,
      sortValue: (r) => r.code,
      render: (r) => (
        <Link to={`/catalog/${r.code}`} className="font-mono text-xs hover:underline">{r.code}</Link>
      ),
    },
    {
      key: "description",
      label: "Description",
      sortable: true,
      sortValue: (r) => r.description ?? "",
      render: (r) => <span>{r.description ?? "\u2014"}</span>,
    },
    {
      key: "size",
      label: "Size",
      sortable: true,
      sortValue: (r) => r.size ?? "",
      render: (r) => <span className="text-zinc-600">{r.size ?? "\u2014"}</span>,
    },
    {
      key: "original_case",
      label: "Original Case",
      sortable: true,
      align: "right",
      hideBelow: "sm",
      sortValue: (r) => r.original_case ? parseFloat(r.original_case) : null,
      render: (r) => <span className="tabular-nums line-through text-zinc-400">{money(r.original_case)}</span>,
    },
    {
      key: "best_case",
      label: "Best Case",
      sortable: true,
      align: "right",
      sortValue: (r) => r.best_case ? parseFloat(r.best_case) : null,
      render: (r) => <span className="tabular-nums font-medium text-emerald-700">{money(r.best_case)}</span>,
    },
    {
      key: "case_save",
      label: "Save",
      sortable: true,
      align: "right",
      sortValue: (r) => r.case_save ? parseFloat(r.case_save) : null,
      render: (r) => <span className="tabular-nums text-emerald-700">{money(r.case_save)}</span>,
    },
    {
      key: "pct_off",
      label: "% Off",
      sortable: true,
      align: "right",
      sortValue: (r) => r.pct_off,
      render: (r) =>
        r.pct_off == null ? (
          <span className="text-zinc-300">{"\u2014"}</span>
        ) : (
          <span className={r.pct_off >= 10 ? "text-emerald-700 font-medium" : ""}>{r.pct_off.toFixed(1)}%</span>
        ),
    },
    {
      key: "days_on_list",
      label: "Days on List",
      sortable: true,
      align: "right",
      sortValue: (r) => r.days_on_list,
      render: (r) =>
        r.days_on_list > 60 ? (
          <span className="text-red-600 font-medium">{r.days_on_list}d</span>
        ) : r.days_on_list > 30 ? (
          <span className="text-amber-700">{r.days_on_list}d</span>
        ) : (
          <span className="text-zinc-600">{r.days_on_list}d</span>
        ),
    },
  ];

  const sortedRows = useMemo(() => sorted(filteredRows, columns), [filteredRows, sorted, columns]);

  return (
    <div className="space-y-5">
      <header className="space-y-1">
        <h1 className="text-xl sm:text-2xl font-semibold tracking-tight">Closeouts</h1>
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

      <div className="flex flex-col sm:flex-row flex-wrap gap-3 items-center">
        <input type="text" placeholder="Search SKU or description..." value={search} onChange={(e) => setSearch(e.target.value)}
          className="w-full sm:w-64 rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm placeholder:text-zinc-400 focus:border-zinc-900 focus:outline-none" />
        <select value={daysFilter} onChange={(e) => setDaysFilter(e.target.value as "" | "new" | "aging")} className="rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm">
          <option value="">All items</option>
          <option value="new">New (30 days or less)</option>
          <option value="aging">Aging (more than 30 days)</option>
        </select>
        <label className="text-sm text-zinc-700 flex items-center gap-2">
          Min %
          <input type="number" value={minPct} onChange={(e) => setMinPct(parseFloat(e.target.value) || 0)}
            min={0} max={100} step={1} className="w-16 rounded-md border border-zinc-300 bg-white px-2 py-1 text-sm" />
        </label>
      </div>

      <div className="rounded-lg border border-zinc-200 bg-white overflow-hidden">
        {q.isLoading ? (
          <div className="text-center py-12 text-zinc-500">Loading...</div>
        ) : (
          <SortableTable
            columns={columns}
            data={sortedRows}
            sort={sort}
            onSort={toggle}
            rowKey={(r) => r.code}
            emptyMessage="No closeouts match your filters."
          />
        )}
      </div>
    </div>
  );
}
