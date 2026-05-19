import { useState, useMemo, useRef } from "react";
import { Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import { watchlistApi } from "../lib/api";
import type { OrderItem } from "../lib/api";
import { money } from "../lib/fmt";
import FavoriteButton from "../components/FavoriteButton";

type SortKey = "name" | "price_asc" | "price_desc" | "rip_save";

function sortItems(items: OrderItem[], key: SortKey): OrderItem[] {
  const copy = [...items];
  switch (key) {
    case "name":
      return copy.sort((a, b) => (a.description ?? "").localeCompare(b.description ?? ""));
    case "price_asc":
      return copy.sort((a, b) => (parseFloat(a.case_cost ?? "999999") - parseFloat(b.case_cost ?? "999999")));
    case "price_desc":
      return copy.sort((a, b) => (parseFloat(b.case_cost ?? "0") - parseFloat(a.case_cost ?? "0")));
    case "rip_save":
      return copy.sort((a, b) => (parseFloat(b.rip_save_amount ?? "0") - parseFloat(a.rip_save_amount ?? "0")));
    default:
      return copy;
  }
}

type CartQty = { bottles: number; cases: number };

function InlineNote({ code, initial }: { code: string; initial: string | null }) {
  const qc = useQueryClient();
  const [value, setValue] = useState(initial ?? "");
  const savedRef = useRef(initial ?? "");
  const [flash, setFlash] = useState(false);

  const update = useMutation({
    mutationFn: (notes: string) => watchlistApi.update(code, { notes: notes || null }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["watchlist"] });
      qc.invalidateQueries({ queryKey: ["watchlist-order"] });
      setFlash(true);
      setTimeout(() => setFlash(false), 1500);
    },
  });

  function handleBlur() {
    if (value !== savedRef.current) {
      savedRef.current = value;
      update.mutate(value);
    }
  }

  return (
    <div className="relative">
      <input
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onBlur={handleBlur}
        placeholder="Add note..."
        className="w-full min-w-[100px] rounded border border-transparent bg-transparent px-1.5 py-0.5 text-xs text-zinc-600 placeholder:text-zinc-300 hover:border-zinc-200 focus:border-zinc-400 focus:bg-white focus:outline-none"
      />
      {flash && (
        <span className="absolute -top-4 left-0 text-[10px] text-emerald-600 font-medium animate-pulse">
          Saved
        </span>
      )}
    </div>
  );
}

export default function Watchlist() {
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState<string>("");
  const [sort, setSort] = useState<SortKey>("name");
  const [cart, setCart] = useState<Map<string, CartQty>>(new Map());

  // Debounce search
  useMemo(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 250);
    return () => clearTimeout(t);
  }, [search]);

  const q = useQuery({
    queryKey: ["watchlist-order", { search: debouncedSearch, category: categoryFilter, sort }],
    queryFn: () =>
      watchlistApi.order({
        search: debouncedSearch || undefined,
        category: categoryFilter || undefined,
        sort: sort === "name" ? undefined : sort,
      }),
    placeholderData: (prev) => prev,
  });

  const items = useMemo(() => {
    if (!q.data) return [];
    return sortItems(q.data, sort);
  }, [q.data, sort]);

  const categories = useMemo(() => {
    if (!q.data) return [];
    const set = new Set<string>();
    for (const item of q.data) {
      if (item.category_display) set.add(item.category_display);
    }
    return [...set].sort();
  }, [q.data]);

  // Cart helpers
  function getQty(code: string): CartQty {
    return cart.get(code) ?? { bottles: 0, cases: 0 };
  }

  function setQty(code: string, update: Partial<CartQty>) {
    setCart((prev) => {
      const next = new Map(prev);
      const cur = prev.get(code) ?? { bottles: 0, cases: 0 };
      next.set(code, { ...cur, ...update });
      return next;
    });
  }

  // Summary calculations
  const summary = useMemo(() => {
    let totalItems = 0;
    let totalCost = 0;
    for (const item of items) {
      const qty = cart.get(item.product_code);
      if (!qty) continue;
      const { bottles, cases } = qty;
      if (bottles + cases === 0) continue;
      totalItems += bottles + cases;
      const btlPrice = parseFloat(item.effective_btl ?? item.btl_cost ?? "0");
      const casePrice = parseFloat(item.effective_case ?? item.case_cost ?? "0");
      totalCost += bottles * btlPrice + cases * casePrice;
    }
    return { totalItems, totalCost };
  }, [items, cart]);

  return (
    <div className="space-y-5">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">My Order List</h1>
        <p className="text-sm text-zinc-600">
          {q.data
            ? `${q.data.length} saved product${q.data.length === 1 ? "" : "s"}`
            : "Loading..."}
        </p>
      </header>

      {/* Filters */}
      <div className="flex flex-col md:flex-row gap-3 md:items-center">
        <input
          type="text"
          placeholder="Search products..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm focus:border-zinc-900 focus:outline-none"
        />
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="rounded-md border border-zinc-300 bg-white px-2.5 py-2 text-sm"
        >
          <option value="">All categories</option>
          {categories.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value as SortKey)}
          className="rounded-md border border-zinc-300 bg-white px-2.5 py-2 text-sm"
        >
          <option value="name">Product A-Z</option>
          <option value="price_asc">Price low-high</option>
          <option value="price_desc">Price high-low</option>
          <option value="rip_save">Best RIP savings</option>
        </select>
      </div>

      {/* Table */}
      <div className="rounded-lg border border-zinc-200 bg-white overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-zinc-200 text-sm">
            <thead className="bg-zinc-50 text-left text-xs uppercase tracking-wide text-zinc-500">
              <tr>
                <th className="px-3 py-2 w-8"></th>
                <th className="px-3 py-2">Product</th>
                <th className="px-3 py-2">Category</th>
                <th className="px-3 py-2">Brand</th>
                <th className="px-3 py-2 text-right">Case</th>
                <th className="px-3 py-2 text-right">Btl</th>
                <th className="px-3 py-2">RIP Details</th>
                <th className="px-3 py-2 text-right">Eff. Case</th>
                <th className="px-3 py-2 text-right">Eff. Btl</th>
                <th className="px-3 py-2">Note</th>
                <th className="px-3 py-2 text-center">Qty in Cart</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {q.isLoading ? (
                <tr>
                  <td colSpan={11} className="px-4 py-6 text-center text-zinc-500">Loading...</td>
                </tr>
              ) : items.length === 0 ? (
                <tr>
                  <td colSpan={11} className="px-4 py-6 text-center text-zinc-500">
                    No items yet. Browse the <Link to="/catalog" className="text-zinc-900 underline">Catalog</Link> and star products to add them.
                  </td>
                </tr>
              ) : (
                items.map((item) => {
                  const qty = getQty(item.product_code);
                  const hasRipPrice = item.has_rip && item.effective_case;
                  return (
                    <tr key={item.product_code} className="hover:bg-zinc-50 align-top">
                      {/* Star (remove) */}
                      <td className="px-3 py-2">
                        <FavoriteButton code={item.product_code} isFavorite={true} />
                      </td>

                      {/* Product info */}
                      <td className="px-3 py-2">
                        <Link to={`/catalog/${item.product_code}`} className="hover:underline font-medium text-zinc-900">
                          {item.description ?? "Unknown"}
                        </Link>
                        <div className="text-xs text-zinc-500 mt-0.5">
                          {item.size ?? ""}{item.pack ? ` / ${item.pack}pk` : ""} · SKU {item.product_code}
                        </div>
                      </td>

                      {/* Category */}
                      <td className="px-3 py-2 text-zinc-600">{item.category_display ?? "\u2014"}</td>

                      {/* Brand */}
                      <td className="px-3 py-2 text-zinc-600">{item.brand_display ?? "\u2014"}</td>

                      {/* Current price */}
                      <td className="px-3 py-2 text-right tabular-nums">{money(item.case_cost)}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{money(item.btl_cost)}</td>

                      {/* RIP */}
                      <td className="px-3 py-2">
                        {item.has_rip && item.rip_tier ? (
                          <div>
                            <span className="inline-flex items-center rounded-md bg-amber-50 border border-amber-200 px-2 py-0.5 text-xs font-medium text-amber-800">
                              {item.rip_tier_cases ?? ""}CS
                            </span>
                            <span className="ml-1.5 text-xs text-emerald-700 font-medium">
                              save {money(item.rip_save_amount)}
                            </span>
                          </div>
                        ) : (
                          <span className="text-zinc-400">{"\u2014"}</span>
                        )}
                      </td>

                      {/* Effective price */}
                      <td className={`px-3 py-2 text-right tabular-nums ${hasRipPrice ? "text-emerald-700 font-medium" : ""}`}>
                        {money(item.effective_case ?? item.case_cost)}
                      </td>
                      <td className={`px-3 py-2 text-right tabular-nums ${hasRipPrice ? "text-emerald-700 font-medium" : ""}`}>
                        {money(item.effective_btl ?? item.btl_cost)}
                      </td>

                      {/* Inline editable note */}
                      <td className="px-3 py-2">
                        <InlineNote code={item.product_code} initial={item.notes} />
                      </td>

                      {/* Qty selectors */}
                      <td className="px-3 py-2">
                        <div className="flex flex-col gap-1 text-xs">
                          {/* Bottles */}
                          <div className="flex items-center gap-1.5">
                            <span className="w-10 text-zinc-500">Btl</span>
                            <button
                              onClick={() => setQty(item.product_code, { bottles: Math.max(0, qty.bottles - 1) })}
                              className="rounded border border-zinc-300 bg-white w-6 h-6 flex items-center justify-center hover:bg-zinc-100 disabled:opacity-40"
                              disabled={qty.bottles === 0}
                            >-</button>
                            <span className="w-6 text-center tabular-nums font-medium">{qty.bottles}</span>
                            <button
                              onClick={() => setQty(item.product_code, { bottles: qty.bottles + 1 })}
                              className="rounded border border-zinc-300 bg-white w-6 h-6 flex items-center justify-center hover:bg-zinc-100"
                            >+</button>
                          </div>
                          {/* Cases */}
                          <div className="flex items-center gap-1.5">
                            <span className="w-10 text-zinc-500">Case</span>
                            <button
                              onClick={() => setQty(item.product_code, { cases: Math.max(0, qty.cases - 1) })}
                              className="rounded border border-zinc-300 bg-white w-6 h-6 flex items-center justify-center hover:bg-zinc-100 disabled:opacity-40"
                              disabled={qty.cases === 0}
                            >-</button>
                            <span className="w-6 text-center tabular-nums font-medium">{qty.cases}</span>
                            <button
                              onClick={() => setQty(item.product_code, { cases: qty.cases + 1 })}
                              className="rounded border border-zinc-300 bg-white w-6 h-6 flex items-center justify-center hover:bg-zinc-100"
                            >+</button>
                          </div>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Summary bar */}
        {summary.totalItems > 0 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-zinc-200 bg-zinc-50 text-sm">
            <div className="text-zinc-700 font-medium">
              {summary.totalItems} item{summary.totalItems === 1 ? "" : "s"} in cart
            </div>
            <div className="text-zinc-900 font-semibold tabular-nums">
              Estimated total: {money(summary.totalCost)}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
