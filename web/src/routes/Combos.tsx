import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { insightsApi } from "../lib/api";
import { money } from "../lib/fmt";

export default function Combos() {
  const [search, setSearch] = useState("");
  const [selectedCat, setSelectedCat] = useState("");

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

  return (
    <div className="space-y-5">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Combos</h1>
        <p className="text-sm text-zinc-600">
          Bundled SKUs from the current edition. {rows.length > 0 && `${rows.length} combos loaded.`}
        </p>
      </header>

      <div className="flex flex-wrap gap-3">
        <input
          type="text"
          placeholder="Search SKU, code, or contents..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-64 rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm placeholder:text-zinc-400 focus:border-indigo-400 focus:outline-none focus:ring-1 focus:ring-indigo-400"
        />
        {subcategories.length > 0 && (
          <select
            value={selectedCat}
            onChange={(e) => setSelectedCat(e.target.value)}
            className="rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm"
          >
            <option value="">All categories</option>
            {subcategories.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        )}
      </div>

      <div className="rounded-lg border border-zinc-200 bg-white overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-zinc-200 text-sm">
            <thead className="bg-zinc-50 text-left text-xs uppercase tracking-wide text-zinc-500">
              <tr>
                <th className="px-4 py-2">SKU</th>
                <th className="px-4 py-2">Category</th>
                <th className="px-4 py-2">Item Code</th>
                <th className="px-4 py-2">Contains</th>
                <th className="px-4 py-2 text-right">Front-Line Price</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {combosQ.isLoading ? (
                <tr>
                  <td colSpan={5} className="px-4 py-6 text-center text-zinc-500">
                    Loading...
                  </td>
                </tr>
              ) : rows.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-6 text-center text-zinc-500">
                    No combos found.
                  </td>
                </tr>
              ) : (
                rows.map((c) => (
                  <tr key={c.sku} className="hover:bg-zinc-50">
                    <td className="px-4 py-2 font-mono text-xs whitespace-nowrap">{c.sku}</td>
                    <td className="px-4 py-2 text-zinc-600 whitespace-nowrap">
                      {c.subcategory ?? "—"}
                    </td>
                    <td className="px-4 py-2 font-mono text-xs text-zinc-600 whitespace-nowrap">
                      {c.item_code ?? "—"}
                    </td>
                    <td className="px-4 py-2 max-w-md truncate" title={c.contains ?? ""}>
                      {c.contains ?? "—"}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums whitespace-nowrap">
                      {money(c.front_line_price)}
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
