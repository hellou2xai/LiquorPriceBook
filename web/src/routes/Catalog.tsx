import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { catalogApi, watchlistApi } from "../lib/api";
import type { Facets } from "../lib/api";
import { money, pct, pctClass } from "../lib/fmt";
import FavoriteButton from "../components/FavoriteButton";

const PAGE_SIZE = 50;

type SortKey = "name" | "case_cost_asc" | "case_cost_desc" | "moved_pct_abs";

// ── Collapsible filter section ──

function FilterSection({
  title,
  defaultOpen = true,
  children,
  count,
}: {
  title: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
  count?: number;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-b border-zinc-100 pb-3">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between py-2 text-left"
      >
        <span className="text-xs font-semibold uppercase tracking-wide text-zinc-700">
          {title}
          {count !== undefined && (
            <span className="ml-1.5 font-normal normal-case text-zinc-400">
              ({count})
            </span>
          )}
        </span>
        <svg
          className={`h-3.5 w-3.5 text-zinc-400 transition-transform ${open ? "" : "-rotate-90"}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {open && <div className="space-y-1">{children}</div>}
    </div>
  );
}

// ── Checkbox filter item ──

function CheckItem({
  label,
  count,
  checked,
  onChange,
}: {
  label: string;
  count?: number;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex cursor-pointer items-center gap-2 rounded px-1 py-0.5 text-sm hover:bg-zinc-50">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="h-3.5 w-3.5 rounded border-zinc-300 text-zinc-900 focus:ring-zinc-500"
      />
      <span className="flex-1 truncate text-zinc-700">{label}</span>
      {count !== undefined && (
        <span className="text-xs tabular-nums text-zinc-400">{count.toLocaleString()}</span>
      )}
    </label>
  );
}

// ── Searchable checkbox list (for brands) ──

function SearchableCheckList({
  items,
  selected,
  onToggle,
  maxVisible = 7,
}: {
  items: { value: string; label: string; count: number }[];
  selected: Set<string>;
  onToggle: (value: string) => void;
  maxVisible?: number;
}) {
  const [search, setSearch] = useState("");
  const [showAll, setShowAll] = useState(false);

  const filtered = useMemo(() => {
    if (!search) return items;
    const q = search.toLowerCase();
    return items.filter((i) => i.label.toLowerCase().includes(q));
  }, [items, search]);

  const visible = showAll ? filtered : filtered.slice(0, maxVisible);
  const hasMore = filtered.length > maxVisible;

  return (
    <div className="space-y-1.5">
      {items.length > maxVisible && (
        <input
          type="text"
          placeholder="Search..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full rounded border border-zinc-200 bg-white px-2 py-1 text-xs placeholder:text-zinc-400 focus:border-zinc-400 focus:outline-none"
        />
      )}
      <div className="max-h-[240px] overflow-y-auto space-y-0.5">
        {visible.map((item) => (
          <CheckItem
            key={item.value}
            label={item.label}
            count={item.count}
            checked={selected.has(item.value)}
            onChange={() => onToggle(item.value)}
          />
        ))}
      </div>
      {hasMore && !showAll && !search && (
        <button
          onClick={() => setShowAll(true)}
          className="text-xs text-zinc-500 hover:text-zinc-700 pl-1"
        >
          Show all {filtered.length}...
        </button>
      )}
      {showAll && !search && (
        <button
          onClick={() => setShowAll(false)}
          className="text-xs text-zinc-500 hover:text-zinc-700 pl-1"
        >
          Show less
        </button>
      )}
    </div>
  );
}

// ── Sidebar filters ──

type Filters = {
  search: string;
  categories: Set<string>;
  brands: Set<string>;
  divisions: Set<string>;
  sizes: Set<string>;
  hasRip: boolean | null;
  minPrice: string;
  maxPrice: string;
  sort: SortKey;
};

const EMPTY_FILTERS: Filters = {
  search: "",
  categories: new Set(),
  brands: new Set(),
  divisions: new Set(),
  sizes: new Set(),
  hasRip: null,
  minPrice: "",
  maxPrice: "",
  sort: "name",
};

function toggleSet(set: Set<string>, val: string): Set<string> {
  const next = new Set(set);
  if (next.has(val)) next.delete(val);
  else next.add(val);
  return next;
}

function FilterSidebar({
  filters,
  onChange,
  facets,
}: {
  filters: Filters;
  onChange: (f: Filters) => void;
  facets: Facets | undefined;
}) {
  const [priceMin, setPriceMin] = useState(filters.minPrice);
  const [priceMax, setPriceMax] = useState(filters.maxPrice);

  const activeCount =
    filters.categories.size +
    filters.brands.size +
    filters.divisions.size +
    filters.sizes.size +
    (filters.hasRip !== null ? 1 : 0) +
    (filters.minPrice ? 1 : 0) +
    (filters.maxPrice ? 1 : 0);

  return (
    <aside className="w-[220px] flex-shrink-0 space-y-1 pr-4">
      <div className="flex items-center justify-between pb-2 border-b border-zinc-200">
        <h2 className="text-sm font-bold text-zinc-800">Filters</h2>
        {activeCount > 0 && (
          <button
            onClick={() => {
              onChange({ ...EMPTY_FILTERS, search: filters.search, sort: filters.sort });
              setPriceMin("");
              setPriceMax("");
            }}
            className="text-[10px] text-red-600 hover:text-red-700 font-medium"
          >
            Clear all ({activeCount})
          </button>
        )}
      </div>

      {/* Deals / RIP */}
      <FilterSection title="Deals" count={facets?.total_with_rip}>
        <CheckItem
          label="Has RIP offer"
          count={facets?.total_with_rip}
          checked={filters.hasRip === true}
          onChange={(v) => onChange({ ...filters, hasRip: v ? true : null })}
        />
        <CheckItem
          label="No RIP"
          checked={filters.hasRip === false}
          onChange={(v) => onChange({ ...filters, hasRip: v ? false : null })}
        />
      </FilterSection>

      {/* Sales Divisions */}
      {facets && facets.divisions.length > 0 && (
        <FilterSection title="Sales Divisions" count={facets.divisions.length}>
          <div className="max-h-[200px] overflow-y-auto space-y-0.5">
            {facets.divisions.map((d) => (
              <CheckItem
                key={d.code}
                label={d.code}
                count={d.product_count}
                checked={filters.divisions.has(d.code)}
                onChange={() =>
                  onChange({ ...filters, divisions: toggleSet(filters.divisions, d.code) })
                }
              />
            ))}
          </div>
        </FilterSection>
      )}

      {/* Price Range */}
      <FilterSection title="Price Range (Case)">
        {facets?.price_min != null && facets?.price_max != null && (
          <p className="text-[10px] text-zinc-400 mb-1">
            {money(facets.price_min)} &ndash; {money(facets.price_max)}
          </p>
        )}
        <div className="flex items-center gap-1.5">
          <input
            type="text"
            inputMode="decimal"
            placeholder="Min"
            value={priceMin}
            onChange={(e) => setPriceMin(e.target.value)}
            className="w-16 rounded border border-zinc-200 px-1.5 py-1 text-xs focus:border-zinc-400 focus:outline-none"
          />
          <span className="text-zinc-400 text-xs">to</span>
          <input
            type="text"
            inputMode="decimal"
            placeholder="Max"
            value={priceMax}
            onChange={(e) => setPriceMax(e.target.value)}
            className="w-16 rounded border border-zinc-200 px-1.5 py-1 text-xs focus:border-zinc-400 focus:outline-none"
          />
          <button
            onClick={() => onChange({ ...filters, minPrice: priceMin, maxPrice: priceMax })}
            className="rounded bg-zinc-800 px-2 py-1 text-[10px] font-medium text-white hover:bg-zinc-700"
          >
            Go
          </button>
        </div>
      </FilterSection>

      {/* Category */}
      <CategoriesFilter filters={filters} onChange={onChange} />

      {/* Brand */}
      <BrandsFilter filters={filters} onChange={onChange} facets={facets} />

      {/* Size */}
      {facets && facets.sizes.length > 0 && (
        <FilterSection title="Size" defaultOpen={false}>
          <SearchableCheckList
            items={facets.sizes.map((s) => ({
              value: s.size,
              label: s.size,
              count: s.product_count,
            }))}
            selected={filters.sizes}
            onToggle={(v) => onChange({ ...filters, sizes: toggleSet(filters.sizes, v) })}
            maxVisible={10}
          />
        </FilterSection>
      )}
    </aside>
  );
}

function CategoriesFilter({
  filters,
  onChange,
}: {
  filters: Filters;
  onChange: (f: Filters) => void;
}) {
  const categoriesQ = useQuery({
    queryKey: ["categories"],
    queryFn: () => catalogApi.categories(),
    staleTime: 5 * 60_000,
  });

  const cats = useMemo(
    () =>
      (categoriesQ.data ?? [])
        .filter((c) => c.product_count > 0)
        .map((c) => ({
          value: c.slug,
          label: c.display_name,
          count: c.product_count,
        })),
    [categoriesQ.data],
  );

  if (cats.length === 0) return null;

  return (
    <FilterSection title="Category" count={cats.length}>
      <SearchableCheckList
        items={cats}
        selected={filters.categories}
        onToggle={(v) =>
          onChange({ ...filters, categories: toggleSet(filters.categories, v) })
        }
      />
    </FilterSection>
  );
}

function BrandsFilter({
  filters,
  onChange,
  facets,
}: {
  filters: Filters;
  onChange: (f: Filters) => void;
  facets: Facets | undefined;
}) {
  const [brandSearch, setBrandSearch] = useState("");
  const [debouncedBrandSearch, setDebouncedBrandSearch] = useState("");

  useMemo(() => {
    const t = setTimeout(() => setDebouncedBrandSearch(brandSearch), 300);
    return () => clearTimeout(t);
  }, [brandSearch]);

  // Server-side brand search when user types
  const brandsQ = useQuery({
    queryKey: ["brands-search", debouncedBrandSearch],
    queryFn: () =>
      catalogApi.brands({
        q: debouncedBrandSearch || undefined,
        limit: 50,
      }),
    staleTime: 60_000,
  });

  const items = useMemo(() => {
    if (debouncedBrandSearch && brandsQ.data) {
      return brandsQ.data.map((b) => ({
        value: b.slug,
        label: b.display_name,
        count: b.product_count,
      }));
    }
    // No search: show top brands from facets
    return (facets?.brands ?? []).slice(0, 15).map((b) => ({
      value: b.slug,
      label: b.display_name,
      count: b.product_count,
    }));
  }, [debouncedBrandSearch, brandsQ.data, facets?.brands]);

  const totalBrands = facets?.brands.length ?? 0;

  return (
    <FilterSection title="Brand" count={totalBrands} defaultOpen={false}>
      <div className="space-y-1.5">
        <input
          type="text"
          placeholder="Search brands..."
          value={brandSearch}
          onChange={(e) => setBrandSearch(e.target.value)}
          className="w-full rounded border border-zinc-200 bg-white px-2 py-1 text-xs placeholder:text-zinc-400 focus:border-zinc-400 focus:outline-none"
        />
        <div className="max-h-[240px] overflow-y-auto space-y-0.5">
          {items.map((item) => (
            <CheckItem
              key={item.value}
              label={item.label}
              count={item.count}
              checked={filters.brands.has(item.value)}
              onChange={() =>
                onChange({
                  ...filters,
                  brands: toggleSet(filters.brands, item.value),
                })
              }
            />
          ))}
          {debouncedBrandSearch && brandsQ.isLoading && (
            <p className="text-[10px] text-zinc-400 pl-1">Searching...</p>
          )}
          {debouncedBrandSearch && !brandsQ.isLoading && items.length === 0 && (
            <p className="text-[10px] text-zinc-400 pl-1">No brands found</p>
          )}
        </div>
      </div>
    </FilterSection>
  );
}

// ══════════════════ Main Component ══════════════════

export default function Catalog() {
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [page, setPage] = useState(0);

  // Debounce search
  useMemo(() => {
    const t = setTimeout(() => setDebouncedSearch(filters.search), 250);
    return () => clearTimeout(t);
  }, [filters.search]);

  const wlQ = useQuery({
    queryKey: ["watchlist"],
    queryFn: () => watchlistApi.list(),
  });
  const favCodes = useMemo(
    () => new Set((wlQ.data ?? []).map((w) => w.product_code)),
    [wlQ.data],
  );
  const favNotes = useMemo(() => {
    const m = new Map<string, string>();
    for (const w of wlQ.data ?? []) if (w.notes) m.set(w.product_code, w.notes);
    return m;
  }, [wlQ.data]);

  const facetsQ = useQuery({
    queryKey: ["catalog-facets"],
    queryFn: () => catalogApi.facets(),
    staleTime: 5 * 60_000,
  });

  const productsQ = useQuery({
    queryKey: [
      "products",
      {
        search: debouncedSearch,
        categories: [...filters.categories],
        brands: [...filters.brands],
        divisions: [...filters.divisions],
        sizes: [...filters.sizes],
        hasRip: filters.hasRip,
        minPrice: filters.minPrice,
        maxPrice: filters.maxPrice,
        sort: filters.sort,
        page,
      },
    ],
    queryFn: () =>
      catalogApi.products({
        search: debouncedSearch || undefined,
        category: filters.categories.size > 0 ? [...filters.categories] : undefined,
        brand: filters.brands.size > 0 ? [...filters.brands] : undefined,
        division: filters.divisions.size > 0 ? [...filters.divisions] : undefined,
        size: filters.sizes.size > 0 ? [...filters.sizes] : undefined,
        has_rip: filters.hasRip ?? undefined,
        min_case_cost: filters.minPrice ? parseFloat(filters.minPrice) : undefined,
        max_case_cost: filters.maxPrice ? parseFloat(filters.maxPrice) : undefined,
        sort: filters.sort,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      }),
    placeholderData: (prev) => prev,
  });

  const total = productsQ.data?.total ?? 0;
  const lastPage = Math.max(0, Math.ceil(total / PAGE_SIZE) - 1);

  function updateFilters(f: Filters) {
    setFilters(f);
    setPage(0);
  }

  return (
    <div className="space-y-5">
      <header className="flex items-start justify-between">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Catalog</h1>
          <p className="text-sm text-zinc-600">
            {productsQ.data ? (
              <>
                {total.toLocaleString()} products in{" "}
                {productsQ.data.edition.label}
                {productsQ.data.edition.is_current ? " (current edition)" : ""}
              </>
            ) : (
              "Loading..."
            )}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={filters.sort}
            onChange={(e) =>
              updateFilters({ ...filters, sort: e.target.value as SortKey })
            }
            className="rounded-md border border-zinc-300 bg-white px-2.5 py-2 text-sm"
          >
            <option value="name">Sort by name</option>
            <option value="case_cost_asc">Price (low to high)</option>
            <option value="case_cost_desc">Price (high to low)</option>
          </select>
        </div>
      </header>

      {/* Search bar */}
      <input
        type="text"
        placeholder="Search code, description, brand..."
        value={filters.search}
        onChange={(e) => setFilters({ ...filters, search: e.target.value })}
        className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm focus:border-zinc-900 focus:outline-none"
      />

      {/* Active filter chips */}
      <ActiveFilterChips filters={filters} onChange={updateFilters} />

      {/* Sidebar + Content */}
      <div className="flex gap-0">
        <FilterSidebar
          filters={filters}
          onChange={updateFilters}
          facets={facetsQ.data}
        />

        {/* Product table */}
        <div className="flex-1 min-w-0">
          <div className="rounded-lg border border-zinc-200 bg-white overflow-hidden">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-zinc-200 text-sm">
                <thead className="bg-zinc-50 text-left text-xs uppercase tracking-wide text-zinc-500">
                  <tr>
                    <th className="px-3 py-2 w-8" />
                    <th className="px-3 py-2">Code</th>
                    <th
                      className={`px-3 py-2 cursor-pointer select-none hover:text-zinc-700 ${filters.sort === "name" ? "text-zinc-900" : ""}`}
                      onClick={() => updateFilters({ ...filters, sort: "name" })}
                    >
                      Description {filters.sort === "name" && <span className="text-[10px]">▲</span>}
                    </th>
                    <th className="px-3 py-2">Size</th>
                    <th
                      className={`px-3 py-2 text-right cursor-pointer select-none hover:text-zinc-700 ${filters.sort.startsWith("case_cost") ? "text-zinc-900" : ""}`}
                      onClick={() => updateFilters({ ...filters, sort: filters.sort === "case_cost_asc" ? "case_cost_desc" : "case_cost_asc" })}
                    >
                      Case {filters.sort === "case_cost_asc" ? <span className="text-[10px]">▲</span> : filters.sort === "case_cost_desc" ? <span className="text-[10px]">▼</span> : null}
                    </th>
                    <th className="px-3 py-2 text-right">Btl</th>
                    <th className="px-3 py-2 text-right">MoM</th>
                    <th className="px-3 py-2">Top RIP</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-100">
                  {productsQ.isLoading ? (
                    <tr>
                      <td colSpan={8} className="px-4 py-6 text-center text-zinc-500">
                        Loading...
                      </td>
                    </tr>
                  ) : productsQ.data?.items.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="px-4 py-6 text-center text-zinc-500">
                        No products match your filters.
                      </td>
                    </tr>
                  ) : (
                    productsQ.data?.items.map((p) => (
                      <tr key={p.code} className="hover:bg-zinc-50">
                        <td className="px-3 py-2">
                          <FavoriteButton
                            code={p.code}
                            isFavorite={favCodes.has(p.code)}
                            note={favNotes.get(p.code)}
                            showNote
                          />
                        </td>
                        <td className="px-3 py-2 font-mono text-xs">
                          <Link
                            to={`/catalog/${p.code}`}
                            className="text-zinc-700 hover:text-zinc-900 hover:underline"
                          >
                            {p.code}
                          </Link>
                        </td>
                        <td className="px-3 py-2">
                          <Link to={`/catalog/${p.code}`} className="hover:underline">
                            {p.description ?? "\u2014"}
                          </Link>
                          {p.divisions && (
                            <span className="ml-2 text-[10px] font-mono text-zinc-400">
                              {p.divisions}
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-zinc-600">{p.size ?? "\u2014"}</td>
                        <td className="px-3 py-2 text-right tabular-nums">
                          {money(p.case_cost)}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums">
                          {money(p.btl_cost)}
                        </td>
                        <td
                          className={`px-3 py-2 text-right tabular-nums ${pctClass(p.case_cost_pct)}`}
                        >
                          {pct(p.case_cost_pct)}
                        </td>
                        <td className="px-3 py-2">
                          {p.has_rip ? (
                            <span className="inline-flex items-center rounded-md bg-amber-50 border border-amber-200 px-2 py-0.5 text-xs font-medium text-amber-800">
                              {p.top_rip_tier ?? "RIP"} &middot; save{" "}
                              {money(p.top_rip_save)}
                            </span>
                          ) : null}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            <div className="flex items-center justify-between px-4 py-3 border-t border-zinc-200 bg-zinc-50 text-sm">
              <div className="text-zinc-600">
                Page {page + 1} of {lastPage + 1} &middot;{" "}
                {total.toLocaleString()} total
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
      </div>
    </div>
  );
}

// ── Active filter chips ──

function ActiveFilterChips({
  filters,
  onChange,
}: {
  filters: Filters;
  onChange: (f: Filters) => void;
}) {
  const chips: { key: string; label: string; onRemove: () => void }[] = [];

  for (const cat of filters.categories) {
    chips.push({
      key: `cat-${cat}`,
      label: `Category: ${cat}`,
      onRemove: () => {
        const next = new Set(filters.categories);
        next.delete(cat);
        onChange({ ...filters, categories: next });
      },
    });
  }
  for (const brand of filters.brands) {
    chips.push({
      key: `brand-${brand}`,
      label: `Brand: ${brand}`,
      onRemove: () => {
        const next = new Set(filters.brands);
        next.delete(brand);
        onChange({ ...filters, brands: next });
      },
    });
  }
  for (const div of filters.divisions) {
    chips.push({
      key: `div-${div}`,
      label: `Division: ${div}`,
      onRemove: () => {
        const next = new Set(filters.divisions);
        next.delete(div);
        onChange({ ...filters, divisions: next });
      },
    });
  }
  for (const sz of filters.sizes) {
    chips.push({
      key: `sz-${sz}`,
      label: `Size: ${sz}`,
      onRemove: () => {
        const next = new Set(filters.sizes);
        next.delete(sz);
        onChange({ ...filters, sizes: next });
      },
    });
  }
  if (filters.hasRip === true) {
    chips.push({
      key: "rip-yes",
      label: "Has RIP",
      onRemove: () => onChange({ ...filters, hasRip: null }),
    });
  } else if (filters.hasRip === false) {
    chips.push({
      key: "rip-no",
      label: "No RIP",
      onRemove: () => onChange({ ...filters, hasRip: null }),
    });
  }
  if (filters.minPrice) {
    chips.push({
      key: "price-min",
      label: `Min: $${filters.minPrice}`,
      onRemove: () => onChange({ ...filters, minPrice: "" }),
    });
  }
  if (filters.maxPrice) {
    chips.push({
      key: "price-max",
      label: `Max: $${filters.maxPrice}`,
      onRemove: () => onChange({ ...filters, maxPrice: "" }),
    });
  }

  if (chips.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-1.5">
      {chips.map((c) => (
        <span
          key={c.key}
          className="inline-flex items-center gap-1 rounded-full bg-zinc-100 border border-zinc-200 px-2.5 py-0.5 text-xs text-zinc-700"
        >
          {c.label}
          <button
            onClick={c.onRemove}
            className="ml-0.5 text-zinc-400 hover:text-zinc-600"
          >
            &times;
          </button>
        </span>
      ))}
      <button
        onClick={() =>
          onChange({
            ...EMPTY_FILTERS,
            search: filters.search,
            sort: filters.sort,
          })
        }
        className="text-xs text-red-600 hover:text-red-700 px-1"
      >
        Clear all
      </button>
    </div>
  );
}
