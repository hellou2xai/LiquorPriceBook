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
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
  PieChart, Pie, Legend,
} from "recharts";

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
  { view: "buy_now_defer", label: "Buy Now vs Defer", desc: "Compare current vs next month — find timing deals", icon: "⏱", color: "bg-gradient-to-br from-emerald-50 to-amber-50 border-emerald-300 text-emerald-800", group: "single" },
  { view: "shortlist_review", label: "Shortlist Review", desc: "Deep analytics on your tracked products", icon: "📊", color: "bg-gradient-to-br from-violet-50 to-blue-50 border-violet-300 text-violet-800", group: "single" },
  // Cross-distributor views
  { view: "cross_category_compare", label: "Category Compare", desc: "Avg price per category across distributors", icon: "⇔", color: "bg-indigo-50 border-indigo-200 text-indigo-700", group: "cross" },
  { view: "cross_rip_coverage", label: "RIP Coverage", desc: "RIP offer coverage comparison by category", icon: "%", color: "bg-teal-50 border-teal-200 text-teal-700", group: "cross" },
  { view: "cross_brand_availability", label: "Brand Availability", desc: "Brand presence comparison across distributors", icon: "B", color: "bg-orange-50 border-orange-200 text-orange-700", group: "cross" },
  { view: "cross_price_compare", label: "Price Compare", desc: "Matched product prices across distributors", icon: "$$", color: "bg-pink-50 border-pink-200 text-pink-700", group: "cross" },
];

const SINGLE_VIEWS = VIEWS.filter((v) => v.group === "single");
const CROSS_VIEWS_LIST = VIEWS.filter((v) => v.group === "cross");

const PCT_VIEWS = new Set<AnalyticsView>(["price_drops", "price_increases", "watchlist_movers", "best_value", "buy_now_defer", "shortlist_review"]);
const COMPARISON_VIEWS = new Set<AnalyticsView>(["price_drops", "price_increases", "watchlist_movers", "best_value", "buy_now_defer", "shortlist_review"]);
const RIP_VIEWS = new Set<AnalyticsView>(["new_rips", "lost_rips", "best_value", "closeout_rip", "buy_now_defer", "shortlist_review"]);
const CROSS_VIEW_SET = new Set<AnalyticsView>(["cross_category_compare", "cross_rip_coverage", "cross_brand_availability", "cross_price_compare"]);
const CHART_VIEWS = new Set<AnalyticsView>(["buy_now_defer", "shortlist_review"]);

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
    const isBuyDefer = activeView === "buy_now_defer";
    cols.push(
      {
        key: "prev_case_cost", label: isBuyDefer ? "Next $" : "Prev $", sortable: true, align: "right" as const, hideBelow: "md",
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
    key: "tag", label: activeView && CHART_VIEWS.has(activeView) ? "Signal" : "Tag", sortable: true, hideBelow: "lg",
    render: (r) => {
      if (!r.tag) return null;
      const signalStyle = SIGNAL_BG[r.tag];
      if (signalStyle) {
        return <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold border ${signalStyle}`}>{r.tag.replace("_", " ")}</span>;
      }
      return <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-brand-navy/5 border border-brand-navy/10 text-brand-navy">{r.tag}</span>;
    },
    sortValue: (r) => {
      const rank: Record<string, number> = { BUY_NOW: 0, GOOD_BUY: 1, HOLD: 2, DEFER: 3 };
      return rank[r.tag ?? ""] ?? 4;
    },
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

// -- Signal colors -----------------------------------------------------------

const SIGNAL_COLORS: Record<string, string> = {
  BUY_NOW: "#059669",   // emerald-600
  GOOD_BUY: "#0891b2",  // cyan-600
  HOLD: "#71717a",      // zinc-500
  DEFER: "#d97706",     // amber-600
};

const SIGNAL_BG: Record<string, string> = {
  BUY_NOW: "bg-emerald-100 text-emerald-800 border-emerald-300",
  GOOD_BUY: "bg-cyan-100 text-cyan-800 border-cyan-300",
  HOLD: "bg-zinc-100 text-zinc-700 border-zinc-300",
  DEFER: "bg-amber-100 text-amber-800 border-amber-300",
};

// -- Chart panels for Buy Now / Defer & Shortlist Review --------------------

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function SignalDistributionChart({ chartData }: { chartData: Record<string, any> }) {
  const dist = chartData?.signal_distribution ?? chartData?.signal_summary;
  if (!dist) return null;
  const pieData = Object.entries(dist).map(([name, value]) => ({ name, value: value as number }));
  if (pieData.every((d) => d.value === 0)) return null;

  return (
    <div className="bg-white border border-zinc-200 rounded-xl shadow-sm p-4">
      <h3 className="text-sm font-semibold text-zinc-700 mb-3">Signal Distribution</h3>
      <div className="flex items-center gap-6">
        <div className="w-48 h-48">
          <ResponsiveContainer>
            <PieChart>
              <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={70} label={(e) => e.value > 0 ? `${e.name}: ${e.value}` : ""} labelLine={false} fontSize={10}>
                {pieData.map((d) => <Cell key={d.name} fill={SIGNAL_COLORS[d.name] ?? "#94a3b8"} />)}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div className="flex flex-col gap-2">
          {pieData.filter((d) => d.value > 0).map((d) => (
            <div key={d.name} className="flex items-center gap-2">
              <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold border ${SIGNAL_BG[d.name] ?? "bg-zinc-100"}`}>{d.name.replace("_", " ")}</span>
              <span className="text-sm font-medium text-zinc-600">{d.value} products</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function CategoryHeatmap({ chartData }: { chartData: Record<string, any> }) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const heatmap: any[] = chartData?.category_heatmap;
  if (!heatmap || heatmap.length === 0) return null;

  // Normalize keys — backend may send buy_now or BUY_NOW
  const norm = heatmap.map((h) => ({
    category: h.category as string,
    buy_now: (h.buy_now ?? h.BUY_NOW ?? 0) as number,
    good_buy: (h.good_buy ?? h.GOOD_BUY ?? 0) as number,
    defer: (h.defer ?? h.DEFER ?? 0) as number,
    hold: (h.hold ?? h.HOLD ?? 0) as number,
    avg_pct: (h.avg_pct ?? 0) as number,
  }));
  const hasGoodBuy = norm.some((h) => h.good_buy > 0);

  const maxCount = Math.max(...norm.flatMap((h) => [h.buy_now, h.defer, h.hold, h.good_buy]), 1);
  const cellBg = (val: number, r: number, g: number, b: number) => {
    const a = val > 0 ? Math.min(val / maxCount, 1) * 0.6 + 0.1 : 0.05;
    return `rgba(${r},${g},${b},${a})`;
  };

  return (
    <div className="bg-white border border-zinc-200 rounded-xl shadow-sm p-4 overflow-x-auto">
      <h3 className="text-sm font-semibold text-zinc-700 mb-3">Category Heatmap</h3>
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-zinc-200">
            <th className="text-left py-1.5 px-2 font-medium text-zinc-500">Category</th>
            <th className="text-center py-1.5 px-2 font-medium text-emerald-600">Buy Now</th>
            {hasGoodBuy && <th className="text-center py-1.5 px-2 font-medium text-cyan-600">Good Buy</th>}
            <th className="text-center py-1.5 px-2 font-medium text-amber-600">Defer</th>
            <th className="text-center py-1.5 px-2 font-medium text-zinc-500">Hold</th>
            <th className="text-right py-1.5 px-2 font-medium text-zinc-500">Avg % Change</th>
          </tr>
        </thead>
        <tbody>
          {norm.map((h) => (
            <tr key={h.category} className="border-b border-zinc-50">
              <td className="py-1.5 px-2 font-medium text-zinc-700">{h.category}</td>
              <td className="py-1 px-2 text-center">
                <span className="inline-block min-w-[28px] rounded px-1.5 py-0.5 font-semibold" style={{ backgroundColor: cellBg(h.buy_now, 5, 150, 105), color: h.buy_now > 0 ? "#065f46" : "#a1a1aa" }}>{h.buy_now}</span>
              </td>
              {hasGoodBuy && (
                <td className="py-1 px-2 text-center">
                  <span className="inline-block min-w-[28px] rounded px-1.5 py-0.5 font-semibold" style={{ backgroundColor: cellBg(h.good_buy, 8, 145, 178), color: h.good_buy > 0 ? "#155e75" : "#a1a1aa" }}>{h.good_buy}</span>
                </td>
              )}
              <td className="py-1 px-2 text-center">
                <span className="inline-block min-w-[28px] rounded px-1.5 py-0.5 font-semibold" style={{ backgroundColor: cellBg(h.defer, 217, 119, 6), color: h.defer > 0 ? "#92400e" : "#a1a1aa" }}>{h.defer}</span>
              </td>
              <td className="py-1 px-2 text-center">
                <span className="inline-block min-w-[28px] rounded px-1.5 py-0.5 font-semibold" style={{ backgroundColor: cellBg(h.hold, 113, 113, 122), color: h.hold > 0 ? "#3f3f46" : "#a1a1aa" }}>{h.hold}</span>
              </td>
              <td className="py-1.5 px-2 text-right">
                <span className={`font-medium ${h.avg_pct < 0 ? "text-emerald-600" : h.avg_pct > 0 ? "text-red-600" : "text-zinc-500"}`}>
                  {h.avg_pct > 0 ? "+" : ""}{h.avg_pct.toFixed(1)}%
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function PriceDirectionChart({ chartData, viewType }: { chartData: Record<string, any>; viewType?: string }) {
  // For buy_now_defer: simple up/down/flat
  // For shortlist_review: histogram buckets
  if (viewType === "shortlist_review") {
    const buckets: Record<string, number> = chartData?.price_change_distribution;
    if (!buckets) return null;
    const order = ["< -10%", "-10% to -5%", "-5% to 0%", "0%", "0% to 5%", "5% to 10%", "> 10%"];
    const barData = order.map((name) => ({
      name,
      count: buckets[name] ?? 0,
      fill: name.startsWith("<") || name.startsWith("-") ? "#059669" : name === "0%" ? "#71717a" : "#ef4444",
    }));
    return (
      <div className="bg-white border border-zinc-200 rounded-xl shadow-sm p-4">
        <h3 className="text-sm font-semibold text-zinc-700 mb-3">Price Change Distribution</h3>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={barData} margin={{ left: 5, right: 10, bottom: 5 }}>
            <XAxis dataKey="name" tick={{ fontSize: 9 }} interval={0} angle={-20} textAnchor="end" height={40} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip formatter={(v) => [`${v} products`, "Count"]} />
            <Bar dataKey="count" radius={[4, 4, 0, 0]}>
              {barData.map((d, i) => <Cell key={i} fill={d.fill} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    );
  }

  const dir = chartData?.price_direction;
  if (!dir) return null;
  const barData = [
    { name: "Price Up", count: dir.up ?? 0, fill: "#ef4444" },
    { name: "Stable", count: dir.flat ?? 0, fill: "#71717a" },
    { name: "Price Down", count: dir.down ?? 0, fill: "#059669" },
  ];

  return (
    <div className="bg-white border border-zinc-200 rounded-xl shadow-sm p-4">
      <h3 className="text-sm font-semibold text-zinc-700 mb-3">Price Direction (Next Month)</h3>
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={barData} layout="vertical" margin={{ left: 10, right: 20 }}>
          <XAxis type="number" tick={{ fontSize: 11 }} />
          <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={80} />
          <Tooltip formatter={(v) => [`${v} products`, "Count"]} />
          <Bar dataKey="count" radius={[0, 4, 4, 0]}>
            {barData.map((d, i) => <Cell key={i} fill={d.fill} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function TopSavingsChart({ chartData }: { chartData: Record<string, any> }) {
  const items: { code: string; description: string; savings: string }[] = chartData?.top_savings;
  if (!items || items.length === 0) return null;
  const barData = items.slice(0, 10).map((s) => ({
    name: s.description?.slice(0, 25) ?? s.code,
    savings: Math.abs(parseFloat(s.savings)),
  }));

  return (
    <div className="bg-white border border-zinc-200 rounded-xl shadow-sm p-4">
      <h3 className="text-sm font-semibold text-zinc-700 mb-3">Top Defer Savings (per case)</h3>
      <ResponsiveContainer width="100%" height={Math.max(200, barData.length * 28)}>
        <BarChart data={barData} layout="vertical" margin={{ left: 10, right: 20 }}>
          <XAxis type="number" tick={{ fontSize: 11 }} tickFormatter={(v) => `$${v}`} />
          <YAxis type="category" dataKey="name" tick={{ fontSize: 10 }} width={140} />
          <Tooltip formatter={(v) => [`$${v}`, "Savings"]} />
          <Bar dataKey="savings" fill="#059669" radius={[0, 4, 4, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function ShortlistSummaryCards({ chartData, rows }: { chartData: Record<string, any>; rows: AnalyticsRow[] }) {
  if (!chartData) return null;
  const sig = chartData.signal_summary ?? {};
  const rip = chartData.rip_coverage ?? {};
  const totalItems = Object.values(sig).reduce((s: number, v) => s + (v as number), 0);
  const closeoutCount = rows.filter((r) => r.is_closeout).length;
  const totalRipSave = rows.reduce((s, r) => s + (r.rip_save ? parseFloat(r.rip_save) : 0), 0);

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
      <div className="rounded-xl shadow-sm border border-zinc-200 bg-white px-3 py-2">
        <div className="text-xs text-zinc-500">Tracked Items</div>
        <div className="text-lg font-semibold text-brand-navy">{totalItems}</div>
      </div>
      <div className="rounded-xl shadow-sm border border-emerald-200 bg-emerald-50 px-3 py-2">
        <div className="text-xs text-emerald-600">Buy Now</div>
        <div className="text-lg font-semibold text-emerald-800">{(sig.BUY_NOW ?? 0) + (sig.GOOD_BUY ?? 0)}</div>
      </div>
      <div className="rounded-xl shadow-sm border border-amber-200 bg-amber-50 px-3 py-2">
        <div className="text-xs text-amber-600">Defer</div>
        <div className="text-lg font-semibold text-amber-800">{sig.DEFER ?? 0}</div>
      </div>
      <div className="rounded-xl shadow-sm border border-blue-200 bg-blue-50 px-3 py-2">
        <div className="text-xs text-blue-600">With RIP</div>
        <div className="text-lg font-semibold text-blue-800">{rip.with_rip ?? 0} <span className="text-xs font-normal">({rip.pct ?? 0}%)</span></div>
      </div>
      <div className="rounded-xl shadow-sm border border-violet-200 bg-violet-50 px-3 py-2">
        <div className="text-xs text-violet-600">Total RIP Savings</div>
        <div className="text-lg font-semibold text-violet-800">${totalRipSave.toFixed(2)}</div>
      </div>
      <div className="rounded-xl shadow-sm border border-fuchsia-200 bg-fuchsia-50 px-3 py-2">
        <div className="text-xs text-fuchsia-600">Closeout Items</div>
        <div className="text-lg font-semibold text-fuchsia-800">{closeoutCount}</div>
      </div>
    </div>
  );
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function RipCoverageChart({ chartData }: { chartData: Record<string, any> }) {
  const rip = chartData?.rip_coverage;
  if (!rip) return null;
  const pieData = [
    { name: "With RIP", value: rip.with_rip ?? 0 },
    { name: "No RIP", value: rip.without_rip ?? 0 },
  ];
  const colors = ["#059669", "#d4d4d8"];

  return (
    <div className="bg-white border border-zinc-200 rounded-xl shadow-sm p-4">
      <h3 className="text-sm font-semibold text-zinc-700 mb-3">RIP Coverage ({rip.pct ?? 0}%)</h3>
      <div className="flex items-center gap-4">
        <div className="w-40 h-40">
          <ResponsiveContainer>
            <PieChart>
              <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={35} outerRadius={60} label={(e) => e.value > 0 ? `${e.value}` : ""} fontSize={11}>
                {pieData.map((_, i) => <Cell key={i} fill={colors[i]} />)}
              </Pie>
              <Tooltip />
              <Legend wrapperStyle={{ fontSize: 11 }} />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div className="text-sm text-zinc-600">
          <div><strong className="text-emerald-700">{rip.with_rip}</strong> products have RIP offers</div>
          <div className="text-xs text-zinc-400 mt-1">{rip.without_rip} without RIP</div>
        </div>
      </div>
    </div>
  );
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function ChartPanel({ activeView, chartData, rows }: { activeView: AnalyticsView | null; chartData: Record<string, any> | null; rows: AnalyticsRow[] }) {
  if (!chartData || !activeView || !CHART_VIEWS.has(activeView)) return null;

  if (activeView === "buy_now_defer") {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <SignalDistributionChart chartData={chartData} />
        <PriceDirectionChart chartData={chartData} />
        <CategoryHeatmap chartData={chartData} />
        <TopSavingsChart chartData={chartData} />
      </div>
    );
  }

  if (activeView === "shortlist_review") {
    return (
      <div className="space-y-4">
        <ShortlistSummaryCards chartData={chartData} rows={rows} />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <SignalDistributionChart chartData={chartData} />
          <RipCoverageChart chartData={chartData} />
          <CategoryHeatmap chartData={chartData} />
          <PriceDirectionChart chartData={chartData} viewType="shortlist_review" />
        </div>
      </div>
    );
  }

  return null;
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

          {/* Charts for Buy Now / Defer & Shortlist Review */}
          {data && !isLoading && CHART_VIEWS.has(activeView!) && (
            <ChartPanel activeView={activeView} chartData={data.chart_data ?? null} rows={filteredRows} />
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
