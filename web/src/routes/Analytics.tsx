import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { analyticsApi, watchlistApi, type AnalyticsView, type AnalyticsRow, type CategoryTrendRow } from "../lib/api";
import SortableTable, { useSort, type Column } from "../components/SortableTable";
import FavoriteButton from "../components/FavoriteButton";
import { useDistributor } from "../lib/distributor";

type ViewCard = {
  view: AnalyticsView;
  label: string;
  desc: string;
  icon: string;
  color: string;
};

const VIEWS: ViewCard[] = [
  {
    view: "price_drops",
    label: "Price Drops",
    desc: "Products with biggest price decreases vs last edition",
    icon: "↓",
    color: "bg-emerald-50 border-emerald-200 text-emerald-700",
  },
  {
    view: "price_increases",
    label: "Price Increases",
    desc: "Products with biggest price increases — buy before next hike",
    icon: "↑",
    color: "bg-red-50 border-red-200 text-red-700",
  },
  {
    view: "new_rips",
    label: "New RIPs",
    desc: "RIP offers added this month — fresh rebate opportunities",
    icon: "$",
    color: "bg-blue-50 border-blue-200 text-blue-700",
  },
  {
    view: "lost_rips",
    label: "Lost RIPs",
    desc: "RIP offers removed — stock up before rebate disappears",
    icon: "!",
    color: "bg-amber-50 border-amber-200 text-amber-700",
  },
  {
    view: "best_value",
    label: "Best Value (After RIP)",
    desc: "Lowest effective cost products with RIP savings applied",
    icon: "*",
    color: "bg-violet-50 border-violet-200 text-violet-700",
  },
  {
    view: "closeout_rip",
    label: "Closeout + RIP",
    desc: "Double savings: closeout discount AND RIP rebate",
    icon: "2x",
    color: "bg-fuchsia-50 border-fuchsia-200 text-fuchsia-700",
  },
  {
    view: "category_trends",
    label: "Category Trends",
    desc: "Average price movement per category between editions",
    icon: "~",
    color: "bg-cyan-50 border-cyan-200 text-cyan-700",
  },
  {
    view: "new_products",
    label: "New Products",
    desc: "Products added to catalog this edition",
    icon: "+",
    color: "bg-lime-50 border-lime-200 text-lime-700",
  },
  {
    view: "discontinued",
    label: "Discontinued",
    desc: "Products removed from catalog — last chance to buy",
    icon: "x",
    color: "bg-stone-50 border-stone-200 text-stone-700",
  },
  {
    view: "watchlist_movers",
    label: "Tracked Movers",
    desc: "Price changes on your tracked/order list products",
    icon: "★",
    color: "bg-yellow-50 border-yellow-200 text-yellow-700",
  },
];

function makeProductColumns(
  favCodes: Set<string>,
  favNotes: Map<string, string>,
  activeView: AnalyticsView | null,
): Column<AnalyticsRow>[] {
  const showComparison = activeView ? COMPARISON_VIEWS.has(activeView) : true;
  const showRip = activeView ? RIP_VIEWS.has(activeView) : true;

  const cols: Column<AnalyticsRow>[] = [
    {
      key: "fav",
      label: "",
      thClassName: "w-8",
      render: (r) => (
        <FavoriteButton code={r.code} isFavorite={favCodes.has(r.code)} note={favNotes.get(r.code)} showNote />
      ),
    },
    {
      key: "code",
      label: "Code",
      sortable: true,
      render: (r) => (
        <Link to={`/catalog/${r.code}`} className="text-brand-navy hover:text-brand-orange hover:underline font-mono text-xs">
          {r.code}
        </Link>
      ),
      sortValue: (r) => r.code,
    },
    {
      key: "description",
      label: "Product",
      sortable: true,
      render: (r) => (
        <span className="text-sm">{r.description ?? "—"}</span>
      ),
      sortValue: (r) => r.description ?? "",
    },
    {
      key: "brand",
      label: "Brand",
      sortable: true,
      hideBelow: "lg",
      render: (r) => <span className="text-xs text-zinc-500">{r.brand ?? "—"}</span>,
      sortValue: (r) => r.brand ?? "",
    },
    {
      key: "category",
      label: "Category",
      sortable: true,
      hideBelow: "md",
      render: (r) => <span className="text-xs text-zinc-500">{r.category ?? "—"}</span>,
      sortValue: (r) => r.category ?? "",
    },
    {
      key: "size",
      label: "Size",
      sortable: false,
      hideBelow: "sm",
      render: (r) => <span className="text-xs">{r.size ?? "—"}</span>,
    },
    {
      key: "case_cost",
      label: "Case $",
      sortable: true,
      align: "right",
      render: (r) => <span className="font-mono text-sm">{r.case_cost ? `$${r.case_cost}` : "—"}</span>,
      sortValue: (r) => (r.case_cost ? parseFloat(r.case_cost) : 0),
    },
  ];

  if (showComparison) {
    cols.push(
      {
        key: "prev_case_cost",
        label: "Prev $",
        sortable: true,
        align: "right",
        hideBelow: "md",
        render: (r) =>
          r.prev_case_cost ? (
            <span className="font-mono text-xs text-zinc-400">${r.prev_case_cost}</span>
          ) : (
            <span className="text-zinc-300">—</span>
          ),
        sortValue: (r) => (r.prev_case_cost ? parseFloat(r.prev_case_cost) : 0),
      },
      {
        key: "pct_change",
        label: "Change",
        sortable: true,
        align: "right",
        render: (r) => {
          if (r.pct_change == null) return <span className="text-zinc-300">—</span>;
          const color = r.pct_change < 0 ? "text-emerald-600" : r.pct_change > 0 ? "text-red-600" : "text-zinc-500";
          return <span className={`text-xs font-medium ${color}`}>{r.pct_change > 0 ? "+" : ""}{r.pct_change}%</span>;
        },
        sortValue: (r) => r.pct_change ?? 0,
      },
    );
  }

  if (showRip) {
    cols.push(
      {
        key: "rip_save",
        label: "RIP Save",
        sortable: true,
        align: "right",
        hideBelow: "sm",
        render: (r) =>
          r.rip_save ? (
            <span className="text-xs text-emerald-600 font-medium">-${r.rip_save}</span>
          ) : (
            <span className="text-zinc-300">—</span>
          ),
        sortValue: (r) => (r.rip_save ? parseFloat(r.rip_save) : 0),
      },
      {
        key: "effective_cost",
        label: "Effective",
        sortable: true,
        align: "right",
        hideBelow: "sm",
        render: (r) =>
          r.effective_cost ? (
            <span className="font-mono text-xs text-emerald-700">${r.effective_cost}</span>
          ) : (
            <span className="text-zinc-300">—</span>
          ),
        sortValue: (r) => (r.effective_cost ? parseFloat(r.effective_cost) : 0),
      },
    );
  }

  if (activeView === "closeout_rip") {
    cols.push({
      key: "closeout_pct",
      label: "Closeout %",
      sortable: true,
      align: "right",
      render: (r) =>
        r.closeout_pct_off != null ? (
          <span className="text-xs font-medium text-fuchsia-600">-{r.closeout_pct_off}%</span>
        ) : (
          <span className="text-zinc-300">—</span>
        ),
      sortValue: (r) => r.closeout_pct_off ?? 0,
    });
  }

  cols.push({
    key: "tag",
    label: "Tag",
    sortable: false,
    hideBelow: "lg",
    render: (r) =>
      r.tag ? (
        <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-brand-navy/5 border border-brand-navy/10 text-brand-navy">
          {r.tag}
        </span>
      ) : null,
  });

  return cols;
}

const categoryColumns: Column<CategoryTrendRow>[] = [
  {
    key: "category",
    label: "Category",
    sortable: true,
    render: (r) => <span className="text-sm font-medium">{r.category}</span>,
    sortValue: (r) => r.category,
  },
  {
    key: "product_count",
    label: "Products",
    sortable: true,
    align: "right",
    render: (r) => <span className="text-sm">{r.product_count}</span>,
    sortValue: (r) => r.product_count,
  },
  {
    key: "avg_case_cost",
    label: "Avg Case $",
    sortable: true,
    align: "right",
    render: (r) => <span className="font-mono text-sm">${r.avg_case_cost}</span>,
    sortValue: (r) => parseFloat(r.avg_case_cost),
  },
  {
    key: "prev_avg",
    label: "Prev Avg $",
    sortable: true,
    align: "right",
    hideBelow: "md",
    render: (r) => <span className="font-mono text-xs text-zinc-400">${r.prev_avg_case_cost}</span>,
    sortValue: (r) => parseFloat(r.prev_avg_case_cost),
  },
  {
    key: "avg_change",
    label: "Avg Change",
    sortable: true,
    align: "right",
    render: (r) => {
      const val = parseFloat(r.avg_change);
      const color = val < 0 ? "text-emerald-600" : val > 0 ? "text-red-600" : "text-zinc-500";
      return <span className={`text-sm font-medium ${color}`}>{val > 0 ? "+" : ""}${r.avg_change}</span>;
    },
    sortValue: (r) => parseFloat(r.avg_change),
  },
  {
    key: "avg_pct_change",
    label: "% Change",
    sortable: true,
    align: "right",
    render: (r) => {
      const color = r.avg_pct_change < 0 ? "text-emerald-600" : r.avg_pct_change > 0 ? "text-red-600" : "text-zinc-500";
      return <span className={`text-xs font-medium ${color}`}>{r.avg_pct_change > 0 ? "+" : ""}{r.avg_pct_change}%</span>;
    },
    sortValue: (r) => r.avg_pct_change,
  },
  {
    key: "drops",
    label: "Drops",
    sortable: true,
    align: "right",
    hideBelow: "sm",
    render: (r) => <span className="text-xs text-emerald-600">{r.drops}</span>,
    sortValue: (r) => r.drops,
  },
  {
    key: "increases",
    label: "Increases",
    sortable: true,
    align: "right",
    hideBelow: "sm",
    render: (r) => <span className="text-xs text-red-600">{r.increases}</span>,
    sortValue: (r) => r.increases,
  },
];

// Views where % change filter makes sense
const PCT_VIEWS = new Set<AnalyticsView>([
  "price_drops", "price_increases", "watchlist_movers",
  "best_value",
]);

// Views that compare editions (show Prev $ and Change columns)
const COMPARISON_VIEWS = new Set<AnalyticsView>([
  "price_drops", "price_increases", "watchlist_movers", "best_value",
]);

// Views that show RIP data columns
const RIP_VIEWS = new Set<AnalyticsView>([
  "new_rips", "lost_rips", "best_value", "closeout_rip",
]);

export default function Analytics() {
  const [activeView, setActiveView] = useState<AnalyticsView | null>(null);

  // Filters (reset when view changes)
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [brandFilter, setBrandFilter] = useState("");
  const [divisionFilter, setDivisionFilter] = useState("");
  const [minPct, setMinPct] = useState(0);

  // Watchlist for favorite state
  const wlQ = useQuery({ queryKey: ["watchlist"], queryFn: () => watchlistApi.list() });
  const favCodes = useMemo(() => new Set((wlQ.data ?? []).map((w) => w.product_code)), [wlQ.data]);
  const favNotes = useMemo(() => {
    const m = new Map<string, string>();
    for (const w of wlQ.data ?? []) if (w.notes) m.set(w.product_code, w.notes);
    return m;
  }, [wlQ.data]);

  const productColumns = useMemo(
    () => makeProductColumns(favCodes, favNotes, activeView),
    [favCodes, favNotes, activeView],
  );

  const { distributor } = useDistributor();

  const { data, isLoading, error } = useQuery({
    queryKey: ["analytics", activeView, distributor],
    queryFn: () => analyticsApi.query(activeView!, 500, distributor),
    enabled: activeView !== null,
  });

  const productSort = useSort<AnalyticsRow>({ key: "pct_change", direction: "asc" });
  const categorySort = useSort<CategoryTrendRow>({ key: "avg_pct_change", direction: "asc" });

  const isCategoryView = activeView === "category_trends";

  // Extract unique filter values from product rows
  const facets = useMemo(() => {
    const rows = data?.rows ?? [];
    const cats = new Set<string>();
    const brands = new Set<string>();
    const divs = new Set<string>();
    for (const r of rows) {
      if (r.category) cats.add(r.category);
      if (r.brand) brands.add(r.brand);
      if (r.divisions) {
        for (const d of r.divisions.split(/\s+/)) {
          if (d.trim()) divs.add(d.trim());
        }
      }
    }
    return {
      categories: [...cats].sort(),
      brands: [...brands].sort(),
      divisions: [...divs].sort(),
    };
  }, [data?.rows]);

  // Filtered product rows
  const filteredRows = useMemo(() => {
    let rows = data?.rows ?? [];
    if (search) {
      const q = search.toLowerCase();
      rows = rows.filter(
        (r) =>
          r.code.toLowerCase().includes(q) ||
          (r.description ?? "").toLowerCase().includes(q) ||
          (r.brand ?? "").toLowerCase().includes(q),
      );
    }
    if (categoryFilter) {
      rows = rows.filter((r) => r.category === categoryFilter);
    }
    if (brandFilter) {
      rows = rows.filter((r) => r.brand === brandFilter);
    }
    if (divisionFilter) {
      rows = rows.filter(
        (r) => r.divisions && r.divisions.includes(divisionFilter),
      );
    }
    if (minPct > 0) {
      rows = rows.filter(
        (r) => r.pct_change != null && Math.abs(r.pct_change) >= minPct,
      );
    }
    return rows;
  }, [data?.rows, search, categoryFilter, brandFilter, divisionFilter, minPct]);

  // Filtered category rows (only search applies)
  const filteredCatRows = useMemo(() => {
    let rows = data?.category_rows ?? [];
    if (search) {
      const q = search.toLowerCase();
      rows = rows.filter((r) => r.category.toLowerCase().includes(q));
    }
    if (minPct > 0) {
      rows = rows.filter(
        (r) => Math.abs(r.avg_pct_change) >= minPct,
      );
    }
    return rows;
  }, [data?.category_rows, search, minPct]);

  // Summary stats for product views
  const stats = useMemo(() => {
    if (isCategoryView || filteredRows.length === 0) return null;
    const withPct = filteredRows.filter((r) => r.pct_change != null);
    const avgPct = withPct.length > 0
      ? withPct.reduce((s, r) => s + (r.pct_change ?? 0), 0) / withPct.length
      : null;
    const withRip = filteredRows.filter((r) => r.rip_save != null);
    const totalRipSave = withRip.reduce(
      (s, r) => s + parseFloat(r.rip_save ?? "0"), 0,
    );
    return {
      shown: filteredRows.length,
      total: data?.total ?? 0,
      avgPct,
      ripCount: withRip.length,
      totalRipSave,
    };
  }, [filteredRows, data?.total, isCategoryView]);

  const handleViewClick = (view: AnalyticsView) => {
    setActiveView(view);
    // Reset filters on view change
    setSearch("");
    setCategoryFilter("");
    setBrandFilter("");
    setDivisionFilter("");
    setMinPct(0);
  };

  const hasActiveFilters = search || categoryFilter || brandFilter || divisionFilter || minPct > 0;

  const clearFilters = () => {
    setSearch("");
    setCategoryFilter("");
    setBrandFilter("");
    setDivisionFilter("");
    setMinPct(0);
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-brand-navy">Pricing Analytics</h1>
          <p className="text-sm text-zinc-500 mt-1">
            Compare pricing across editions. Click an analysis to run it.
          </p>
        </div>
        {data && (
          <div className="text-xs text-zinc-400">
            Comparing {data.edition_current}
            {data.edition_previous ? ` vs ${data.edition_previous}` : ""}
          </div>
        )}
      </div>

      {/* Smart Button Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
        {VIEWS.map((v) => (
          <button
            key={v.view}
            onClick={() => handleViewClick(v.view)}
            className={`text-left p-3 rounded-lg border transition-all ${
              activeView === v.view
                ? `${v.color} ring-2 ring-offset-1 ring-current`
                : "border-zinc-200 hover:border-zinc-300 hover:bg-brand-tan"
            }`}
          >
            <div className="flex items-center gap-2 mb-1">
              <span className={`text-lg font-bold ${activeView === v.view ? "" : "text-zinc-400"}`}>
                {v.icon}
              </span>
              <span className="text-sm font-semibold leading-tight">{v.label}</span>
            </div>
            <p className="text-[11px] text-zinc-500 leading-snug">{v.desc}</p>
          </button>
        ))}
      </div>

      {/* Results */}
      {activeView && (
        <>
          {/* Stats bar */}
          {stats && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="rounded-xl shadow-sm border border-zinc-200 bg-white px-3 py-2">
                <div className="text-xs text-zinc-500">Results</div>
                <div className="text-lg font-semibold text-brand-navy">
                  {stats.shown}
                  {stats.shown !== stats.total && (
                    <span className="text-xs font-normal text-zinc-400"> / {stats.total}</span>
                  )}
                </div>
              </div>
              {stats.avgPct != null && (
                <div className={`rounded-lg border px-3 py-2 ${
                  stats.avgPct < 0
                    ? "border-emerald-200 bg-emerald-50"
                    : stats.avgPct > 0
                      ? "border-red-200 bg-red-50"
                      : "border-zinc-200 bg-white"
                }`}>
                  <div className={`text-xs ${
                    stats.avgPct < 0 ? "text-emerald-600" : stats.avgPct > 0 ? "text-red-600" : "text-zinc-500"
                  }`}>Avg Change</div>
                  <div className={`text-lg font-semibold ${
                    stats.avgPct < 0 ? "text-emerald-800" : stats.avgPct > 0 ? "text-red-800" : "text-zinc-900"
                  }`}>
                    {stats.avgPct > 0 ? "+" : ""}{stats.avgPct.toFixed(1)}%
                  </div>
                </div>
              )}
              {stats.ripCount > 0 && (
                <div className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-2">
                  <div className="text-xs text-blue-600">With RIP</div>
                  <div className="text-lg font-semibold text-blue-800">{stats.ripCount}</div>
                </div>
              )}
              {stats.totalRipSave > 0 && (
                <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2">
                  <div className="text-xs text-emerald-600">Total RIP Savings</div>
                  <div className="text-lg font-semibold text-emerald-800">
                    ${stats.totalRipSave.toFixed(2)}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Filters bar */}
          {data && !isLoading && (
            <div className="flex flex-col sm:flex-row flex-wrap gap-3 items-start sm:items-center">
              <input
                type="text"
                placeholder={isCategoryView ? "Search category..." : "Search SKU, description, brand..."}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full sm:w-64 rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm placeholder:text-zinc-400 focus:border-brand-orange focus:outline-none"
              />

              {!isCategoryView && facets.categories.length > 1 && (
                <select
                  value={categoryFilter}
                  onChange={(e) => setCategoryFilter(e.target.value)}
                  className="rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm"
                >
                  <option value="">All categories</option>
                  {facets.categories.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              )}

              {!isCategoryView && facets.brands.length > 1 && (
                <select
                  value={brandFilter}
                  onChange={(e) => setBrandFilter(e.target.value)}
                  className="rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm"
                >
                  <option value="">All brands</option>
                  {facets.brands.map((b) => (
                    <option key={b} value={b}>{b}</option>
                  ))}
                </select>
              )}

              {!isCategoryView && facets.divisions.length > 1 && (
                <select
                  value={divisionFilter}
                  onChange={(e) => setDivisionFilter(e.target.value)}
                  className="rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm"
                >
                  <option value="">All divisions</option>
                  {facets.divisions.map((d) => (
                    <option key={d} value={d}>{d}</option>
                  ))}
                </select>
              )}

              {(isCategoryView || (activeView && PCT_VIEWS.has(activeView))) && (
                <label className="text-sm text-zinc-700 flex items-center gap-2">
                  Min %
                  <input
                    type="number"
                    value={minPct}
                    onChange={(e) => setMinPct(parseFloat(e.target.value) || 0)}
                    min={0}
                    max={100}
                    step={1}
                    className="w-16 rounded-md border border-zinc-300 bg-white px-2 py-1 text-sm"
                  />
                </label>
              )}

              {hasActiveFilters && (
                <button
                  onClick={clearFilters}
                  className="text-xs text-zinc-500 hover:text-zinc-800 underline"
                >
                  Clear filters
                </button>
              )}
            </div>
          )}

          {/* Table */}
          <div className="bg-white border border-zinc-200 rounded-xl shadow-sm overflow-hidden">
            {isLoading && (
              <div className="p-8 text-center text-zinc-400">Loading analysis...</div>
            )}

            {error && (
              <div className="p-8 text-center text-red-500">
                {error instanceof Error ? error.message : "Failed to load"}
              </div>
            )}

            {data && !isLoading && (
              <>
                <div className="px-4 py-3 border-b border-zinc-100 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1">
                  <h2 className="font-semibold text-sm">
                    {VIEWS.find((v) => v.view === activeView)?.label}
                    <span className="ml-2 text-zinc-400 font-normal">
                      {isCategoryView ? filteredCatRows.length : filteredRows.length} results
                      {hasActiveFilters && (
                        <> (filtered from {data.total})</>
                      )}
                    </span>
                  </h2>
                  <span className="text-xs text-zinc-400">
                    {data.edition_current}
                    {data.edition_previous ? ` vs ${data.edition_previous}` : ""}
                  </span>
                </div>

                {isCategoryView && filteredCatRows.length > 0 ? (
                  <SortableTable
                    data={categorySort.sorted(filteredCatRows, categoryColumns)}
                    columns={categoryColumns}
                    sort={categorySort.sort}
                    onSort={categorySort.toggle}
                    rowKey={(r) => r.category}
                    emptyMessage="No categories match your filters."
                  />
                ) : !isCategoryView && filteredRows.length > 0 ? (
                  <SortableTable
                    data={productSort.sorted(filteredRows, productColumns)}
                    columns={productColumns}
                    sort={productSort.sort}
                    onSort={productSort.toggle}
                    rowKey={(r) => r.code}
                    emptyMessage="No products match your filters."
                  />
                ) : (
                  <div className="p-8 text-center text-zinc-400 text-sm">
                    {hasActiveFilters
                      ? "No results match your filters."
                      : <>No results for this analysis.
                          {!data.edition_previous && " Only one edition available — comparison requires two editions."}
                        </>
                    }
                  </div>
                )}
              </>
            )}
          </div>
        </>
      )}

      {!activeView && (
        <div className="text-center py-12 text-zinc-400 text-sm">
          Select an analysis above to compare pricing across editions.
        </div>
      )}
    </div>
  );
}
