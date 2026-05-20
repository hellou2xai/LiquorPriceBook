import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  analyticsApi, watchlistApi,
  type AnalyticsView, type AnalyticsRow, type CategoryTrendRow,
  type CrossCategoryRow, type CrossRipRow, type CrossBrandRow, type CrossPriceRow,
} from "../lib/api";
import SortableTable, { useSort, type Column } from "../components/SortableTable";
import FavoriteButton from "../components/FavoriteButton";

// -- View definitions --------------------------------------------------------

type ViewCard = {
  view: AnalyticsView;
  label: string;
  desc: string;
  icon: string;
  color: string;
  group: "single" | "cross";
};

const VIEWS: ViewCard[] = [
  // Single-distributor views
  { view: "price_drops", label: "Price Drops", desc: "Biggest price decreases vs last edition", icon: "↓", color: "bg-emerald-50 border-emerald-200 text-emerald-700", group: "single" },
  { view: "price_increases", label: "Price Increases", desc: "Biggest price increases — buy before next hike", icon: "↑", color: "bg-red-50 border-red-200 text-red-700", group: "single" },
  { view: "new_rips", label: "New RIPs", desc: "RIP offers added this month", icon: "$", color: "bg-blue-50 border-blue-200 text-blue-700", group: "single" },
  { view: "lost_rips", label: "Lost RIPs", desc: "RIP offers removed this month", icon: "!", color: "bg-amber-50 border-amber-200 text-amber-700", group: "single" },
  { view: "best_value", label: "Best Value", desc: "Lowest effective cost with RIP applied", icon: "*", color: "bg-violet-50 border-violet-200 text-violet-700", group: "single" },
  { view: "closeout_rip", label: "Closeout + RIP", desc: "Double savings: closeout + RIP rebate", icon: "2x", color: "bg-fuchsia-50 border-fuchsia-200 text-fuchsia-700", group: "single" },
  { view: "category_trends", label: "Category Trends", desc: "Avg price movement per category", icon: "~", color: "bg-cyan-50 border-cyan-200 text-cyan-700", group: "single" },
  { view: "new_products", label: "New Products", desc: "Products added this edition", icon: "+", color: "bg-lime-50 border-lime-200 text-lime-700", group: "single" },
  { view: "discontinued", label: "Discontinued", desc: "Products removed from catalog", icon: "x", color: "bg-stone-50 border-stone-200 text-stone-700", group: "single" },
  { view: "watchlist_movers", label: "Tracked Movers", desc: "Price changes on tracked products", icon: "★", color: "bg-yellow-50 border-yellow-200 text-yellow-700", group: "single" },
  // Cross-distributor views
  { view: "cross_category_compare", label: "Category Compare", desc: "Avg price per category across distributors", icon: "⇔", color: "bg-indigo-50 border-indigo-200 text-indigo-700", group: "cross" },
  { view: "cross_rip_coverage", label: "RIP Coverage", desc: "RIP offer coverage comparison by category", icon: "%", color: "bg-teal-50 border-teal-200 text-teal-700", group: "cross" },
  { view: "cross_brand_availability", label: "Brand Availability", desc: "Brand presence comparison across distributors", icon: "B", color: "bg-orange-50 border-orange-200 text-orange-700", group: "cross" },
  { view: "cross_price_compare", label: "Price Compare", desc: "Matched product prices across distributors", icon: "$$", color: "bg-pink-50 border-pink-200 text-pink-700", group: "cross" },
];

const SINGLE_VIEWS = VIEWS.filter((v) => v.group === "single");
const CROSS_VIEWS_LIST = VIEWS.filter((v) => v.group === "cross");

const PCT_VIEWS = new Set<AnalyticsView>(["price_drops", "price_increases", "watchlist_movers", "best_value"]);
const COMPARISON_VIEWS = new Set<AnalyticsView>(["price_drops", "price_increases", "watchlist_movers", "best_value"]);
const RIP_VIEWS = new Set<AnalyticsView>(["new_rips", "lost_rips", "best_value", "closeout_rip"]);
const CROSS_VIEW_SET = new Set<AnalyticsView>(["cross_category_compare", "cross_rip_coverage", "cross_brand_availability", "cross_price_compare"]);

type DistMode = "allied" | "fedway" | "all" | "compare";

function distSlug(mode: DistMode): string {
  if (mode === "allied") return "nj-allied";
  if (mode === "fedway") return "nj-fedway";
  return "all";
}

// -- Product columns ---------------------------------------------------------

function makeProductColumns(
  favCodes: Set<string>,
  favNotes: Map<string, string>,
  activeView: AnalyticsView | null,
  showDistributor: boolean,
): Column<AnalyticsRow>[] {
  const showComparison = activeView ? COMPARISON_VIEWS.has(activeView) : true;
  const showRip = activeView ? RIP_VIEWS.has(activeView) : true;

  const cols: Column<AnalyticsRow>[] = [
    {
      key: "fav", label: "", thClassName: "w-8",
      render: (r) => <FavoriteButton code={r.code} distributor={r.distributor_slug ?? undefined} isFavorite={favCodes.has(r.code)} note={favNotes.get(r.code)} showNote />,
    },
    {
      key: "code", label: "Code", sortable: true,
      render: (r) => (
        <Link to={`/catalog/${r.code}${r.distributor_slug ? `?d=${r.distributor_slug}` : ""}`} className="text-brand-navy hover:text-brand-orange hover:underline font-mono text-xs">
          {r.code}
        </Link>
      ),
      sortValue: (r) => r.code,
    },
    {
      key: "description", label: "Product", sortable: true,
      render: (r) => <span className="text-sm">{r.description ?? "—"}</span>,
      sortValue: (r) => r.description ?? "",
    },
  ];

  if (showDistributor) {
    cols.push({
      key: "distributor", label: "Dist.", sortable: true, hideBelow: "lg",
      render: (r) => (
        <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold ${
          r.distributor_slug === "nj-allied"
            ? "bg-blue-50 text-blue-700 border border-blue-200"
            : "bg-purple-50 text-purple-700 border border-purple-200"
        }`}>
          {r.distributor_name ?? r.distributor_slug ?? "—"}
        </span>
      ),
      sortValue: (r) => r.distributor_name ?? "",
    });
  }

  cols.push(
    { key: "brand", label: "Brand", sortable: true, hideBelow: "lg", render: (r) => <span className="text-xs text-zinc-500">{r.brand ?? "—"}</span>, sortValue: (r) => r.brand ?? "" },
    { key: "category", label: "Category", sortable: true, hideBelow: "md", render: (r) => <span className="text-xs text-zinc-500">{r.category ?? "—"}</span>, sortValue: (r) => r.category ?? "" },
    { key: "size", label: "Size", sortable: false, hideBelow: "sm", render: (r) => <span className="text-xs">{r.size ?? "—"}</span> },
    { key: "case_cost", label: "Case $", sortable: true, align: "right" as const, render: (r) => <span className="font-mono text-sm">{r.case_cost ? `$${r.case_cost}` : "—"}</span>, sortValue: (r) => (r.case_cost ? parseFloat(r.case_cost) : 0) },
  );

  if (showComparison) {
    cols.push(
      {
        key: "prev_case_cost", label: "Prev $", sortable: true, align: "right" as const, hideBelow: "md",
        render: (r) => r.prev_case_cost ? <span className="font-mono text-xs text-zinc-400">${r.prev_case_cost}</span> : <span className="text-zinc-300">—</span>,
        sortValue: (r) => (r.prev_case_cost ? parseFloat(r.prev_case_cost) : 0),
      },
      {
        key: "pct_change", label: "Change", sortable: true, align: "right" as const,
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
        key: "rip_save", label: "RIP Save", sortable: true, align: "right" as const, hideBelow: "sm",
        render: (r) => r.rip_save ? <span className="text-xs text-emerald-600 font-medium">-${r.rip_save}</span> : <span className="text-zinc-300">—</span>,
        sortValue: (r) => (r.rip_save ? parseFloat(r.rip_save) : 0),
      },
      {
        key: "effective_cost", label: "Effective", sortable: true, align: "right" as const, hideBelow: "sm",
        render: (r) => r.effective_cost ? <span className="font-mono text-xs text-emerald-700">${r.effective_cost}</span> : <span className="text-zinc-300">—</span>,
        sortValue: (r) => (r.effective_cost ? parseFloat(r.effective_cost) : 0),
      },
    );
  }

  if (activeView === "closeout_rip") {
    cols.push({
      key: "closeout_pct", label: "Closeout %", sortable: true, align: "right" as const,
      render: (r) => r.closeout_pct_off != null ? <span className="text-xs font-medium text-fuchsia-600">-{r.closeout_pct_off}%</span> : <span className="text-zinc-300">—</span>,
      sortValue: (r) => r.closeout_pct_off ?? 0,
    });
  }

  cols.push({
    key: "tag", label: "Tag", sortable: false, hideBelow: "lg",
    render: (r) => r.tag ? <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-brand-navy/5 border border-brand-navy/10 text-brand-navy">{r.tag}</span> : null,
  });

  return cols;
}

// -- Category trend columns --------------------------------------------------

const categoryColumns: Column<CategoryTrendRow>[] = [
  { key: "category", label: "Category", sortable: true, render: (r) => <span className="text-sm font-medium">{r.category}</span>, sortValue: (r) => r.category },
  { key: "distributor", label: "Dist.", sortable: true, hideBelow: "lg", render: (r) => r.distributor_name ? <span className="text-[10px] text-zinc-500">{r.distributor_name}</span> : null, sortValue: (r) => r.distributor_name ?? "" },
  { key: "product_count", label: "Products", sortable: true, align: "right", render: (r) => <span className="text-sm">{r.product_count}</span>, sortValue: (r) => r.product_count },
  { key: "avg_case_cost", label: "Avg Case $", sortable: true, align: "right", render: (r) => <span className="font-mono text-sm">${r.avg_case_cost}</span>, sortValue: (r) => parseFloat(r.avg_case_cost) },
  { key: "prev_avg", label: "Prev Avg $", sortable: true, align: "right", hideBelow: "md", render: (r) => <span className="font-mono text-xs text-zinc-400">${r.prev_avg_case_cost}</span>, sortValue: (r) => parseFloat(r.prev_avg_case_cost) },
  {
    key: "avg_change", label: "Avg Change", sortable: true, align: "right",
    render: (r) => { const val = parseFloat(r.avg_change); const color = val < 0 ? "text-emerald-600" : val > 0 ? "text-red-600" : "text-zinc-500"; return <span className={`text-sm font-medium ${color}`}>{val > 0 ? "+" : ""}${r.avg_change}</span>; },
    sortValue: (r) => parseFloat(r.avg_change),
  },
  {
    key: "avg_pct_change", label: "% Change", sortable: true, align: "right",
    render: (r) => { const color = r.avg_pct_change < 0 ? "text-emerald-600" : r.avg_pct_change > 0 ? "text-red-600" : "text-zinc-500"; return <span className={`text-xs font-medium ${color}`}>{r.avg_pct_change > 0 ? "+" : ""}{r.avg_pct_change}%</span>; },
    sortValue: (r) => r.avg_pct_change,
  },
  { key: "drops", label: "Drops", sortable: true, align: "right", hideBelow: "sm", render: (r) => <span className="text-xs text-emerald-600">{r.drops}</span>, sortValue: (r) => r.drops },
  { key: "increases", label: "Increases", sortable: true, align: "right", hideBelow: "sm", render: (r) => <span className="text-xs text-red-600">{r.increases}</span>, sortValue: (r) => r.increases },
];

// -- Cross-distributor columns -----------------------------------------------

function crossCatColumns(data: CrossCategoryRow[]): Column<CrossCategoryRow>[] {
  const nameA = data[0]?.distributor_a_name || "A";
  const nameB = data[0]?.distributor_b_name || "B";
  return [
    { key: "category", label: "Category", sortable: true, render: (r) => <span className="text-sm font-medium">{r.category}</span>, sortValue: (r) => r.category },
    { key: "count_a", label: `${nameA} #`, sortable: true, align: "right", render: (r) => <span className="text-sm">{r.product_count_a}</span>, sortValue: (r) => r.product_count_a },
    { key: "avg_a", label: `${nameA} Avg`, sortable: true, align: "right", render: (r) => <span className="font-mono text-sm">{r.avg_cost_a ? `$${r.avg_cost_a}` : "—"}</span>, sortValue: (r) => r.avg_cost_a ? parseFloat(r.avg_cost_a) : 0 },
    { key: "count_b", label: `${nameB} #`, sortable: true, align: "right", render: (r) => <span className="text-sm">{r.product_count_b}</span>, sortValue: (r) => r.product_count_b },
    { key: "avg_b", label: `${nameB} Avg`, sortable: true, align: "right", render: (r) => <span className="font-mono text-sm">{r.avg_cost_b ? `$${r.avg_cost_b}` : "—"}</span>, sortValue: (r) => r.avg_cost_b ? parseFloat(r.avg_cost_b) : 0 },
    { key: "diff", label: "Diff", sortable: true, align: "right", render: (r) => { if (!r.diff) return <span className="text-zinc-300">—</span>; const v = parseFloat(r.diff); const c = v < 0 ? "text-emerald-600" : v > 0 ? "text-red-600" : "text-zinc-500"; return <span className={`text-xs font-medium ${c}`}>{v > 0 ? "+" : ""}${r.diff}</span>; }, sortValue: (r) => r.diff ? parseFloat(r.diff) : 0 },
    { key: "pct_diff", label: "% Diff", sortable: true, align: "right", render: (r) => { if (r.pct_diff == null) return <span className="text-zinc-300">—</span>; const c = r.pct_diff < 0 ? "text-emerald-600" : r.pct_diff > 0 ? "text-red-600" : "text-zinc-500"; return <span className={`text-xs font-medium ${c}`}>{r.pct_diff > 0 ? "+" : ""}{r.pct_diff}%</span>; }, sortValue: (r) => r.pct_diff ?? 0 },
    {
      key: "cheaper", label: "Cheaper", sortable: true,
      render: (r) => r.cheaper ? <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold ${r.cheaper === r.distributor_a_slug ? "bg-blue-50 text-blue-700 border border-blue-200" : "bg-purple-50 text-purple-700 border border-purple-200"}`}>{r.cheaper === r.distributor_a_slug ? nameA : nameB}</span> : <span className="text-zinc-300">—</span>,
      sortValue: (r) => r.cheaper ?? "",
    },
  ];
}

function crossRipColumns(data: CrossRipRow[]): Column<CrossRipRow>[] {
  const nameA = data[0]?.distributor_a_name || "A";
  const nameB = data[0]?.distributor_b_name || "B";
  return [
    { key: "category", label: "Category", sortable: true, render: (r) => <span className="text-sm font-medium">{r.category}</span>, sortValue: (r) => r.category },
    { key: "rip_a", label: `${nameA} RIPs`, sortable: true, align: "right", render: (r) => <span className="text-sm">{r.rip_count_a}</span>, sortValue: (r) => r.rip_count_a },
    { key: "cov_a", label: `${nameA} %`, sortable: true, align: "right", render: (r) => r.coverage_pct_a != null ? <span className="text-xs">{r.coverage_pct_a}%</span> : <span className="text-zinc-300">—</span>, sortValue: (r) => r.coverage_pct_a ?? 0 },
    { key: "avg_a", label: `${nameA} Avg Save`, sortable: true, align: "right", render: (r) => r.avg_save_a ? <span className="text-xs text-emerald-600">${r.avg_save_a}</span> : <span className="text-zinc-300">—</span>, sortValue: (r) => r.avg_save_a ? parseFloat(r.avg_save_a) : 0 },
    { key: "rip_b", label: `${nameB} RIPs`, sortable: true, align: "right", render: (r) => <span className="text-sm">{r.rip_count_b}</span>, sortValue: (r) => r.rip_count_b },
    { key: "cov_b", label: `${nameB} %`, sortable: true, align: "right", render: (r) => r.coverage_pct_b != null ? <span className="text-xs">{r.coverage_pct_b}%</span> : <span className="text-zinc-300">—</span>, sortValue: (r) => r.coverage_pct_b ?? 0 },
    { key: "avg_b", label: `${nameB} Avg Save`, sortable: true, align: "right", render: (r) => r.avg_save_b ? <span className="text-xs text-emerald-600">${r.avg_save_b}</span> : <span className="text-zinc-300">—</span>, sortValue: (r) => r.avg_save_b ? parseFloat(r.avg_save_b) : 0 },
  ];
}

function crossBrandColumns(data: CrossBrandRow[]): Column<CrossBrandRow>[] {
  const nameA = data[0]?.distributor_a_name || "A";
  const nameB = data[0]?.distributor_b_name || "B";
  return [
    { key: "brand", label: "Brand", sortable: true, render: (r) => <span className="text-sm font-medium">{r.brand}</span>, sortValue: (r) => r.brand },
    { key: "count_a", label: `${nameA}`, sortable: true, align: "right", render: (r) => <span className="text-sm">{r.count_a}</span>, sortValue: (r) => r.count_a },
    { key: "count_b", label: `${nameB}`, sortable: true, align: "right", render: (r) => <span className="text-sm">{r.count_b}</span>, sortValue: (r) => r.count_b },
    {
      key: "exclusive", label: "Exclusive", sortable: true,
      render: (r) => {
        if (!r.exclusive_to) return <span className="text-xs text-zinc-400">Shared</span>;
        return <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold ${r.exclusive_to === r.distributor_a_slug ? "bg-blue-50 text-blue-700 border border-blue-200" : "bg-purple-50 text-purple-700 border border-purple-200"}`}>{r.exclusive_to === r.distributor_a_slug ? nameA : nameB} only</span>;
      },
      sortValue: (r) => r.exclusive_to ?? "zzz",
    },
  ];
}

function crossPriceColumns(data: CrossPriceRow[]): Column<CrossPriceRow>[] {
  const nameA = data[0]?.distributor_a_name || "A";
  const nameB = data[0]?.distributor_b_name || "B";
  return [
    { key: "desc", label: "Product", sortable: true, render: (r) => <span className="text-sm">{r.canonical_description ?? "—"}</span>, sortValue: (r) => r.canonical_description ?? "" },
    { key: "size", label: "Size", sortable: false, hideBelow: "sm", render: (r) => <span className="text-xs">{r.size ?? "—"}</span> },
    { key: "brand", label: "Brand", sortable: true, hideBelow: "lg", render: (r) => <span className="text-xs text-zinc-500">{r.brand ?? "—"}</span>, sortValue: (r) => r.brand ?? "" },
    { key: "cost_a", label: `${nameA} $`, sortable: true, align: "right", render: (r) => <span className="font-mono text-sm">{r.case_cost_a ? `$${r.case_cost_a}` : "—"}</span>, sortValue: (r) => r.case_cost_a ? parseFloat(r.case_cost_a) : 0 },
    { key: "eff_a", label: `${nameA} Eff`, sortable: true, align: "right", hideBelow: "md", render: (r) => r.effective_a ? <span className="font-mono text-xs text-emerald-700">${r.effective_a}</span> : <span className="text-zinc-300">—</span>, sortValue: (r) => r.effective_a ? parseFloat(r.effective_a) : 0 },
    { key: "cost_b", label: `${nameB} $`, sortable: true, align: "right", render: (r) => <span className="font-mono text-sm">{r.case_cost_b ? `$${r.case_cost_b}` : "—"}</span>, sortValue: (r) => r.case_cost_b ? parseFloat(r.case_cost_b) : 0 },
    { key: "eff_b", label: `${nameB} Eff`, sortable: true, align: "right", hideBelow: "md", render: (r) => r.effective_b ? <span className="font-mono text-xs text-emerald-700">${r.effective_b}</span> : <span className="text-zinc-300">—</span>, sortValue: (r) => r.effective_b ? parseFloat(r.effective_b) : 0 },
    { key: "diff", label: "Diff", sortable: true, align: "right", render: (r) => { if (!r.diff) return <span className="text-zinc-300">—</span>; const v = parseFloat(r.diff); const c = v < 0 ? "text-emerald-600" : v > 0 ? "text-red-600" : "text-zinc-500"; return <span className={`text-xs font-medium ${c}`}>{v > 0 ? "+" : ""}${r.diff}</span>; }, sortValue: (r) => r.diff ? parseFloat(r.diff) : 0 },
    {
      key: "cheaper", label: "Cheaper", sortable: true,
      render: (r) => r.cheaper ? <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold ${r.cheaper === r.distributor_a_slug ? "bg-blue-50 text-blue-700 border border-blue-200" : "bg-purple-50 text-purple-700 border border-purple-200"}`}>{r.cheaper === r.distributor_a_slug ? nameA : nameB}</span> : <span className="text-zinc-300">—</span>,
      sortValue: (r) => r.cheaper ?? "",
    },
  ];
}

// -- Main component ----------------------------------------------------------

export default function Analytics() {
  const [distMode, setDistMode] = useState<DistMode>("allied");
  const [activeView, setActiveView] = useState<AnalyticsView | null>(null);
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [brandFilter, setBrandFilter] = useState("");
  const [divisionFilter, setDivisionFilter] = useState("");
  const [minPct, setMinPct] = useState(0);

  const wlQ = useQuery({ queryKey: ["watchlist"], queryFn: () => watchlistApi.list() });
  const favCodes = useMemo(() => new Set((wlQ.data ?? []).map((w) => w.product_code)), [wlQ.data]);
  const favNotes = useMemo(() => {
    const m = new Map<string, string>();
    for (const w of wlQ.data ?? []) if (w.notes) m.set(w.product_code, w.notes);
    return m;
  }, [wlQ.data]);

  const showDistCol = distMode === "all";
  const productColumns = useMemo(
    () => makeProductColumns(favCodes, favNotes, activeView, showDistCol),
    [favCodes, favNotes, activeView, showDistCol],
  );

  // Determine API distributor param
  const apiDistributor = distMode === "compare" ? "all" : distSlug(distMode);

  const { data, isLoading, error } = useQuery({
    queryKey: ["analytics", activeView, apiDistributor],
    queryFn: () => analyticsApi.query(activeView!, 500, apiDistributor),
    enabled: activeView !== null,
  });

  const productSort = useSort<AnalyticsRow>({ key: "pct_change", direction: "asc" });
  const categorySort = useSort<CategoryTrendRow>({ key: "avg_pct_change", direction: "asc" });
  const crossCatSort = useSort<CrossCategoryRow>({ key: "pct_diff", direction: "desc" });
  const crossRipSort = useSort<CrossRipRow>({ key: "rip_a", direction: "desc" });
  const crossBrandSort = useSort<CrossBrandRow>({ key: "brand", direction: "asc" });
  const crossPriceSort = useSort<CrossPriceRow>({ key: "diff", direction: "desc" });

  const isCategoryView = activeView === "category_trends";
  const isCrossView = activeView ? CROSS_VIEW_SET.has(activeView) : false;

  // Which views to show based on mode
  const visibleViews = distMode === "compare" ? CROSS_VIEWS_LIST : SINGLE_VIEWS;

  // Extract facets from product rows
  const facets = useMemo(() => {
    const rows = data?.rows ?? [];
    const cats = new Set<string>(), brands = new Set<string>(), divs = new Set<string>();
    for (const r of rows) {
      if (r.category) cats.add(r.category);
      if (r.brand) brands.add(r.brand);
      if (r.divisions) for (const d of r.divisions.split(/\s+/)) if (d.trim()) divs.add(d.trim());
    }
    return { categories: [...cats].sort(), brands: [...brands].sort(), divisions: [...divs].sort() };
  }, [data?.rows]);

  // Filtered rows
  const filteredRows = useMemo(() => {
    let rows = data?.rows ?? [];
    if (search) { const q = search.toLowerCase(); rows = rows.filter((r) => r.code.toLowerCase().includes(q) || (r.description ?? "").toLowerCase().includes(q) || (r.brand ?? "").toLowerCase().includes(q)); }
    if (categoryFilter) rows = rows.filter((r) => r.category === categoryFilter);
    if (brandFilter) rows = rows.filter((r) => r.brand === brandFilter);
    if (divisionFilter) rows = rows.filter((r) => r.divisions && r.divisions.includes(divisionFilter));
    if (minPct > 0) rows = rows.filter((r) => r.pct_change != null && Math.abs(r.pct_change) >= minPct);
    return rows;
  }, [data?.rows, search, categoryFilter, brandFilter, divisionFilter, minPct]);

  const filteredCatRows = useMemo(() => {
    let rows = data?.category_rows ?? [];
    if (search) { const q = search.toLowerCase(); rows = rows.filter((r) => r.category.toLowerCase().includes(q)); }
    if (minPct > 0) rows = rows.filter((r) => Math.abs(r.avg_pct_change) >= minPct);
    return rows;
  }, [data?.category_rows, search, minPct]);

  // Stats
  const stats = useMemo(() => {
    if (isCategoryView || isCrossView || filteredRows.length === 0) return null;
    const withPct = filteredRows.filter((r) => r.pct_change != null);
    const avgPct = withPct.length > 0 ? withPct.reduce((s, r) => s + (r.pct_change ?? 0), 0) / withPct.length : null;
    const withRip = filteredRows.filter((r) => r.rip_save != null);
    const totalRipSave = withRip.reduce((s, r) => s + parseFloat(r.rip_save ?? "0"), 0);
    return { shown: filteredRows.length, total: data?.total ?? 0, avgPct, ripCount: withRip.length, totalRipSave };
  }, [filteredRows, data?.total, isCategoryView, isCrossView]);

  const handleViewClick = (view: AnalyticsView) => {
    setActiveView(view);
    setSearch(""); setCategoryFilter(""); setBrandFilter(""); setDivisionFilter(""); setMinPct(0);
  };

  const handleModeChange = (mode: DistMode) => {
    setDistMode(mode);
    setActiveView(null);
    setSearch(""); setCategoryFilter(""); setBrandFilter(""); setDivisionFilter(""); setMinPct(0);
  };

  const hasActiveFilters = search || categoryFilter || brandFilter || divisionFilter || minPct > 0;
  const clearFilters = () => { setSearch(""); setCategoryFilter(""); setBrandFilter(""); setDivisionFilter(""); setMinPct(0); };

  return (
    <div className="space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-brand-navy">Pricing Analytics</h1>
          <p className="text-sm text-zinc-500 mt-1">
            {distMode === "compare" ? "Cross-distributor comparison." : "Compare pricing across editions."}
          </p>
        </div>
        {data && (
          <div className="text-xs text-zinc-400">
            {data.edition_current}
            {data.edition_previous ? ` vs ${data.edition_previous}` : ""}
          </div>
        )}
      </div>

      {/* Distributor Mode Selector */}
      <div className="flex items-center gap-1 p-1 rounded-lg bg-zinc-100 w-fit">
        {([
          { mode: "allied" as DistMode, label: "Allied" },
          { mode: "fedway" as DistMode, label: "Fedway" },
          { mode: "all" as DistMode, label: "All" },
          { mode: "compare" as DistMode, label: "Compare" },
        ]).map(({ mode, label }) => (
          <button
            key={mode}
            onClick={() => handleModeChange(mode)}
            className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
              distMode === mode
                ? "bg-white text-brand-navy shadow-sm"
                : "text-zinc-500 hover:text-zinc-700"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* View Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
        {visibleViews.map((v) => (
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
              <span className={`text-lg font-bold ${activeView === v.view ? "" : "text-zinc-400"}`}>{v.icon}</span>
              <span className="text-sm font-semibold leading-tight">{v.label}</span>
            </div>
            <p className="text-[11px] text-zinc-500 leading-snug">{v.desc}</p>
          </button>
        ))}
      </div>

      {/* Results */}
      {activeView && (
        <>
          {/* Stats bar (product views only) */}
          {stats && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="rounded-xl shadow-sm border border-zinc-200 bg-white px-3 py-2">
                <div className="text-xs text-zinc-500">Results</div>
                <div className="text-lg font-semibold text-brand-navy">
                  {stats.shown}
                  {stats.shown !== stats.total && <span className="text-xs font-normal text-zinc-400"> / {stats.total}</span>}
                </div>
              </div>
              {stats.avgPct != null && (
                <div className={`rounded-lg border px-3 py-2 ${stats.avgPct < 0 ? "border-emerald-200 bg-emerald-50" : stats.avgPct > 0 ? "border-red-200 bg-red-50" : "border-zinc-200 bg-white"}`}>
                  <div className={`text-xs ${stats.avgPct < 0 ? "text-emerald-600" : stats.avgPct > 0 ? "text-red-600" : "text-zinc-500"}`}>Avg Change</div>
                  <div className={`text-lg font-semibold ${stats.avgPct < 0 ? "text-emerald-800" : stats.avgPct > 0 ? "text-red-800" : "text-zinc-900"}`}>
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
                  <div className="text-lg font-semibold text-emerald-800">${stats.totalRipSave.toFixed(2)}</div>
                </div>
              )}
            </div>
          )}

          {/* Filters */}
          {data && !isLoading && !isCrossView && (
            <div className="flex flex-col sm:flex-row flex-wrap gap-3 items-start sm:items-center">
              <input
                type="text"
                placeholder={isCategoryView ? "Search category..." : "Search SKU, description, brand..."}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full sm:w-64 rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm placeholder:text-zinc-400 focus:border-brand-orange focus:outline-none"
              />
              {!isCategoryView && facets.categories.length > 1 && (
                <select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)} className="rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm">
                  <option value="">All categories</option>
                  {facets.categories.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              )}
              {!isCategoryView && facets.brands.length > 1 && (
                <select value={brandFilter} onChange={(e) => setBrandFilter(e.target.value)} className="rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm">
                  <option value="">All brands</option>
                  {facets.brands.map((b) => <option key={b} value={b}>{b}</option>)}
                </select>
              )}
              {!isCategoryView && facets.divisions.length > 1 && (
                <select value={divisionFilter} onChange={(e) => setDivisionFilter(e.target.value)} className="rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm">
                  <option value="">All divisions</option>
                  {facets.divisions.map((d) => <option key={d} value={d}>{d}</option>)}
                </select>
              )}
              {(isCategoryView || (activeView && PCT_VIEWS.has(activeView))) && (
                <label className="text-sm text-zinc-700 flex items-center gap-2">
                  Min %
                  <input type="number" value={minPct} onChange={(e) => setMinPct(parseFloat(e.target.value) || 0)} min={0} max={100} step={1} className="w-16 rounded-md border border-zinc-300 bg-white px-2 py-1 text-sm" />
                </label>
              )}
              {hasActiveFilters && (
                <button onClick={clearFilters} className="text-xs text-zinc-500 hover:text-zinc-800 underline">Clear filters</button>
              )}
            </div>
          )}

          {/* Table */}
          <div className="bg-white border border-zinc-200 rounded-xl shadow-sm overflow-hidden">
            {isLoading && <div className="p-8 text-center text-zinc-400">Loading analysis...</div>}
            {error && <div className="p-8 text-center text-red-500">{error instanceof Error ? error.message : "Failed to load"}</div>}

            {data && !isLoading && (
              <>
                <div className="px-4 py-3 border-b border-zinc-100 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1">
                  <h2 className="font-semibold text-sm">
                    {VIEWS.find((v) => v.view === activeView)?.label}
                    <span className="ml-2 text-zinc-400 font-normal">
                      {isCrossView
                        ? `${data.cross_category_rows.length || data.cross_rip_rows.length || data.cross_brand_rows.length || data.cross_price_rows.length} results`
                        : `${isCategoryView ? filteredCatRows.length : filteredRows.length} results`}
                      {hasActiveFilters && !isCrossView && <> (filtered from {data.total})</>}
                    </span>
                  </h2>
                  <span className="text-xs text-zinc-400">{data.edition_current}{data.edition_previous ? ` vs ${data.edition_previous}` : ""}</span>
                </div>

                {/* Cross-distributor tables */}
                {activeView === "cross_category_compare" && data.cross_category_rows.length > 0 && (() => {
                  const cols = crossCatColumns(data.cross_category_rows);
                  return <SortableTable data={crossCatSort.sorted(data.cross_category_rows, cols)} columns={cols} sort={crossCatSort.sort} onSort={crossCatSort.toggle} rowKey={(r) => r.category} emptyMessage="No data." />;
                })()}

                {activeView === "cross_rip_coverage" && data.cross_rip_rows.length > 0 && (() => {
                  const cols = crossRipColumns(data.cross_rip_rows);
                  return <SortableTable data={crossRipSort.sorted(data.cross_rip_rows, cols)} columns={cols} sort={crossRipSort.sort} onSort={crossRipSort.toggle} rowKey={(r) => r.category} emptyMessage="No data." />;
                })()}

                {activeView === "cross_brand_availability" && data.cross_brand_rows.length > 0 && (() => {
                  const cols = crossBrandColumns(data.cross_brand_rows);
                  return <SortableTable data={crossBrandSort.sorted(data.cross_brand_rows, cols)} columns={cols} sort={crossBrandSort.sort} onSort={crossBrandSort.toggle} rowKey={(r) => r.brand} emptyMessage="No data." />;
                })()}

                {activeView === "cross_price_compare" && data.cross_price_rows.length > 0 && (() => {
                  const cols = crossPriceColumns(data.cross_price_rows);
                  return <SortableTable data={crossPriceSort.sorted(data.cross_price_rows, cols)} columns={cols} sort={crossPriceSort.sort} onSort={crossPriceSort.toggle} rowKey={(r) => r.link_id} emptyMessage="No linked products yet. Run the product matcher to link products across distributors." />;
                })()}

                {/* Single-distributor tables */}
                {isCategoryView && filteredCatRows.length > 0 ? (
                  <SortableTable data={categorySort.sorted(filteredCatRows, categoryColumns)} columns={categoryColumns} sort={categorySort.sort} onSort={categorySort.toggle} rowKey={(r) => `${r.category}-${r.distributor_slug}`} emptyMessage="No categories match your filters." />
                ) : !isCategoryView && !isCrossView && filteredRows.length > 0 ? (
                  <SortableTable data={productSort.sorted(filteredRows, productColumns)} columns={productColumns} sort={productSort.sort} onSort={productSort.toggle} rowKey={(r) => `${r.distributor_slug}-${r.code}`} emptyMessage="No products match your filters." />
                ) : !isCrossView ? (
                  <div className="p-8 text-center text-zinc-400 text-sm">
                    {hasActiveFilters ? "No results match your filters." : <>No results for this analysis.{!data.edition_previous && " Only one edition — comparison requires two."}</>}
                  </div>
                ) : isCrossView && data.cross_category_rows.length === 0 && data.cross_rip_rows.length === 0 && data.cross_brand_rows.length === 0 && data.cross_price_rows.length === 0 ? (
                  <div className="p-8 text-center text-zinc-400 text-sm">
                    {activeView === "cross_price_compare" ? "No linked products yet. Run the product matcher to link products across distributors." : "No data available for this comparison."}
                  </div>
                ) : null}
              </>
            )}
          </div>
        </>
      )}

      {!activeView && (
        <div className="text-center py-12 text-zinc-400 text-sm">
          Select a distributor mode and analysis above to begin.
        </div>
      )}
    </div>
  );
}
