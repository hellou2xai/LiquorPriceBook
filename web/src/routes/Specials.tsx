import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { specialsApi } from "../lib/api";
import type { WebSpecial } from "../lib/api";
import { money } from "../lib/fmt";
import { useDistributor } from "../lib/distributor";

function fmtDate(d: string): string {
  const dt = new Date(d + "T00:00:00");
  return dt.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function daysLabel(d: number): string {
  if (d === 0) return "Ends today";
  if (d === 1) return "1 day left";
  return `${d} days left`;
}

function urgencyClass(days: number): string {
  if (days === 0) return "bg-red-100 border-red-300 text-red-800";
  if (days <= 2) return "bg-amber-100 border-amber-300 text-amber-800";
  if (days <= 5) return "bg-yellow-50 border-yellow-200 text-yellow-800";
  return "bg-zinc-100 border-zinc-200 text-zinc-600";
}

function CountdownBadge({ days }: { days: number }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold ${urgencyClass(days)}`}
    >
      {daysLabel(days)}
    </span>
  );
}

function DateRange({ start, end }: { start: string; end: string }) {
  return (
    <span className="text-xs text-zinc-500">
      {fmtDate(start)} &ndash; {fmtDate(end)}
    </span>
  );
}

type Filter = "all" | "pricing" | "rip" | "expiring";

export default function Specials() {
  const [filter, setFilter] = useState<Filter>("all");
  const { distributor } = useDistributor();

  const q = useQuery({
    queryKey: ["specials-active", distributor],
    queryFn: () => specialsApi.active(distributor),
    refetchInterval: 5 * 60_000,
  });

  const items = useMemo(() => {
    if (!q.data) return [];
    switch (filter) {
      case "pricing":
        return q.data.filter((s) => s.kind === "pricing");
      case "rip":
        return q.data.filter((s) => s.kind === "rip");
      case "expiring":
        return q.data.filter((s) => s.days_remaining <= 2);
      default:
        return q.data;
    }
  }, [q.data, filter]);

  const expiringCount = useMemo(
    () => (q.data ?? []).filter((s) => s.days_remaining <= 2).length,
    [q.data],
  );
  const ripCount = useMemo(
    () => (q.data ?? []).filter((s) => s.kind === "rip").length,
    [q.data],
  );
  const pricingCount = useMemo(
    () => (q.data ?? []).filter((s) => s.kind === "pricing").length,
    [q.data],
  );

  // Group by date range for visual clustering
  const grouped = useMemo(() => {
    const groups: Record<string, WebSpecial[]> = {};
    for (const s of items) {
      const key = `${s.start_date}|${s.end_date}`;
      if (!groups[key]) groups[key] = [];
      groups[key].push(s);
    }
    return Object.entries(groups).sort(([a], [b]) => {
      const endA = a.split("|")[1];
      const endB = b.split("|")[1];
      return endA.localeCompare(endB);
    });
  }, [items]);

  return (
    <div className="space-y-5">
      <header className="space-y-1">
        <h1 className="text-xl sm:text-2xl font-semibold tracking-tight text-brand-navy">
          Web Specials
        </h1>
        <p className="text-sm text-zinc-600">
          {q.data
            ? `${q.data.length} active time-limited deals`
            : "Loading..."}
        </p>
      </header>

      {/* Summary cards */}
      {q.data && q.data.length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <SummaryCard
            label="Total Active"
            value={q.data.length}
            active={filter === "all"}
            onClick={() => setFilter("all")}
          />
          <SummaryCard
            label="Expiring Soon"
            value={expiringCount}
            color="red"
            active={filter === "expiring"}
            onClick={() => setFilter("expiring")}
          />
          <SummaryCard
            label="Web RIPs"
            value={ripCount}
            color="amber"
            active={filter === "rip"}
            onClick={() => setFilter("rip")}
          />
          <SummaryCard
            label="Web Pricing"
            value={pricingCount}
            color="sky"
            active={filter === "pricing"}
            onClick={() => setFilter("pricing")}
          />
        </div>
      )}

      {/* Results */}
      {q.isLoading ? (
        <div className="text-center py-12 text-zinc-500">Loading specials...</div>
      ) : items.length === 0 ? (
        <div className="text-center py-12 text-zinc-500">
          No active web specials right now.
        </div>
      ) : (
        <div className="space-y-6">
          {grouped.map(([key, specials]) => {
            const [startDate, endDate] = key.split("|");
            const daysLeft = specials[0].days_remaining;
            return (
              <div
                key={key}
                className="rounded-xl shadow-sm border border-zinc-200 bg-white overflow-hidden"
              >
                {/* Date group header */}
                <div
                  className={`flex items-center justify-between px-4 py-2.5 border-b ${
                    daysLeft <= 2
                      ? "bg-red-50 border-red-200"
                      : daysLeft <= 5
                        ? "bg-amber-50 border-amber-200"
                        : "bg-zinc-50 border-zinc-200"
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <DateRange start={startDate} end={endDate} />
                    <CountdownBadge days={daysLeft} />
                  </div>
                  <span className="text-xs text-zinc-500">
                    {specials.length} deal{specials.length !== 1 ? "s" : ""}
                  </span>
                </div>

                {/* Items table */}
                <table className="min-w-full divide-y divide-zinc-100 text-sm">
                  <thead className="bg-brand-tan text-left text-[10px] uppercase tracking-wide text-brand-navy">
                    <tr>
                      <th className="px-4 py-1.5">Type</th>
                      <th className="px-4 py-1.5">Description</th>
                      <th className="px-4 py-1.5 hidden md:table-cell">Valid Dates</th>
                      <th className="px-4 py-1.5 hidden sm:table-cell">Size</th>
                      <th className="px-4 py-1.5 hidden sm:table-cell">Product</th>
                      <th className="px-4 py-1.5 text-right hidden md:table-cell">
                        Regular Case
                      </th>
                      <th className="px-4 py-1.5 text-right">Deal</th>
                      <th className="px-4 py-1.5 text-right">
                        You Save
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-50">
                    {specials.map((s) => (
                      <SpecialRow key={s.id} special={s} />
                    ))}
                  </tbody>
                </table>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function SpecialRow({ special: s }: { special: WebSpecial }) {
  const regularCase = s.product_case_cost
    ? parseFloat(s.product_case_cost)
    : null;
  const dealPrice =
    s.kind === "pricing"
      ? s.best_case_price
        ? parseFloat(s.best_case_price)
        : null
      : s.rip_price
        ? parseFloat(s.rip_price)
        : null;

  // For RIPs, the "deal price" is the save amount, not final price
  const savings =
    s.kind === "rip" && dealPrice != null
      ? dealPrice
      : regularCase != null && dealPrice != null
        ? regularCase - dealPrice
        : null;

  return (
    <tr className="hover:bg-brand-tan">
      <td className="px-4 py-2">
        <span
          className={`inline-flex items-center rounded-md border px-1.5 py-0.5 text-[10px] font-medium ${
            s.kind === "rip"
              ? "bg-brand-navy/5 border-brand-navy/10 text-brand-navy"
              : "bg-brand-navy/5 border-brand-navy/10 text-brand-navy"
          }`}
        >
          {s.kind === "rip" ? "WEB RIP" : "WEB PRICE"}
        </span>
      </td>
      <td className="px-4 py-2 font-medium text-zinc-900">
        {s.description}
      </td>
      <td className="px-4 py-2 hidden md:table-cell">
        <div className="flex flex-col gap-0.5">
          <span className="text-xs text-zinc-700 font-medium whitespace-nowrap">
            {fmtDate(s.start_date)} &ndash; {fmtDate(s.end_date)}
          </span>
          <CountdownBadge days={s.days_remaining} />
        </div>
      </td>
      <td className="px-4 py-2 text-zinc-500 hidden sm:table-cell">{s.size ?? "\u2014"}</td>
      <td className="px-4 py-2 hidden sm:table-cell">
        {s.product_code ? (
          <Link
            to={`/catalog/${s.product_code}`}
            className="text-brand-navy hover:text-brand-orange font-mono text-xs"
          >
            {s.product_code}
          </Link>
        ) : (
          <span className="text-zinc-300 text-xs">unlinked</span>
        )}
      </td>
      <td className="px-4 py-2 text-right tabular-nums hidden md:table-cell">
        {money(s.product_case_cost)}
      </td>
      <td className="px-4 py-2 text-right">
        {s.kind === "rip" ? (
          <span className="text-amber-700 font-medium text-xs">
            {s.tier ?? ""} save {money(s.rip_price)}
          </span>
        ) : (
          <span className="text-sky-700 font-medium tabular-nums">
            {money(s.best_case_price)}
            {s.best_case_tier ? (
              <span className="text-zinc-400 text-[10px] ml-1">
                ({s.best_case_tier})
              </span>
            ) : null}
          </span>
        )}
      </td>
      <td className="px-4 py-2 text-right">
        {savings != null && savings > 0 ? (
          <span className="text-emerald-700 font-semibold tabular-nums">
            {money(savings)}
          </span>
        ) : (
          <span className="text-zinc-300">{"\u2014"}</span>
        )}
      </td>
    </tr>
  );
}

function SummaryCard({
  label,
  value,
  color = "zinc",
  active,
  onClick,
}: {
  label: string;
  value: number;
  color?: string;
  active: boolean;
  onClick: () => void;
}) {
  const colors: Record<string, string> = {
    zinc: "border-zinc-200",
    red: "border-red-200",
    amber: "border-amber-200",
    sky: "border-sky-200",
  };
  return (
    <button
      onClick={onClick}
      className={`rounded-lg border bg-white p-3 text-left transition-all ${
        colors[color] ?? colors.zinc
      } ${active ? "ring-2 ring-brand-navy ring-offset-1" : "hover:shadow-sm"}`}
    >
      <div className="text-2xl font-bold tabular-nums text-zinc-900">
        {value}
      </div>
      <div className="text-xs text-zinc-500 mt-0.5">{label}</div>
    </button>
  );
}
