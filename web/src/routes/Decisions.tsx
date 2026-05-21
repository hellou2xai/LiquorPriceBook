import { useState, useMemo } from "react";
import { Link } from "react-router-dom";
import { ProductLink } from "../components/ProductPopup";
import { useQuery } from "@tanstack/react-query";
import {
  decisionsApi,
  watchlistApi,
  type BuySheetItem,
  type BuySheetSection,
  type BuySheetResponse,
  type MissedOpportunityRow,
  type ScorecardMetric,
} from "../lib/api";
import { money } from "../lib/fmt";
import { useDistributor } from "../lib/distributor";
import SortableTable, { useSort, type Column } from "../components/SortableTable";
import RowLimitSelect, { useRowLimit } from "../components/RowLimitSelect";
import FavoriteButton from "../components/FavoriteButton";
import ProductContextMenu, { useContextMenu } from "../components/ProductContextMenu";
import TrackedOnlyToggle from "../components/TrackedOnlyToggle";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
  RadialBarChart, RadialBar, PolarAngleAxis,
} from "recharts";

// ============================================================================
// TABS
// ============================================================================

type Tab = "buysheet" | "scorecard" | "missed";

// ============================================================================
// SECTION ICON MAP
// ============================================================================

const SECTION_ICONS: Record<string, string> = {
  fire: "\uD83D\uDD25",
  star: "\u2B50",
  check: "\u2705",
  think: "\uD83E\uDD14",
  pause: "\u23F8\uFE0F",
  sparkle: "\u2728",
};

const SECTION_COLORS: Record<string, { bg: string; border: string; text: string; badge: string }> = {
  last_chance: { bg: "bg-red-50", border: "border-red-200", text: "text-red-800", badge: "bg-red-100 text-red-800" },
  strong_buy: { bg: "bg-emerald-50", border: "border-emerald-200", text: "text-emerald-800", badge: "bg-emerald-100 text-emerald-800" },
  buy_now: { bg: "bg-blue-50", border: "border-blue-200", text: "text-blue-800", badge: "bg-blue-100 text-blue-800" },
  consider: { bg: "bg-amber-50", border: "border-amber-200", text: "text-amber-800", badge: "bg-amber-100 text-amber-800" },
  defer: { bg: "bg-zinc-50", border: "border-zinc-200", text: "text-zinc-600", badge: "bg-zinc-100 text-zinc-700" },
  new_opportunities: { bg: "bg-violet-50", border: "border-violet-200", text: "text-violet-800", badge: "bg-violet-100 text-violet-800" },
};

const VERDICT_BADGES: Record<string, { label: string; cls: string }> = {
  LAST_CHANCE: { label: "LAST CHANCE", cls: "bg-red-600 text-white" },
  STRONG_BUY: { label: "STRONG BUY", cls: "bg-emerald-600 text-white" },
  BUY_NOW: { label: "BUY NOW", cls: "bg-blue-600 text-white" },
  CONSIDER: { label: "CONSIDER", cls: "bg-amber-500 text-white" },
  DEFER: { label: "DEFER", cls: "bg-zinc-400 text-white" },
  PASS: { label: "PASS", cls: "bg-zinc-300 text-zinc-700" },
};

// ============================================================================
// BUY SHEET PANEL (main new feature)
// ============================================================================

function BuySheetPanel({ distributor }: { distributor: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["buy-sheet", distributor],
    queryFn: () => decisionsApi.buySheet(distributor),
  });

  const wlQ = useQuery({ queryKey: ["watchlist"], queryFn: () => watchlistApi.list(), staleTime: 30_000 });
  const favCodes = new Set((wlQ.data ?? []).map((w) => w.product_code));

  const [activeSection, setActiveSection] = useState<string | null>(null);
  const [trackedOnly, setTrackedOnly] = useState(false);
  const ctx = useContextMenu();

  if (isLoading) return <div className="p-12 text-center text-zinc-400">Analyzing market data...</div>;
  if (error) return <div className="p-12 text-center text-red-500">{error instanceof Error ? error.message : "Failed to load"}</div>;
  if (!data || data.sections.length === 0) {
    return (
      <div className="text-center py-16 text-zinc-400">
        <p className="text-lg mb-2">No decision data available</p>
        <p className="text-sm">Price book data is needed to generate recommendations.</p>
      </div>
    );
  }

  const sum = data.summary;

  return (
    <div className="space-y-6">
      {/* Summary Banner */}
      <SummaryBanner summary={sum} />

      {/* Section Navigator */}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => setActiveSection(null)}
          className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
            activeSection === null
              ? "bg-brand-navy text-white shadow-sm"
              : "bg-zinc-100 text-zinc-600 hover:bg-zinc-200"
          }`}
        >
          All Sections ({sum.total_items})
        </button>
        {data.sections.map((sec) => {
          const colors = SECTION_COLORS[sec.key] ?? SECTION_COLORS.consider;
          return (
            <button
              key={sec.key}
              onClick={() => setActiveSection(activeSection === sec.key ? null : sec.key)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
                activeSection === sec.key
                  ? `${colors.badge} ring-2 ring-offset-1 ring-brand-navy`
                  : "bg-zinc-100 text-zinc-600 hover:bg-zinc-200"
              }`}
            >
              {SECTION_ICONS[sec.icon] ?? ""} {sec.title} ({sec.count})
            </button>
          );
        })}
        <TrackedOnlyToggle active={trackedOnly} onChange={setTrackedOnly} />
      </div>

      {/* Sections */}
      {data.sections
        .filter((sec) => activeSection === null || sec.key === activeSection)
        .map((sec) => (
          <BuySheetSectionCard
            key={sec.key}
            section={sec}
            favCodes={favCodes}
            trackedOnly={trackedOnly}
            ctx={ctx}
          />
        ))}

      <ProductContextMenu
        target={ctx.target}
        onClose={ctx.close}
        isFavorite={ctx.target ? favCodes.has(ctx.target.code) : false}
      />
    </div>
  );
}

// -- Summary Banner ----------------------------------------------------------

function SummaryBanner({ summary: s }: { summary: BuySheetResponse["summary"] }) {
  const marketColor = s.market_direction === "prices_falling"
    ? "text-emerald-700" : s.market_direction === "prices_rising"
    ? "text-red-700" : "text-zinc-600";
  const marketLabel = s.market_direction === "prices_falling"
    ? "Prices Falling" : s.market_direction === "prices_rising"
    ? "Prices Rising" : "Stable";

  return (
    <div className="bg-white rounded-xl border border-zinc-200 shadow-sm p-5">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-4">
        <div>
          <h2 className="text-lg font-bold text-brand-navy">Buy Sheet — {s.edition_label}</h2>
          <p className="text-sm text-zinc-500">
            {s.total_items} products analyzed across {s.total_closeouts} closeouts, {s.total_new_rips} new RIPs, {s.total_lost_rips} lost RIPs
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className={`text-sm font-semibold ${marketColor}`}>{marketLabel}</span>
          <span className="text-xs text-zinc-400">({s.avg_market_change_pct > 0 ? "+" : ""}{s.avg_market_change_pct.toFixed(1)}%)</span>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
        <StatCard label="Last Chance" value={s.total_last_chance} color="red" />
        <StatCard label="Strong Buy" value={s.total_buy_now} color="emerald" />
        <StatCard label="Consider" value={s.total_consider} color="amber" />
        <StatCard label="Defer" value={s.total_defer} color="zinc" />
        <StatCard label="New RIPs" value={s.total_new_rips} color="violet" />
        <StatCard label="Lost RIPs" value={s.total_lost_rips} color="red" />
        <StatCard label="RIP Savings" value={`$${s.potential_rip_savings}`} color="emerald" isText />
      </div>
    </div>
  );
}

function StatCard({ label, value, color, isText }: {
  label: string; value: number | string; color: string; isText?: boolean;
}) {
  const borderCls = `border-${color}-200`;
  const bgCls = color === "zinc" ? "bg-zinc-50" : `bg-${color}-50`;
  return (
    <div className={`rounded-lg border ${borderCls} ${bgCls} px-3 py-2`}>
      <div className="text-[10px] text-zinc-500 uppercase tracking-wide">{label}</div>
      <div className={`${isText ? "text-sm" : "text-xl"} font-bold tabular-nums text-zinc-900`}>{value}</div>
    </div>
  );
}

// -- Section Card with Table -------------------------------------------------

function BuySheetSectionCard({ section, favCodes, trackedOnly, ctx }: {
  section: BuySheetSection;
  favCodes: Set<string>;
  trackedOnly: boolean;
  ctx: ReturnType<typeof useContextMenu>;
}) {
  const colors = SECTION_COLORS[section.key] ?? SECTION_COLORS.consider;
  const { sort, toggle, sorted } = useSort<BuySheetItem>({ key: "urgency", direction: "desc" });
  const { limit: rowLimit, setLimit: setRowLimit } = useRowLimit(50);

  const filteredItems = useMemo(
    () => trackedOnly ? section.items.filter((i) => i.is_tracked) : section.items,
    [section.items, trackedOnly],
  );

  const columns: Column<BuySheetItem>[] = useMemo(() => [
    {
      key: "fav", label: "", thClassName: "w-8",
      render: (r) => <FavoriteButton code={r.code} distributor={r.distributor_slug ?? undefined} isFavorite={favCodes.has(r.code)} />,
    },
    {
      key: "verdict", label: "Verdict", sortable: true,
      render: (r) => {
        const badge = VERDICT_BADGES[r.verdict] ?? VERDICT_BADGES.CONSIDER;
        return <span className={`inline-block rounded-md px-2 py-0.5 text-[10px] font-bold ${badge.cls}`}>{badge.label}</span>;
      },
      sortValue: (r) => r.urgency,
    },
    {
      key: "code", label: "Code", sortable: true,
      render: (r) => (
        <ProductLink code={r.code} distributor={r.distributor_slug ?? undefined}>
          <span className="font-mono text-xs">{r.code}</span>
        </ProductLink>
      ),
      sortValue: (r) => r.code,
    },
    {
      key: "description", label: "Product", sortable: true,
      render: (r) => (
        <div>
          <ProductLink code={r.code} distributor={r.distributor_slug ?? undefined}>
            <span className="text-sm font-medium text-zinc-900 line-clamp-1">{r.description ?? "—"}</span>
          </ProductLink>
          {r.brand && <div className="text-[10px] text-zinc-400">{r.brand}</div>}
        </div>
      ),
      sortValue: (r) => r.description ?? "",
    },
    {
      key: "size", label: "Size", sortable: true, hideBelow: "md",
      render: (r) => <span className="text-xs text-zinc-500">{r.size ?? "—"}</span>,
      sortValue: (r) => r.size ?? "",
    },
    {
      key: "case_cost", label: "Case $", sortable: true, align: "right",
      render: (r) => (
        <div className="text-right">
          <div className="font-mono text-sm tabular-nums">{money(r.case_cost)}</div>
          {r.prev_case_cost && (
            <div className="text-[10px] text-zinc-400">was {money(r.prev_case_cost)}</div>
          )}
        </div>
      ),
      sortValue: (r) => r.case_cost ? parseFloat(r.case_cost) : 0,
    },
    {
      key: "change", label: "Change", sortable: true, align: "right", hideBelow: "sm",
      render: (r) => {
        if (r.case_cost_pct == null) return <span className="text-zinc-300">—</span>;
        const cls = r.case_cost_pct < 0 ? "text-emerald-600" : r.case_cost_pct > 0 ? "text-red-600" : "text-zinc-500";
        return <span className={`text-xs font-medium ${cls}`}>{r.case_cost_pct > 0 ? "+" : ""}{r.case_cost_pct.toFixed(1)}%</span>;
      },
      sortValue: (r) => r.case_cost_pct ?? 0,
    },
    {
      key: "rip", label: "RIP Save", sortable: true, align: "right",
      render: (r) => {
        if (!r.has_rip) return <span className="text-zinc-300">—</span>;
        return (
          <div className="text-right">
            <div className="text-emerald-700 font-semibold text-sm tabular-nums">${r.best_rip_save}</div>
            <div className="text-[10px] text-zinc-400">{r.best_rip_tier} ({r.rip_discount_pct?.toFixed(0)}%)</div>
          </div>
        );
      },
      sortValue: (r) => r.best_rip_save ? parseFloat(r.best_rip_save) : 0,
    },
    {
      key: "signals", label: "Signals", sortable: false, hideBelow: "lg",
      render: (r) => (
        <div className="flex flex-wrap gap-1">
          {r.at_12m_low && <SignalBadge text="12m Low" cls="bg-emerald-100 text-emerald-800" />}
          {r.at_12m_high && <SignalBadge text="12m High" cls="bg-red-100 text-red-800" />}
          {r.is_closeout && <SignalBadge text="Closeout" cls="bg-fuchsia-100 text-fuchsia-800" />}
          {r.has_active_special && <SignalBadge text={`Special ${r.special_days_remaining}d`} cls="bg-sky-100 text-sky-800" />}
          {r.rip_stable === false && <SignalBadge text="New RIP" cls="bg-violet-100 text-violet-800" />}
          {r.rip_stable === true && <SignalBadge text="Stable RIP" cls="bg-zinc-100 text-zinc-600" />}
          {r.price_trend === "falling" && <SignalBadge text="Falling" cls="bg-emerald-100 text-emerald-700" />}
          {r.price_trend === "rising" && <SignalBadge text="Rising" cls="bg-red-100 text-red-700" />}
        </div>
      ),
    },
    {
      key: "reasons", label: "Why", sortable: false,
      render: (r) => (
        <ul className="space-y-0.5">
          {r.verdict_reasons.map((reason, i) => (
            <li key={i} className="text-xs text-zinc-600 leading-snug">{reason}</li>
          ))}
        </ul>
      ),
    },
  ], [favCodes]);

  return (
    <div className={`rounded-xl border ${colors.border} overflow-hidden shadow-sm`}>
      {/* Section Header */}
      <div className={`${colors.bg} px-5 py-3 border-b ${colors.border}`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-lg">{SECTION_ICONS[section.icon] ?? ""}</span>
            <div>
              <h3 className={`font-bold ${colors.text}`}>{section.title}</h3>
              <p className="text-xs text-zinc-500">{section.subtitle}</p>
            </div>
          </div>
          <span className={`rounded-full px-3 py-0.5 text-sm font-bold ${colors.badge}`}>
            {filteredItems.length}
          </span>
        </div>
      </div>

      {/* Table */}
      {filteredItems.length === 0 ? (
        <div className="p-6 text-center text-zinc-400 text-sm">
          {trackedOnly ? "No tracked items in this section" : "No items"}
        </div>
      ) : (
        <>
          <SortableTable
            data={sorted(filteredItems, columns).slice(0, rowLimit)}
            columns={columns}
            sort={sort}
            onSort={toggle}
            rowKey={(r) => `${r.code}-${section.key}`}
            emptyMessage="No items match."
            onRowContextMenu={(e, r) => ctx.handleContextMenu(e, r.code, r.distributor_slug ?? undefined)}
          />
          <RowLimitSelect total={filteredItems.length} limit={rowLimit} onChange={setRowLimit} />
        </>
      )}
    </div>
  );
}

function SignalBadge({ text, cls }: { text: string; cls: string }) {
  return (
    <span className={`inline-block rounded-full px-1.5 py-0.5 text-[9px] font-semibold ${cls}`}>
      {text}
    </span>
  );
}

// ============================================================================
// SCORECARD PANEL (existing, kept)
// ============================================================================

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

function ScorecardPanel({ distributor }: { distributor: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["order-scorecard", distributor],
    queryFn: () => decisionsApi.orderScorecard(distributor),
  });

  if (isLoading) return <div className="p-8 text-center text-zinc-400">Analyzing your order...</div>;
  if (error) return <div className="p-8 text-center text-red-500">{error instanceof Error ? error.message : "Failed"}</div>;
  if (!data) return null;

  if (data.overall_grade === "\u2014") {
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

      <div className="bg-white border border-zinc-200 rounded-xl shadow-sm p-5">
        <h3 className="text-sm font-semibold text-zinc-700 mb-4">Score Breakdown</h3>
        <div className="space-y-4">
          {data.metrics.map((m) => <MetricBar key={m.label} metric={m} />)}
        </div>
      </div>

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

// ============================================================================
// MISSED OPPORTUNITIES PANEL (existing, kept)
// ============================================================================

const OPP_TYPE_LABELS: Record<string, { label: string; color: string }> = {
  closeout_deal: { label: "Closeout", color: "bg-fuchsia-100 text-fuchsia-800 border-fuchsia-300" },
  rip_not_tracked: { label: "RIP Deal", color: "bg-emerald-100 text-emerald-800 border-emerald-300" },
  partial_ending: { label: "Expiring", color: "bg-amber-100 text-amber-800 border-amber-300" },
};

function missedColumns(favCodes: Set<string>): Column<MissedOpportunityRow>[] {
  return [
    {
      key: "fav", label: "", thClassName: "w-8",
      render: (r) => r.code !== "\u2014" ? <FavoriteButton code={r.code} distributor={r.distributor_slug ?? undefined} isFavorite={favCodes.has(r.code)} /> : null,
    },
    {
      key: "code", label: "Code", sortable: true,
      render: (r) => r.code !== "\u2014" ? (
        <ProductLink code={r.code} distributor={r.distributor_slug ?? undefined}>
          {r.code}
        </ProductLink>
      ) : <span className="text-zinc-400 text-xs">\u2014</span>,
      sortValue: (r) => r.code,
    },
    {
      key: "description", label: "Product", sortable: true,
      render: (r) => <span className="text-sm">{r.description ?? "\u2014"}</span>,
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
      render: (r) => r.case_cost ? <span className="font-mono text-sm">${r.case_cost}</span> : <span className="text-zinc-300">\u2014</span>,
      sortValue: (r) => r.case_cost ? parseFloat(r.case_cost) : 0,
    },
    {
      key: "savings", label: "Savings", sortable: true, align: "right",
      render: (r) => {
        if (r.rip_save) return <span className="text-xs text-emerald-600 font-medium">-${r.rip_save} ({r.rip_discount_pct}%)</span>;
        if (r.closeout_pct_off) return <span className="text-xs text-fuchsia-600 font-medium">-{r.closeout_pct_off}%</span>;
        return <span className="text-zinc-300">\u2014</span>;
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
  const [trackedOnly, setTrackedOnly] = useState(false);
  const ctx = useContextMenu();
  const { sort, toggle, sorted } = useSort<MissedOpportunityRow>({ key: "savings", direction: "desc" });
  const { limit: rowLimit, setLimit: setRowLimit } = useRowLimit(100);

  const { data, isLoading, error } = useQuery({
    queryKey: ["missed-opportunities", distributor],
    queryFn: () => decisionsApi.missedOpportunities(distributor, 200),
  });

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

  const filteredRows = (typeFilter ? data.rows.filter((r) => r.opportunity_type === typeFilter) : data.rows)
    .filter((r) => !trackedOnly || favCodes.has(r.code));
  const cols = missedColumns(favCodes);
  const summary = data.summary;
  const byType = summary.by_type as Record<string, number>;

  const chartData = Object.entries(byType).map(([type, count]) => ({
    name: OPP_TYPE_LABELS[type]?.label ?? type,
    count: count as number,
    fill: type === "closeout_deal" ? "#c026d3" : type === "rip_not_tracked" ? "#059669" : "#d97706",
  }));

  return (
    <div className="space-y-5">
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
          <div className="flex items-center gap-2 mb-3 flex-wrap">
            <button onClick={() => setTypeFilter("")} className={`px-2.5 py-1 rounded-md text-xs font-medium ${!typeFilter ? "bg-brand-navy text-white" : "bg-zinc-100 text-zinc-600 hover:bg-zinc-200"}`}>All</button>
            {Object.entries(OPP_TYPE_LABELS).map(([key, { label }]) => (
              <button key={key} onClick={() => setTypeFilter(key)} className={`px-2.5 py-1 rounded-md text-xs font-medium ${typeFilter === key ? "bg-brand-navy text-white" : "bg-zinc-100 text-zinc-600 hover:bg-zinc-200"}`}>
                {label} ({byType[key] ?? 0})
              </button>
            ))}
            <TrackedOnlyToggle active={trackedOnly} onChange={setTrackedOnly} />
          </div>
        </div>
      </div>

      <div className="bg-white border border-zinc-200 rounded-xl shadow-sm overflow-hidden">
        <SortableTable
          data={sorted(filteredRows, cols).slice(0, rowLimit)}
          columns={cols}
          sort={sort}
          onSort={toggle}
          rowKey={(r) => `${r.code}-${r.opportunity_type}`}
          emptyMessage="No opportunities match this filter."
          onRowContextMenu={(e, r) => ctx.handleContextMenu(e, r.code, r.distributor_slug ?? undefined)}
        />
        <RowLimitSelect total={filteredRows.length} limit={rowLimit} onChange={setRowLimit} />
      </div>
      <ProductContextMenu
        target={ctx.target}
        onClose={ctx.close}
        isFavorite={ctx.target ? favCodes.has(ctx.target.code) : false}
      />
    </div>
  );
}

// ============================================================================
// MAIN PAGE
// ============================================================================

export default function Decisions() {
  const { distributor } = useDistributor();
  const [tab, setTab] = useState<Tab>("buysheet");

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-brand-navy">Decision Support</h1>
        <p className="text-sm text-zinc-500 mt-1">
          What to buy, when to buy, and why — powered by price intelligence.
        </p>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 p-1 rounded-lg bg-zinc-100 w-fit">
        <button
          onClick={() => setTab("buysheet")}
          className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
            tab === "buysheet" ? "bg-white text-brand-navy shadow-sm" : "text-zinc-500 hover:text-zinc-700"
          }`}
        >
          Buy Sheet
        </button>
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
      {tab === "buysheet" && <BuySheetPanel distributor={distributor} />}
      {tab === "scorecard" && <ScorecardPanel distributor={distributor} />}
      {tab === "missed" && <MissedOpportunitiesPanel distributor={distributor} />}
    </div>
  );
}
