import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { insightsApi } from "../lib/api";
import type { ComboRow } from "../lib/api";
import { money } from "../lib/fmt";
import SortableTable, { useSort, Column } from "../components/SortableTable";

const columns: Column<ComboRow>[] = [
  {
    key: "sku",
    label: "SKU",
    sortable: true,
    hideBelow: "sm",
    sortValue: (r) => r.sku,
    render: (r) => <span className="font-mono text-xs whitespace-nowrap">{r.sku}</span>,
  },
  {
    key: "subcategory",
    label: "Category",
    sortable: true,
    hideBelow: "md",
    sortValue: (r) => r.subcategory ?? "",
    render: (r) => <span className="text-zinc-600 whitespace-nowrap">{r.subcategory ?? "\u2014"}</span>,
  },
  {
    key: "item_code",
    label: "Item Code",
    sortable: true,
    sortValue: (r) => r.item_code ?? "",
    render: (r) => <span className="font-mono text-xs text-zinc-600 whitespace-nowrap">{r.item_code ?? "\u2014"}</span>,
  },
  {
    key: "contains",
    label: "Contains",
    sortable: true,
    sortValue: (r) => r.contains ?? "",
    className: "max-w-md truncate",
    render: (r) => <span title={r.contains ?? ""}>{r.contains ?? "\u2014"}</span>,
  },
  {
    key: "front_line_price",
    label: "Front-Line Price",
    sortable: true,
    align: "right",
    sortValue: (r) => r.front_line_price ? parseFloat(r.front_line_price) : null,
    render: (r) => <span className="tabular-nums whitespace-nowrap">{money(r.front_line_price)}</span>,
  },
];

export default function Combos() {
  const [search, setSearch] = useState("");
  const [selectedCat, setSelectedCat] = useState("");

  const { sort, toggle, sorted } = useSort<ComboRow>({ key: "sku", direction: "asc" });

  const combosQ = useQuery({
    queryKey: ["combos", { search, subcategory: selectedCat }],
    queryFn: () =>
      insightsApi.combos({
        search: search || undefined,
        subcategory: selectedCat || undefined,
        limit: 1000,
      }),
  });

  const subcategories = useMemo(() => {
    if (!combosQ.data) return [];
    const cats = new Set(
      combosQ.data.map((c) => c.subcategory).filter(Boolean) as string[],
    );
    return [...cats].sort();
  }, [combosQ.data]);

  const rows = combosQ.data ?? [];
  const sortedRows = useMemo(() => sorted(rows, columns), [rows, sorted]);

  return (
    <div className="space-y-5">
      <header className="space-y-1">
        <h1 className="text-xl sm:text-2xl font-semibold tracking-tight">Combos</h1>
        <p className="text-sm text-zinc-600">
          Bundled SKUs from the current edition. {rows.length > 0 && `${rows.length} combos loaded.`}
        </p>
      </header>

      <div className="flex flex-col sm:flex-row flex-wrap gap-3">
        <input
          type="text"
          placeholder="Search SKU, code, or contents..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full sm:w-64 rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm placeholder:text-zinc-400 focus:border-zinc-900 focus:outline-none"
        />
        {subcategories.length > 0 && (
          <select
            value={selectedCat}
            onChange={(e) => setSelectedCat(e.target.value)}
            className="rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm"
          >
            <option value="">All categories</option>
            {subcategories.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        )}
      </div>

      <div className="rounded-lg border border-zinc-200 bg-white overflow-hidden">
        {combosQ.isLoading ? (
          <div className="text-center py-12 text-zinc-500">Loading...</div>
        ) : (
          <SortableTable
            columns={columns}
            data={sortedRows}
            sort={sort}
            onSort={toggle}
            rowKey={(r) => r.sku}
            emptyMessage="No combos found."
          />
        )}
      </div>
    </div>
  );
}
