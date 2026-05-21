import { createContext, useContext, useState, useCallback, useEffect } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { catalogApi, priceHistoryApi, watchlistApi } from "../lib/api";
import type { PriceDataPoint, PriceHistorySummary } from "../lib/api";
import { money, pct, pctClass } from "../lib/fmt";
import FavoriteButton from "./FavoriteButton";

// ── Context ──

type PopupState = { code: string; distributor: string } | null;

const Ctx = createContext<{
  open: (code: string, distributor?: string) => void;
  close: () => void;
}>({ open: () => {}, close: () => {} });

export function useProductPopup() {
  return useContext(Ctx);
}

export function ProductPopupProvider({ children }: { children: React.ReactNode }) {
  const [target, setTarget] = useState<PopupState>(null);

  const open = useCallback((code: string, distributor?: string) => {
    setTarget({ code, distributor: distributor || "nj-allied" });
  }, []);

  const close = useCallback(() => setTarget(null), []);

  // Close on Escape
  useEffect(() => {
    if (!target) return;
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") setTarget(null);
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [target]);

  return (
    <Ctx.Provider value={{ open, close }}>
      {children}
      {target && <ProductModal code={target.code} distributor={target.distributor} onClose={close} />}
    </Ctx.Provider>
  );
}

// ── Clickable product code link ──

export function ProductLink({
  code,
  distributor,
  children,
  className = "",
}: {
  code: string;
  distributor?: string;
  children: React.ReactNode;
  className?: string;
}) {
  const { open } = useProductPopup();
  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        open(code, distributor);
      }}
      className={className || "font-mono text-xs text-brand-navy hover:text-brand-orange hover:underline"}
    >
      {children}
    </button>
  );
}

// ── Modal ──

function ProductModal({
  code,
  distributor,
  onClose,
}: {
  code: string;
  distributor: string;
  onClose: () => void;
}) {
  const detailQ = useQuery({
    queryKey: ["product", code, distributor],
    queryFn: () => catalogApi.product(code, distributor),
    enabled: !!code,
  });

  const phQ = useQuery({
    queryKey: ["price-history", code, distributor],
    queryFn: () => priceHistoryApi.get(code, distributor),
    enabled: !!code,
  });

  const wlQ = useQuery({ queryKey: ["watchlist"], queryFn: () => watchlistApi.list(), staleTime: 30_000 });
  const isFav = (wlQ.data ?? []).some((w) => w.product_code === code);

  const d = detailQ.data;
  const ph = phQ.data;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-8 sm:pt-16 px-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/40" />
      <div
        className="relative bg-white rounded-xl shadow-2xl border border-zinc-200 w-full max-w-2xl max-h-[85vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute top-3 right-3 rounded-full p-1 hover:bg-zinc-100 text-zinc-400 hover:text-zinc-700 z-10"
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>

        {detailQ.isLoading && (
          <div className="p-12 text-center text-zinc-500">Loading...</div>
        )}

        {detailQ.isError && (
          <div className="p-12 text-center text-red-600">Failed to load product.</div>
        )}

        {d && (
          <div className="p-5 space-y-5">
            {/* Header */}
            <div className="pr-8">
              <div className="flex items-center gap-2 text-xs text-zinc-500 uppercase tracking-wide">
                {d.category_display ?? "Uncategorised"}
                {d.brand_display && <span>· {d.brand_display}</span>}
              </div>
              <h2 className="text-lg font-semibold text-brand-navy mt-1">{d.description ?? "Product"}</h2>
              <div className="flex items-center gap-3 mt-1">
                <span className="text-sm text-zinc-600 font-mono">{d.code}</span>
                <span className="text-sm text-zinc-500">{d.size ?? "—"}</span>
                {d.pack && <span className="text-sm text-zinc-500">Pack {d.pack}</span>}
                {d.divisions && (
                  <span className="text-[10px] font-mono text-zinc-400">{d.divisions}</span>
                )}
                <FavoriteButton code={d.code} distributor={distributor} isFavorite={isFav} />
              </div>
            </div>

            {/* Pricing Grid */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <PriceCard label="Case Cost" value={money(d.case_cost)} />
              <PriceCard label="Bottle Cost" value={money(d.btl_cost)} />
              <PriceCard
                label="vs Previous"
                value={pct(d.case_cost_pct)}
                valueClass={pctClass(d.case_cost_pct)}
                sub={d.prev_case_cost ? `was ${money(d.prev_case_cost)}` : undefined}
              />
              {d.current_rips.length > 0 && (
                <PriceCard
                  label="Best RIP Save"
                  value={money(d.current_rips[d.current_rips.length - 1].save_amount)}
                  valueClass="text-emerald-700"
                />
              )}
            </div>

            {/* RIP Tiers */}
            {d.current_rips.length > 0 && (
              <div>
                <h3 className="text-xs font-medium text-zinc-500 uppercase tracking-wide mb-2">RIP Tiers</h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {d.current_rips.map((r) => (
                    <div key={r.tier} className="flex items-center justify-between rounded-lg border border-emerald-200 bg-emerald-50/50 px-3 py-2 text-sm">
                      <span className="font-mono text-xs font-bold text-emerald-800">{r.tier}</span>
                      <span className="text-emerald-700 font-medium">Save {money(r.save_amount)}/cs</span>
                      <span className="text-zinc-500 text-xs">→ {money(r.case_price)}/cs</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Active Partials */}
            {d.active_partials.length > 0 && (
              <div>
                <h3 className="text-xs font-medium text-zinc-500 uppercase tracking-wide mb-2">Active Specials</h3>
                <div className="space-y-1.5">
                  {d.active_partials.map((p, i) => (
                    <div key={i} className="rounded-lg border border-sky-200 bg-sky-50/50 px-3 py-2 text-sm flex items-center justify-between">
                      <span className="text-zinc-700">{p.description ?? p.kind}</span>
                      <span className="text-xs text-zinc-500">{p.start_date} – {p.end_date}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Price History */}
            {ph && ph.data_points.length > 0 && (
              <PriceHistorySection data={ph.data_points} summary={ph.summary} />
            )}

            {/* Full detail link */}
            <div className="text-center pt-2 border-t border-zinc-100">
              <Link
                to={`/catalog/${code}?d=${distributor}`}
                onClick={onClose}
                className="text-sm text-brand-orange hover:text-brand-orange-dark font-medium"
              >
                Open Full Detail →
              </Link>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function PriceCard({
  label,
  value,
  valueClass = "text-zinc-900",
  sub,
}: {
  label: string;
  value: string;
  valueClass?: string;
  sub?: string;
}) {
  return (
    <div className="rounded-lg border border-zinc-200 bg-white px-3 py-2">
      <div className="text-[10px] text-zinc-500 uppercase tracking-wide">{label}</div>
      <div className={`text-lg font-semibold tabular-nums ${valueClass}`}>{value}</div>
      {sub && <div className="text-[10px] text-zinc-400">{sub}</div>}
    </div>
  );
}

function PriceHistorySection({
  data,
  summary,
}: {
  data: PriceDataPoint[];
  summary: PriceHistorySummary;
}) {
  const now = new Date();
  const curYear = now.getFullYear();
  const curMonth = now.getMonth() + 1;

  return (
    <div>
      <h3 className="text-xs font-medium text-zinc-500 uppercase tracking-wide mb-2">
        Price History ({data.length} editions)
      </h3>
      {summary.price_trend && (
        <div className="text-xs text-zinc-500 mb-2">
          Trend: <span className={`font-medium ${summary.price_trend === "falling" ? "text-emerald-700" : summary.price_trend === "rising" ? "text-red-700" : "text-zinc-600"}`}>
            {summary.price_trend}
          </span>
          {summary.avg_case_cost != null && <span> · Avg: {money(summary.avg_case_cost)}</span>}
        </div>
      )}
      <div className="overflow-x-auto max-h-48">
        <table className="min-w-full text-xs divide-y divide-zinc-100">
          <thead className="bg-brand-tan sticky top-0">
            <tr>
              <th className="px-2 py-1.5 text-left font-medium text-brand-navy">Edition</th>
              <th className="px-2 py-1.5 text-right font-medium text-brand-navy">Case</th>
              <th className="px-2 py-1.5 text-right font-medium text-brand-navy">Bottle</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-50">
            {data.map((dp) => {
              const isCurrent = dp.year === curYear && dp.month === curMonth;
              return (
                <tr key={`${dp.year}-${dp.month}`} className={isCurrent ? "bg-blue-50/40" : ""}>
                  <td className="px-2 py-1 text-zinc-700">
                    {dp.edition_label}
                    {isCurrent && <span className="ml-1 text-[9px] font-semibold text-brand-orange uppercase">Current</span>}
                  </td>
                  <td className="px-2 py-1 text-right tabular-nums">{dp.case_cost != null ? money(dp.case_cost) : "—"}</td>
                  <td className="px-2 py-1 text-right tabular-nums text-zinc-500">{dp.btl_cost != null ? money(dp.btl_cost) : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
