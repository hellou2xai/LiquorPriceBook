import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { insightsApi } from "../lib/api";
import { money } from "../lib/fmt";

export default function Rips() {
  const [minPct, setMinPct] = useState(0);
  const [tierMax, setTierMax] = useState<number | "">("");

  const ripsQ = useQuery({
    queryKey: ["rips", { minPct, tierMax }],
    queryFn: () =>
      insightsApi.rips({
        min_pct: minPct || undefined,
        tier_cases_max: typeof tierMax === "number" ? tierMax : undefined,
        limit: 200,
      }),
  });

  return (
    <div className="space-y-5">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">RIPs</h1>
        <p className="text-sm text-zinc-600">
          Retail Incentive Programs in the current edition, ranked by effective % savings.
        </p>
      </header>

      <div className="flex flex-wrap gap-3">
        <label className="text-sm text-zinc-700 flex items-center gap-2">
          Min effective %
          <input
            type="number"
            value={minPct}
            onChange={(e) => setMinPct(parseFloat(e.target.value) || 0)}
            min={0}
            max={100}
            step={1}
            className="w-20 rounded-md border border-zinc-300 bg-white px-2 py-1 text-sm"
          />
        </label>
        <label className="text-sm text-zinc-700 flex items-center gap-2">
          Max tier (cases)
          <select
            value={tierMax}
            onChange={(e) =>
              setTierMax(e.target.value === "" ? "" : parseInt(e.target.value, 10))
            }
            className="rounded-md border border-zinc-300 bg-white px-2 py-1 text-sm"
          >
            <option value="">Any</option>
            <option value="1">1 case</option>
            <option value="3">3 cases</option>
            <option value="5">5 cases</option>
            <option value="10">10 cases</option>
            <option value="25">25 cases</option>
          </select>
        </label>
      </div>

      <div className="rounded-lg border border-zinc-200 bg-white overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-zinc-200 text-sm">
            <thead className="bg-zinc-50 text-left text-xs uppercase tracking-wide text-zinc-500">
              <tr>
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
                <tr><td colSpan={8} className="px-4 py-6 text-center text-zinc-500">Loading…</td></tr>
              ) : (ripsQ.data ?? []).length === 0 ? (
                <tr><td colSpan={8} className="px-4 py-6 text-center text-zinc-500">No RIPs match.</td></tr>
              ) : (
                ripsQ.data!.map((r, i) => (
                  <tr key={`${r.code}-${r.tier}-${i}`} className="hover:bg-zinc-50">
                    <td className="px-4 py-2 font-mono text-xs">
                      <Link to={`/catalog/${r.code}`} className="hover:underline">{r.code}</Link>
                    </td>
                    <td className="px-4 py-2">
                      <Link to={`/catalog/${r.code}`} className="hover:underline">{r.description ?? "—"}</Link>
                    </td>
                    <td className="px-4 py-2 text-zinc-600">{r.size ?? "—"}</td>
                    <td className="px-4 py-2 font-mono text-xs">{r.tier}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{money(r.save_amount)}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{money(r.case_price)}</td>
                    <td className="px-4 py-2 text-right tabular-nums">
                      {r.effective_pct == null ? "—" : `${r.effective_pct.toFixed(1)}%`}
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
