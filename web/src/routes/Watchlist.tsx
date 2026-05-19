import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { watchlistApi } from "../lib/api";
import { money } from "../lib/fmt";

export default function Watchlist() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["watchlist"], queryFn: () => watchlistApi.list() });

  const remove = useMutation({
    mutationFn: (code: string) => watchlistApi.remove(code),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlist"] }),
  });

  return (
    <div className="space-y-5">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Watchlist</h1>
        <p className="text-sm text-zinc-600">
          SKUs you're tracking, with optional target prices. When the case cost
          dips below a target, an alert fires.
        </p>
      </header>

      <div className="rounded-lg border border-zinc-200 bg-white overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-zinc-200 text-sm">
            <thead className="bg-zinc-50 text-left text-xs uppercase tracking-wide text-zinc-500">
              <tr>
                <th className="px-4 py-2">Code</th>
                <th className="px-4 py-2 text-right">Target case</th>
                <th className="px-4 py-2 text-right">Target btl</th>
                <th className="px-4 py-2">Notes</th>
                <th className="px-4 py-2">Added</th>
                <th className="px-4 py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {q.isLoading ? (
                <tr><td colSpan={6} className="px-4 py-6 text-center text-zinc-500">Loading…</td></tr>
              ) : (q.data ?? []).length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-6 text-center text-zinc-500">
                    No items yet. Open a product and click "Add to watchlist".
                  </td>
                </tr>
              ) : (
                q.data!.map((w) => (
                  <tr key={w.product_code} className="hover:bg-zinc-50">
                    <td className="px-4 py-2 font-mono text-xs">
                      <Link to={`/catalog/${w.product_code}`} className="hover:underline">
                        {w.product_code}
                      </Link>
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">{money(w.target_case_price)}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{money(w.target_btl_price)}</td>
                    <td className="px-4 py-2 text-zinc-600">{w.notes ?? "—"}</td>
                    <td className="px-4 py-2 text-zinc-500">
                      {new Date(w.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-4 py-2 text-right">
                      <button
                        onClick={() => remove.mutate(w.product_code)}
                        className="text-xs text-red-700 hover:underline"
                      >
                        Remove
                      </button>
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
