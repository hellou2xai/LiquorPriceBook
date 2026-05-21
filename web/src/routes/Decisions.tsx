import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  decisionsApi,
  type MissedOpportunityRow,
  type ScorecardMetric,
} from "../lib/api";
import { useDistributor } from "../lib/distributor";
import SortableTable, { useSort, type Column } from "../components/SortableTable";
import FavoriteButton from "../components/FavoriteButton";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
  RadialBarChart, RadialBar, PolarAngleAxis,
} from "recharts";

// -- Tab type ----------------------------------------------------------------

type Tab = "scorecard" | "missed";

// -- Scorecard gauge ---------------------------------------------------------

function ScoreGauge({ score, grade }: { score: number; grade: string }) {
  const color = score >= 80 ? "#059669" : score >= 60 ? "#0891b2" : score >= 40 ? "#d97706" : "#ef4444";
  const data = [{ value: score, fill: color }];
  return (
    <div className="relative w-48 h-48">
      <ResponsiveContainer>
        <RadialBarChart
          innerRadius="70%"
          outerRadius="100%"
          data={data}
          startAngle={180}
          endAngle={0}
          barSize={14}
        >
          <PolarAngleAxis type="number" domain={[0, 100]} tick={false} angleAxisId={0} />
          <RadialBar background={{ fill: "#f4f4f5" }} dataKey="value" cornerRadius={10} />
        </RadialBarChart>
      </ResponsiveContainer>
      <div className="absolute inset-0 flex flex-col items-center justify-center -mt-4">
        <span className="text-4xl font-bold" style={{ color }}>{grade}</span>
        <span className="text-sm text-zinc-500">{score.toFixed(0)}/100</span>
      </div>
    </div>
  );
}

// -- Metric bar --------------------------------------------------------------

function MetricBar({ metric }: { metric: ScorecardMetric }) {
  const barColor = metric.color === "green" ? "#059669" : metric.color === "yellow" ? "#d97706" : "#ef4444";
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-zinc-700">{metric.label}</span>
        <span className="text-sm text-zinc-500">
          {metric.value}
          {metric.max_value && <span className="text-zinc-400 text-xs ml-1">({metric.max_value})</span>}
        </span>
      </div>
      <div className="w-full h-2.5 rounded-full bg-zinc-100 overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${Math.min(metric.score, 100)}%`, backgroundColor: barColor }}
        />
      </div>
    </div>
  );
}

// -- Scorecard panel ---------------------------------------------------------

function ScorecardPanel({ distributor }: { distributor: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["order-scorecard", distributor],
    queryFn: () => decisionsApi.orderScorecard(distributor),
  });

  if (isLoading) return <div className="p-8 text-center text-zinc-400">Analyzing your order...</div>;
  if (error) return <div className="p-8 text-center text-red-500">{error instanceof Error ? error.message : "Failed"}</div>;
  if (!data) return null;

  if (data.overall_grade === "—") {
    return (
      <div className="text-center py-12 text-zinc-400">
        <p className="text-lg mb-2">No items tracked yet</p>
        <p className="text-sm">Add products to your <Link to="/watchlist" className="text-brand-orange underline">Order List</Link> to get a scorecard.</p>
      </div>
    );
  }

  const summary = data.summary;

  return (
    <div className="space-y-6">
      {/* Top section: Gauge + Summary stats */}
      <div className="flex flex-col md:flex-row items-center md:items-start gap-6">
        <ScoreGauge score={data.overall_score} grade={data.overall_grade} />
        <div className="flex-1 space-y-3">
          <h3 className="text-lg font-semibold text-zinc-800">Order Readiness Score</h3>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="rounded-lg border border-zinc-200 bg-white px-3 py-2">
              <div className="text-xs text-zinc-500">Items</div>
              <div className="text-xl font-bold text-brand-navy">{summary.total_items}</div>
            </div>
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2">
              <div className="text-xs text-emerald-600">RIP Savings</div>
              <div className="text-xl font-bold text-emerald-800">${summary.total_rip_savings}</div>
            </div>
            <div className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-2">
              <div className="text-xs text-blue-600">Est. Order</div>
              <div className="text-xl font-bold text-blue-800">${summary.total_cost}</div>
            </div>
            <div className="rounded-lg border border-violet-200 bg-violet-50 px-3 py-2">
              <div className="text-xs text-violet-600">Categories</div>
              <div className="text-xl font-bold text-violet-800">{summary.categories}</div>
            </div>
          </div>
        </div>
      </div>

      {/* Metric bars */}
      <div className="bg-white border border-zinc-200 rounded-xl shadow-sm p-5">
        <h3 className="text-sm font-semibold text-zinc-700 mb-4">Score Breakdown</h3>
        <div className="space-y-4">
          {data.metrics.map((m) => <MetricBar key={m.label} metric={m} />)}
        </div>
      </div>

      {/* Recommendations */}
      {data.recommendations.length > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-amber-800 mb-2">Recommendations</h3>
          <ul className="space-y-1.5">
            {data.recommendations.map((r, i) => (
              <li key={i} className="text-sm text-amber-900 flex items-start gap-2">
                <span className="text-amber-500 mt-0.5 shrink-0">-</span>
                {r}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// -- Missed opportunities panel ----------------------------------------------

const OPP_TYPE_LABELS: Record<string, { label: string; color: string }> = {
  closeout_deal: { label: "Closeout", color: "bg-fuchsia-100 text-fuchsia-800 border-fuchsia-300" },
  rip_not_tracked: { label: "RIP Deal", color: "bg-emerald-100 text-emerald-800 border-emerald-300" },
  partial_ending: { label: "Expiring", color: "bg-amber-100 text-amber-800 border-amber-300" },
};

function missedColumns(favCodes: Set<string>): Column<MissedOpportunityRow>[] {
  return [
    {
      key: "fav", label: "", thClassName: "w-8",
      render: (r) => r.code !== "—" ? <FavoriteButton code={r.code} distributor={r.distributor_slug ?? undefined} isFavorite={favCodes.has(r.code)} /> : null,
    },
    {
      key: "code", label: "Code", sortable: true,
      render: (r) => r.code !== "—" ? (
        <Link to={`/catalog/${r.code}${r.distributor_slug ? `?d=${r.distributor_slug}` : ""}`} className="text-brand-navy hover:text-brand-orange hover:underline font-mono text-xs">
          {r.code}
        </Link>
      ) : <span className="text-zinc-400 text-xs">—</span>,
      sortValue: (r) => r.code,
    },
    {
      key: "description", label: "Product", sortable: true,
      render: (r) => <span className="text-sm">{r.description ?? "—"}</span>,
      sortValue: (r) => r.description ?? "",
    },
    {
      key: "type", label: "Type", sortable: true,
      render: (r) => {
        const t = OPP_TYPE_LABELS[r.opportunity_type] ?? { label: r.opportunity_type, color: "bg-zinc-100 text-zinc-700" };
        return <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold border ${t.color}`}>{t.label}</span>;
      },
      sortValue: (r) => r.priority,
    },
    {
      key: "case_cost", label: "Case $", sortable: true, align: "right",
      render: (r) => r.case_cost ? <span className="font-mono text-sm">${r.case_cost}</span> : <span className="text-zinc-300">—</span>,
      sortValue: (r) => r.case_cost ? parseFloat(r.case_cost) : 0,
    },
    {
      key: "savings", label: "Savings", sortable: true, align: "right",
      render: (r) => {
        if (r.rip_save) return <span className="text-xs text-emerald-600 font-medium">-${r.rip_save} ({r.rip_discount_pct}%)</span>;
        if (r.closeout_pct_off) return <span className="text-xs text-fuchsia-600 font-medium">-{r.closeout_pct_off}%</span>;
        return <span className="text-zinc-300">—</span>;
      },
      sortValue: (r) => r.rip_discount_pct ?? r.closeout_pct_off ?? 0,
    },
    {
      key: "days", label: "Urgency", sortable: true, align: "right", hideBelow: "md",
      render: (r) => {
        if (r.days_remaining != null) return <span className={`text-xs font-medium ${r.days_remaining <= 3 ? "text-red-600" : r.days_remaining <= 7 ? "text-amber-600" : "text-zinc-500"}`}>{r.days_remaining}d left</span>;
        if (r.opportunity_type === "closeout_deal") return <span className="text-xs text-red-500 font-medium">Last call</span>;
        return null;
      },
      sortValue: (r) => r.days_remaining ?? (r.opportunity_type === "closeout_deal" ? -1 : 999),
    },
    {
      key: "reason", label: "Why", sortable: false, hideBelow: "lg",
      render: (r) => <span className="text-xs text-zinc-500">{r.reason}</span>,
    },
  ];
}

function MissedOpportunitiesPanel({ distributor }: { distributor: string }) {
  const [typeFilter, setTypeFilter] = useState("");
  const { sort, toggle, sorted } = useSort<MissedOpportunityRow>({ key: "savings", direction: "desc" });

  const { data, isLoading, error } = useQuery({
    queryKey: ["missed-opportunities", distributor],
    queryFn: () => decisionsApi.missedOpportunities(distributor, 200),
  });

  // Get watchlist for fav icons
  const wlQ = useQuery({ queryKey: ["watchlist"], queryFn: async () => {
    const { watchlistApi } = await import("../lib/api");
    return watchlistApi.list();
  }});
  const favCodes = new Set((wlQ.data ?? []).map((w) => w.product_code));

  if (isLoading) return <div className="p-8 text-center text-zinc-400">Finding opportunities...</div>;
  if (error) return <div className="p-8 text-center text-red-500">{error instanceof Error ? error.message : "Failed"}</div>;
  if (!data || data.total === 0) {
    return (
      <div className="text-center py-12 text-zinc-400">
        <p className="text-lg mb-2">No missed opportunities</p>
        <p className="text-sm">You're tracking all the best deals. Nice work!</p>
      </div>
    );
  }

  const filteredRows = typeFilter ? data.rows.filter((r) => r.opportunity_type === typeFilter) : data.rows;
  const cols = missedColumns(favCodes);
  const summary = data.summary;
  const byType = summary.by_type as Record<string, number>;

  // Bar chart data
  const chartData = Object.entries(byType).map(([type, count]) => ({
    name: OPP_TYPE_LABELS[type]?.label ?? type,
    count: count as number,
    fill: type === "closeout_deal" ? "#c026d3" : type === "rip_not_tracked" ? "#059669" : "#d97706",
  }));

  return (
    <div className="space-y-5">
      {/* Summary */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="rounded-lg border border-zinc-200 bg-white px-3 py-2">
          <div className="text-xs text-zinc-500">Opportunities</div>
          <div className="text-xl font-bold text-brand-navy">{data.total}</div>
        </div>
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2">
          <div className="text-xs text-emerald-600">RIP Savings Missed</div>
          <div className="text-xl font-bold text-emerald-800">${summary.total_rip_savings_missed}</div>
        </div>
        <div className="rounded-lg border border-fuchsia-200 bg-fuchsia-50 px-3 py-2">
          <div className="text-xs text-fuchsia-600">Closeouts</div>
          <div className="text-xl font-bold text-fuchsia-800">{summary.closeout_count}</div>
        </div>
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
          <div className="text-xs text-amber-600">Expiring Deals</div>
          <div className="text-xl font-bold text-amber-800">{summary.expiring_partials}</div>
        </div>
      </div>

      {/* Chart + filters */}
      <div className="flex flex-col md:flex-row gap-4">
        {chartData.length > 0 && (
          <div className="bg-white border border-zinc-200 rounded-xl shadow-sm p-4 w-full md:w-64 shrink-0">
            <h3 className="text-sm font-semibold text-zinc-700 mb-2">By Type</h3>
            <ResponsiveContainer width="100%" height={120}>
              <BarChart data={chartData} layout="vertical" margin={{ left: 5, right: 10 }}>
                <XAxis type="number" tick={{ fontSize: 11 }} />
                <YAxis type="category" dataKey="name" tick={{ fontSize: 10 }} width={60} />
                <Tooltip formatter={(v) => [`${v}`, "Count"]} />
                <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                  {chartData.map((d, i) => <Cell key={i} fill={d.fill} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-3">
            <button onClick={() => setTypeFilter("")} className={`px-2.5 py-1 rounded-md text-xs font-medium ${!typeFilter ? "bg-brand-navy text-white" : "bg-zinc-100 text-zinc-600 hover:bg-zinc-200"}`}>All</button>
            {Object.entries(OPP_TYPE_LABELS).map(([key, { label }]) => (
              <button key={key} onClick={() => setTypeFilter(key)} className={`px-2.5 py-1 rounded-md text-xs font-medium ${typeFilter === key ? "bg-brand-navy text-white" : "bg-zinc-100 text-zinc-600 hover:bg-zinc-200"}`}>
                {label} ({byType[key] ?? 0})
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="bg-white border border-zinc-200 rounded-xl shadow-sm overflow-hidden">
        <SortableTable
          data={sorted(filteredRows, cols)}
          columns={cols}
          sort={sort}
          onSort={toggle}
          rowKey={(r) => `${r.code}-${r.opportunity_type}`}
          emptyMessage="No opportunities match this filter."
        />
      </div>
    </div>
  );
}

// -- Main page ---------------------------------------------------------------

export default function Decisions() {
  const { distributor } = useDistributor();
  const [tab, setTab] = useState<Tab>("scorecard");

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-brand-navy">Decision Support</h1>
        <p className="text-sm text-zinc-500 mt-1">
          Intelligence to help you make better ordering decisions.
        </p>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 p-1 rounded-lg bg-zinc-100 w-fit">
        <button
          onClick={() => setTab("scorecard")}
          className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
            tab === "scorecard" ? "bg-white text-brand-navy shadow-sm" : "text-zinc-500 hover:text-zinc-700"
          }`}
        >
          Order Scorecard
        </button>
        <button
          onClick={() => setTab("missed")}
          className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
            tab === "missed" ? "bg-white text-brand-navy shadow-sm" : "text-zinc-500 hover:text-zinc-700"
          }`}
        >
          Missed Opportunities
        </button>
      </div>

      {/* Tab content */}
      {tab === "scorecard" && <ScorecardPanel distributor={distributor} />}
      {tab === "missed" && <MissedOpportunitiesPanel distributor={distributor} />}
    </div>
  );
}
