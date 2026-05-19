import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { catalogApi, watchlistApi } from "../lib/api";
import { money, pct, pctClass } from "../lib/fmt";
import FavoriteButton from "../components/FavoriteButton";

const PAGE_SIZE = 50;

type SortKey = "name" | "case_cost_asc" | "case_cost_desc" | "moved_pct_abs";

export default function Catalog() {
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [categorySlug, setCategorySlug] = useState<string | null>(null);
  const [hasRip, setHasRip] = useState<boolean | null>(null);
  const [sort, setSort] = useState<SortKey>("name");
  const [page, setPage] = useState(0);

  // Debounce search input
  useMemo(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 250);
    return () => clearTimeout(t);
  }, [search]);

  const wlQ = useQuery({ queryKey: ["watchlist"], queryFn: () => watchlistApi.list() });
  const favCodes = useMemo(() => new Set((wlQ.data ?? []).map((w) => w.product_code)), [wlQ.data]);
  const favNotes = useMemo(() => {
    const m = new Map<string, string>();
    for (const w of wlQ.data ?? []) if (w.notes) m.set(w.product_code, w.notes);
    return m;
  }, [wlQ.data]);

  const categoriesQ = useQuery({
    queryKey: ["categories"],
    queryFn: () => catalogApi.categories(),
    staleTime: 5 * 60_000,
  });

  const productsQ = useQuery({
    queryKey: [
      "products",
      { search: debouncedSearch, category: categorySlug, hasRip, sort, page },
    ],
    queryFn: () =>
      catalogApi.products({
        search: debouncedSearch || undefined,
        category: categorySlug ? [categorySlug] : undefined,
        has_rip: hasRip ?? undefined,
        sort,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      }),
    placeholderData: (prev) => prev,
  });

  const total = productsQ.data?.total ?? 0;
  const lastPage = Math.max(0, Math.ceil(total / PAGE_SIZE) - 1);

  return (
    <div className="space-y-5">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Catalog</h1>
        <p className="text-sm text-zinc-600">
          {productsQ.data ? (
            <>
              {total.toLocaleString()} products in {productsQ.data.edition.label}
              {productsQ.data.edition.is_current ? " (current edition)" : ""}.
            </>
          ) : (
            "Loading…"
          )}
        </p>
      </header>

      <div className="flex flex-col md:flex-row gap-3 md:items-center">
        <input
          type="text"
          placeholder="Search code, description, brand…"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(0);
          }}
          className="flex-1 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm focus:border-zinc-900 focus:outline-none"
        />
        <select
          value={categorySlug ?? ""}
          onChange={(e) => {
            setCategorySlug(e.target.value || null);
            setPage(0);
          }}
          className="rounded-md border border-zinc-300 bg-white px-2.5 py-2 text-sm"
        >
          <option value="">All categories</option>
          {(categoriesQ.data ?? [])
            .filter((c) => c.product_count > 0)
            .map((c) => (
              <option key={c.slug} value={c.slug}>
                {c.display_name} ({c.product_count})
              </option>
            ))}
        </select>
        <select
          value={hasRip === null ? "" : hasRip ? "y" : "n"}
          onChange={(e) => {
            const v = e.target.value;
            setHasRip(v === "" ? null : v === "y");
            setPage(0);
          }}
          className="rounded-md border border-zinc-300 bg-white px-2.5 py-2 text-sm"
        >
          <option value="">RIP: any</option>
          <option value="y">RIP: yes</option>
          <option value="n">RIP: no</option>
        </select>
        <select
          value={sort}
          onChange={(e) => {
            setSort(e.target.value as SortKey);
            setPage(0);
          }}
          className="rounded-md border border-zinc-300 bg-white px-2.5 py-2 text-sm"
        >
          <option value="name">Sort by name</option>
          <option value="case_cost_asc">Price (low to high)</option>
          <option value="case_cost_desc">Price (high to low)</option>
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
                <th className="px-4 py-2 text-right">Case</th>
                <th className="px-4 py-2 text-right">Btl</th>
                <th className="px-4 py-2 text-right">Δ MoM</th>
                <th className="px-4 py-2">Top RIP</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {productsQ.isLoading ? (
                <tr><td colSpan={8} className="px-4 py-6 text-center text-zinc-500">Loading…</td></tr>
              ) : productsQ.data?.items.length === 0 ? (
                <tr><td colSpan={8} className="px-4 py-6 text-center text-zinc-500">No products match.</td></tr>
              ) : (
                productsQ.data?.items.map((p) => (
                  <tr key={p.code} className="hover:bg-zinc-50">
                    <td className="px-3 py-2">
                      <FavoriteButton code={p.code} isFavorite={favCodes.has(p.code)} note={favNotes.get(p.code)} showNote />
                    </td>
                    <td className="px-4 py-2 font-mono text-xs">
                      <Link to={`/catalog/${p.code}`} className="text-zinc-700 hover:text-zinc-900 hover:underline">
                        {p.code}
                      </Link>
                    </td>
                    <td className="px-4 py-2">
                      <Link to={`/catalog/${p.code}`} className="hover:underline">
                        {p.description ?? "—"}
                      </Link>
                    </td>
                    <td className="px-4 py-2 text-zinc-600">{p.size ?? "—"}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{money(p.case_cost)}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{money(p.btl_cost)}</td>
                    <td className={`px-4 py-2 text-right tabular-nums ${pctClass(p.case_cost_pct)}`}>
                      {pct(p.case_cost_pct)}
                    </td>
                    <td className="px-4 py-2">
                      {p.has_rip ? (
                        <span className="inline-flex items-center rounded-md bg-amber-50 border border-amber-200 px-2 py-0.5 text-xs font-medium text-amber-800">
                          {p.top_rip_tier ?? "RIP"} · save {money(p.top_rip_save)}
                        </span>
                      ) : null}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <div className="flex items-center justify-between px-4 py-3 border-t border-zinc-200 bg-zinc-50 text-sm">
          <div className="text-zinc-600">
            Page {page + 1} of {lastPage + 1} · {total.toLocaleString()} total
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setPage(Math.max(0, page - 1))}
              disabled={page === 0}
              className="rounded-md border border-zinc-300 bg-white px-2.5 py-1 text-sm disabled:opacity-50"
            >
              Prev
            </button>
            <button
              onClick={() => setPage(Math.min(lastPage, page + 1))}
              disabled={page >= lastPage}
              className="rounded-md border border-zinc-300 bg-white px-2.5 py-1 text-sm disabled:opacity-50"
            >
              Next
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
