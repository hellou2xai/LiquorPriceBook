import { useMemo } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { insightsApi } from "../lib/api";
import type { AlertEvent } from "../lib/api";
import SortableTable, { useSort, Column } from "../components/SortableTable";

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
  const { sort, toggle, sorted } = useSort<AlertEvent>({ key: "fired_at", direction: "desc" });

  const q = useQuery({
    queryKey: ["alerts", { full: true }],
    queryFn: () => insightsApi.alerts({ limit: 200 }),
  });

  const data = q.data ?? [];

  const columns: Column<AlertEvent>[] = [
    {
      key: "rule_type",
      label: "Type",
      sortable: true,
      sortValue: (a) => a.rule_type,
      render: (a) => (
        <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${RULE_TONE[a.rule_type] ?? "bg-brand-navy/5 border-brand-navy/10 text-brand-navy"}`}>
          {RULE_LABELS[a.rule_type] ?? a.rule_type}
        </span>
      ),
    },
    {
      key: "product_code",
      label: "Product",
      sortable: true,
      hideBelow: "sm",
      sortValue: (a) => a.product_code ?? "",
      render: (a) =>
        a.product_code ? (
          <Link to={`/catalog/${a.product_code}`} className="font-mono text-xs text-brand-navy hover:text-brand-orange hover:underline">{a.product_code}</Link>
        ) : (
          <span className="text-zinc-300 text-xs">{"\u2014"}</span>
        ),
    },
    {
      key: "details",
      label: "Details",
      sortable: false,
      hideBelow: "md",
      render: (a) => (
        <span className="text-zinc-700">
          {String((a.payload as Record<string, unknown>).description ?? "")}
          {(a.payload as Record<string, unknown>).pct != null && (
            <span className="text-zinc-500"> · {Number((a.payload as Record<string, unknown>).pct).toFixed(1)}%</span>
          )}
          {(a.payload as Record<string, unknown>).save_amount != null && (
            <span className="text-zinc-500"> · save ${Number((a.payload as Record<string, unknown>).save_amount).toFixed(2)}</span>
          )}
        </span>
      ),
    },
    {
      key: "fired_at",
      label: "Fired",
      sortable: true,
      align: "right",
      sortValue: (a) => a.fired_at,
      render: (a) => <span className="text-xs text-zinc-500 whitespace-nowrap">{new Date(a.fired_at).toLocaleString()}</span>,
    },
  ];

  const sortedData = useMemo(() => sorted(data, columns), [data, sorted, columns]);

  return (
    <div className="space-y-5">
      <header className="space-y-1">
        <h1 className="text-xl sm:text-2xl font-semibold tracking-tight text-brand-navy">Alerts</h1>
        <p className="text-sm text-zinc-600">
          Fired by the rules engine at the end of every successful ingest.
        </p>
      </header>

      <div className="rounded-xl shadow-sm border border-zinc-200 bg-white overflow-hidden">
        {q.isLoading ? (
          <div className="text-center py-12 text-zinc-500">Loading...</div>
        ) : (
          <SortableTable
            columns={columns}
            data={sortedData}
            sort={sort}
            onSort={toggle}
            rowKey={(a) => a.id}
            emptyMessage="No alerts yet."
          />
        )}
      </div>
    </div>
  );
}
