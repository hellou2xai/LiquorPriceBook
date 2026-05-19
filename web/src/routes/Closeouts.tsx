import { useMemo } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { insightsApi, watchlistApi } from "../lib/api";
import { money } from "../lib/fmt";
import FavoriteButton from "../components/FavoriteButton";

export default function Closeouts() {
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

  return (
    <div className="space-y-5">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Closeouts</h1>
        <p className="text-sm text-zinc-600">
          Inventory Reduction items in the current edition. These are terminal listings —
          last chance to buy. Days-on-list shows how long it has been sitting here.
        </p>
      </header>

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
                <tr><td colSpan={9} className="px-4 py-6 text-center text-zinc-500">Loading…</td></tr>
              ) : (q.data ?? []).length === 0 ? (
                <tr><td colSpan={9} className="px-4 py-6 text-center text-zinc-500">No closeouts in the current edition.</td></tr>
              ) : (
                q.data!.map((r) => (
                  <tr key={r.code} className="hover:bg-zinc-50">
                    <td className="px-3 py-2">
                      <FavoriteButton code={r.code} isFavorite={favCodes.has(r.code)} note={favNotes.get(r.code)} showNote />
                    </td>
                    <td className="px-4 py-2 font-mono text-xs">
                      <Link to={`/catalog/${r.code}`} className="hover:underline">{r.code}</Link>
                    </td>
                    <td className="px-4 py-2">{r.description ?? "—"}</td>
                    <td className="px-4 py-2 text-zinc-600">{r.size ?? "—"}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{money(r.original_case)}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{money(r.best_case)}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{money(r.case_save)}</td>
                    <td className="px-4 py-2 text-right tabular-nums">
                      {r.pct_off == null ? "—" : `${r.pct_off.toFixed(1)}%`}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">
                      {r.days_on_list > 30 ? (
                        <span className="text-amber-700">{r.days_on_list}d</span>
                      ) : (
                        `${r.days_on_list}d`
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
