import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { insightsApi } from "../lib/api";

const RULE_LABELS: Record<string, string> = {
  price_drop_pct: "Price drop",
  price_rise_pct: "Price rise",
  new_rip: "New RIP",
  rip_rotated: "RIP rotated",
  partial_expiring_soon: "Partial expiring",
  new_closeout: "New closeout",
  watchlist_target_hit: "Target hit",
};

const RULE_TONE: Record<string, string> = {
  price_drop_pct: "bg-emerald-50 border-emerald-200 text-emerald-800",
  price_rise_pct: "bg-red-50 border-red-200 text-red-800",
  new_rip: "bg-amber-50 border-amber-200 text-amber-800",
  rip_rotated: "bg-amber-50 border-amber-200 text-amber-800",
  partial_expiring_soon: "bg-sky-50 border-sky-200 text-sky-800",
  new_closeout: "bg-rose-50 border-rose-200 text-rose-800",
  watchlist_target_hit: "bg-emerald-50 border-emerald-200 text-emerald-800",
};

export default function Alerts() {
  const q = useQuery({
    queryKey: ["alerts", { full: true }],
    queryFn: () => insightsApi.alerts({ limit: 200 }),
  });

  return (
    <div className="space-y-5">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Alerts</h1>
        <p className="text-sm text-zinc-600">
          Fired by the rules engine at the end of every successful ingest.
        </p>
      </header>

      <div className="rounded-lg border border-zinc-200 bg-white overflow-hidden">
        <ul className="divide-y divide-zinc-100">
          {q.isLoading ? (
            <li className="px-4 py-6 text-center text-zinc-500 text-sm">Loading…</li>
          ) : (q.data ?? []).length === 0 ? (
            <li className="px-4 py-6 text-center text-zinc-500 text-sm">
              No alerts yet.
            </li>
          ) : (
            q.data!.map((a) => (
              <li key={a.id} className="px-4 py-3 text-sm flex flex-col md:flex-row md:items-center gap-2">
                <span
                  className={`inline-flex w-fit items-center rounded-md border px-2 py-0.5 text-xs font-medium ${
                    RULE_TONE[a.rule_type] ?? "bg-zinc-50 border-zinc-200 text-zinc-700"
                  }`}
                >
                  {RULE_LABELS[a.rule_type] ?? a.rule_type}
                </span>
                {a.product_code ? (
                  <Link
                    to={`/catalog/${a.product_code}`}
                    className="font-mono text-xs hover:underline"
                  >
                    {a.product_code}
                  </Link>
                ) : null}
                <div className="flex-1 text-zinc-700">
                  {String((a.payload as any).description ?? "")}
                  {(a.payload as any).pct != null ? (
                    <span className="text-zinc-500"> · {Number((a.payload as any).pct).toFixed(1)}%</span>
                  ) : null}
                  {(a.payload as any).save_amount != null ? (
                    <span className="text-zinc-500">
                      {" "}
                      · save ${Number((a.payload as any).save_amount).toFixed(2)}
                    </span>
                  ) : null}
                </div>
                <span className="text-xs text-zinc-500">
                  {new Date(a.fired_at).toLocaleString()}
                </span>
              </li>
            ))
          )}
        </ul>
      </div>
    </div>
  );
}
