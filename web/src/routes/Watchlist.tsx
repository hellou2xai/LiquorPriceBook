import { useState, useMemo, useRef, useCallback, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ProductLink } from "../components/ProductPopup";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import { watchlistApi, ordersApi } from "../lib/api";
import type { OrderItem, OrderSummary } from "../lib/api";
import { money } from "../lib/fmt";
import { useDistributor } from "../lib/distributor";
import FavoriteButton from "../components/FavoriteButton";
import SortableTable, { useSort, Column } from "../components/SortableTable";
import RowLimitSelect, { useRowLimit } from "../components/RowLimitSelect";

type CartQty = { bottles: number; cases: number };

// ── localStorage helpers ──

type OrderTemplate = { name: string; cart: Record<string, CartQty>; savedAt: string };
type OrderHistoryEntry = { id: string; orderId?: string; name?: string; cart: Record<string, CartQty>; totalCost: number; itemCount: number; savedAt: string };

const TEMPLATES_KEY = "lpb_order_templates";
const HISTORY_KEY = "lpb_order_history";

function loadTemplates(): OrderTemplate[] {
  try { return JSON.parse(localStorage.getItem(TEMPLATES_KEY) ?? "[]"); } catch { return []; }
}
function saveTemplates(t: OrderTemplate[]) { localStorage.setItem(TEMPLATES_KEY, JSON.stringify(t)); }
function loadHistory(): OrderHistoryEntry[] {
  try { return JSON.parse(localStorage.getItem(HISTORY_KEY) ?? "[]"); } catch { return []; }
}
function saveHistory(h: OrderHistoryEntry[]) { localStorage.setItem(HISTORY_KEY, JSON.stringify(h.slice(0, 50))); }

function cartToRecord(cart: Map<string, CartQty>): Record<string, CartQty> {
  const r: Record<string, CartQty> = {};
  cart.forEach((v, k) => { if (v.bottles + v.cases > 0) r[k] = v; });
  return r;
}
function recordToMap(r: Record<string, CartQty>): Map<string, CartQty> {
  return new Map(Object.entries(r));
}

// ── Inline editable note ──

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
      <input type="text" value={value} onChange={(e) => setValue(e.target.value)} onBlur={handleBlur}
        placeholder="Add note..."
        className="w-full min-w-[90px] rounded border border-transparent bg-transparent px-1.5 py-0.5 text-xs text-zinc-600 placeholder:text-zinc-300 hover:border-zinc-200 focus:border-zinc-400 focus:bg-white focus:outline-none"
      />
      {flash && <span className="absolute -top-4 left-0 text-[10px] text-emerald-600 font-medium animate-pulse">Saved</span>}
    </div>
  );
}

// ── Inline target price ──

function TargetPrice({ code, field, initial }: { code: string; field: "target_case_price" | "target_btl_price"; initial: string | null }) {
  const qc = useQueryClient();
  const [value, setValue] = useState(initial ?? "");
  const savedRef = useRef(initial ?? "");
  const [flash, setFlash] = useState(false);

  const update = useMutation({
    mutationFn: (price: string) => {
      const num = parseFloat(price);
      return watchlistApi.update(code, { [field]: Number.isFinite(num) ? num : null });
    },
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
      <input type="text" inputMode="decimal" value={value} onChange={(e) => setValue(e.target.value)} onBlur={handleBlur}
        placeholder="\u2014"
        className="w-16 rounded border border-transparent bg-transparent px-1 py-0.5 text-xs tabular-nums text-right placeholder:text-zinc-300 hover:border-zinc-200 focus:border-zinc-400 focus:bg-white focus:outline-none text-zinc-500"
      />
      {flash && <span className="absolute -top-4 right-0 text-[10px] text-emerald-600 font-medium animate-pulse">Saved</span>}
    </div>
  );
}

// ── RIP Progress Bar ──

function RipProgress({ item, cartCases }: { item: OrderItem; cartCases: number }) {
  if (!item.has_rip || !item.rip_tier_cases) return null;
  const needed = item.rip_tier_cases;
  const pct = Math.min(100, Math.round((cartCases / needed) * 100));
  const unlocked = cartCases >= needed;
  return (
    <div className="mt-1">
      <div className="flex items-center gap-1.5 text-[10px]">
        <div className="flex-1 h-1.5 rounded-full bg-zinc-200 overflow-hidden">
          <div className={`h-full rounded-full transition-all ${unlocked ? "bg-emerald-500" : "bg-amber-400"}`} style={{ width: `${pct}%` }} />
        </div>
        <span className={unlocked ? "text-emerald-700 font-medium" : "text-zinc-500"}>
          {unlocked ? "RIP unlocked!" : `${cartCases}/${needed}CS`}
        </span>
      </div>
    </div>
  );
}

// ── Buy Signal Badge ──

const SIGNAL_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  BUY_NOW:  { bg: "bg-emerald-100 border-emerald-300", text: "text-emerald-800", label: "BUY NOW" },
  GOOD_BUY: { bg: "bg-sky-50 border-sky-200", text: "text-sky-800", label: "GOOD BUY" },
  HOLD:     { bg: "bg-zinc-100 border-zinc-200", text: "text-zinc-600", label: "HOLD" },
  DEFER:    { bg: "bg-amber-50 border-amber-200", text: "text-amber-800", label: "WAIT" },
};

function BuySignalBadge({ signal, reasons }: { signal: string; reasons: string[] }) {
  const s = SIGNAL_STYLES[signal] ?? SIGNAL_STYLES.HOLD;
  return (
    <div className="space-y-0.5">
      <span className={`inline-flex items-center rounded-md border px-1.5 py-0.5 text-[10px] font-bold tracking-wide ${s.bg} ${s.text}`}>
        {s.label}
      </span>
      {reasons.length > 0 && (
        <div className="text-[10px] text-zinc-500 leading-tight">
          {reasons.slice(0, 2).join(" \u00b7 ")}
        </div>
      )}
    </div>
  );
}

// ── Price Trend Indicator ──

function PriceTrend({ item }: { item: OrderItem }) {
  const dir = item.price_direction;
  const pct = item.price_pct_change ? parseFloat(item.price_pct_change) : null;
  if (!dir || dir === "new") return <span className="text-zinc-400 text-[10px]">new</span>;

  const arrow = dir === "down" ? "\u2193" : dir === "up" ? "\u2191" : "\u2192";
  const color = dir === "down" ? "text-emerald-600" : dir === "up" ? "text-red-600" : "text-zinc-400";
  const label = pct !== null ? `${pct > 0 ? "+" : ""}${pct.toFixed(1)}%` : "";

  return (
    <div className="flex flex-col items-end">
      <span className={`text-xs font-medium ${color}`}>{arrow} {label}</span>
      {item.prev_case_cost && (
        <span className="text-[10px] text-zinc-400">was {money(item.prev_case_cost)}</span>
      )}
      {item.at_12m_low && <span className="text-[10px] text-emerald-600 font-medium">12m low</span>}
      {item.at_12m_high && !item.at_12m_low && <span className="text-[10px] text-red-500">12m high</span>}
    </div>
  );
}

// ── CSV export ──

function exportCsv(items: OrderItem[], cart: Map<string, CartQty>) {
  const header = ["SKU", "Description", "Size", "Pack", "Category", "Brand", "Case Price", "RIP Save", "After RIP Case", "GP% w/RIP", "Buy Signal", "Bottles", "Cases", "Line Total", "Note"];
  const rows: string[][] = [header];
  let grandTotal = 0;
  for (const item of items) {
    const qty = cart.get(item.product_code);
    if (!qty || qty.bottles + qty.cases === 0) continue;
    const btlPrice = parseFloat(item.effective_btl ?? item.btl_cost ?? "0");
    const casePrice = parseFloat(item.effective_case ?? item.case_cost ?? "0");
    const lineTotal = qty.bottles * btlPrice + qty.cases * casePrice;
    grandTotal += lineTotal;
    rows.push([
      item.product_code, item.description ?? "", item.size ?? "", String(item.pack ?? ""),
      item.category_display ?? "", item.brand_display ?? "",
      item.case_cost ?? "", item.rip_save_amount ?? "",
      item.effective_case ?? item.case_cost ?? "",
      item.rip_discount_pct ? `${item.rip_discount_pct}%` : "",
      item.buy_signal, String(qty.bottles), String(qty.cases), lineTotal.toFixed(2), item.notes ?? "",
    ]);
  }
  rows.push(["", "", "", "", "", "", "", "", "", "", "", "", "", grandTotal.toFixed(2), "GRAND TOTAL"]);
  const csv = rows.map((r) => r.map((c) => `"${c.replace(/"/g, '""')}"`).join(",")).join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `order-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

// ── Add to Order button ──

function AddToOrderButton({
  code,
  qty,
  draftOrders,
  onAdded,
}: {
  code: string;
  qty: CartQty;
  draftOrders: OrderSummary[];
  onAdded: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState<{ text: string; orderId?: string } | null>(null);
  const [showNew, setShowNew] = useState(false);
  const [newName, setNewName] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  // Close dropdown on outside click
  useEffect(() => {
    if (!open) return;
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  async function addToOrder(orderId: string) {
    setBusy(true);
    try {
      await ordersApi.addItem(orderId, {
        code,
        qty_cases: qty.cases > 0 ? qty.cases : 0,
        qty_bottles: qty.bottles > 0 ? qty.bottles : 0,
      });
      onAdded();
      setFlash({ text: "Added!", orderId });
      setTimeout(() => setFlash(null), 4000);
      setOpen(false);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      setFlash({ text: `Failed: ${msg}` });
      setTimeout(() => setFlash(null), 4000);
    } finally {
      setBusy(false);
    }
  }

  async function createAndAdd() {
    if (!newName.trim()) return;
    setBusy(true);
    try {
      const order = await ordersApi.create({ name: newName.trim() });
      await ordersApi.addItem(order.id, {
        code,
        qty_cases: qty.cases > 0 ? qty.cases : 0,
        qty_bottles: qty.bottles > 0 ? qty.bottles : 0,
      });
      onAdded();
      setFlash({ text: "Created!", orderId: order.id });
      setTimeout(() => setFlash(null), 4000);
      setOpen(false);
      setShowNew(false);
      setNewName("");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      setFlash({ text: `Failed: ${msg}` });
      setTimeout(() => setFlash(null), 4000);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative" ref={ref}>
      {flash ? (
        <span className="text-[10px] font-medium whitespace-nowrap">
          <span className={flash.orderId ? "text-emerald-600" : "text-red-600"}>{flash.text}</span>
          {flash.orderId && (
            <Link to={`/orders/${flash.orderId}`} className="ml-1 text-brand-orange underline hover:text-brand-orange-dark">
              View
            </Link>
          )}
        </span>
      ) : (
        <button
          onClick={() => setOpen(!open)}
          disabled={busy}
          className="rounded border border-zinc-300 bg-brand-tan text-brand-navy px-1.5 py-0.5 text-[10px] hover:bg-zinc-200 whitespace-nowrap disabled:opacity-50"
          title="Add this product to an order"
        >
          + Order
        </button>
      )}
      {open && (
        <div className="absolute right-0 top-full mt-1 z-20 w-52 rounded-lg border border-zinc-200 bg-white shadow-lg py-1">
          {draftOrders.length > 0 && (
            <>
              <div className="px-3 py-1 text-[10px] uppercase tracking-wide text-zinc-400 font-medium">
                Add to draft order
              </div>
              {draftOrders.map((o) => (
                <button
                  key={o.id}
                  onClick={() => addToOrder(o.id)}
                  disabled={busy}
                  className="w-full text-left px-3 py-1.5 text-xs text-zinc-700 hover:bg-brand-tan disabled:opacity-50 flex items-center justify-between"
                >
                  <span className="truncate">{o.name}</span>
                  <span className="text-[10px] text-zinc-400 ml-2">{o.item_count} items</span>
                </button>
              ))}
              <div className="border-t border-zinc-100 my-1" />
            </>
          )}
          {!showNew ? (
            <button
              onClick={() => setShowNew(true)}
              className="w-full text-left px-3 py-1.5 text-xs text-zinc-700 hover:bg-brand-tan font-medium"
            >
              + Create new order...
            </button>
          ) : (
            <div className="px-3 py-2 space-y-1.5">
              <input
                autoFocus
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Order name..."
                className="w-full rounded border border-zinc-300 px-2 py-1 text-xs focus:border-brand-orange focus:outline-none"
                onKeyDown={(e) => { if (e.key === "Enter") createAndAdd(); if (e.key === "Escape") { setShowNew(false); setNewName(""); } }}
              />
              <button
                onClick={createAndAdd}
                disabled={!newName.trim() || busy}
                className="w-full rounded bg-brand-orange px-2 py-1 text-[10px] text-white hover:bg-brand-orange-dark disabled:opacity-50"
              >
                Create & Add
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ══════════════════ Main Component ══════════════════

export default function Watchlist() {
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState<string>("");
  const [cart, setCart] = useState<Map<string, CartQty>>(new Map());
  const [groupByCategory, setGroupByCategory] = useState(false);
  const [templates, setTemplatesState] = useState<OrderTemplate[]>(loadTemplates);
  const [showTemplates, setShowTemplates] = useState(false);
  const [templateName, setTemplateName] = useState("");
  const [history, setHistoryState] = useState<OrderHistoryEntry[]>(loadHistory);
  const [showHistory, setShowHistory] = useState(false);
  const { distributor } = useDistributor();
  const { limit: rowLimit, setLimit: setRowLimit } = useRowLimit(100);

  const { sort: sortConfig, toggle: toggleSort, sorted } = useSort<OrderItem>({ key: "description", direction: "asc" });

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 250);
    return () => clearTimeout(t);
  }, [search]);

  const q = useQuery({
    queryKey: ["watchlist-order", { search: debouncedSearch, category: categoryFilter }, distributor],
    queryFn: () => watchlistApi.order({ search: debouncedSearch || undefined, category: categoryFilter || undefined, distributor }),
    placeholderData: (prev) => prev,
  });

  const qc = useQueryClient();
  const draftOrdersQ = useQuery({
    queryKey: ["orders", { status: "draft" }],
    queryFn: () => ordersApi.list({ status: "draft" }),
    staleTime: 30_000,
  });
  const draftOrders = draftOrdersQ.data ?? [];

  const categories = useMemo(() => {
    if (!q.data) return [];
    const map = new Map<string, string>();
    for (const item of q.data) {
      if (item.category_slug && item.category_display) map.set(item.category_slug, item.category_display);
    }
    return [...map.entries()].sort(([, a], [, b]) => a.localeCompare(b));
  }, [q.data]);

  function getQty(code: string): CartQty { return cart.get(code) ?? { bottles: 0, cases: 0 }; }

  function setQty(code: string, update: Partial<CartQty>) {
    setCart((prev) => {
      const next = new Map(prev);
      const cur = prev.get(code) ?? { bottles: 0, cases: 0 };
      next.set(code, { ...cur, ...update });
      return next;
    });
  }

  // ── Column definitions ──

  const columns = useMemo<Column<OrderItem>[]>(() => [
    {
      key: "favorite",
      label: "",
      render: (item) => <FavoriteButton code={item.product_code} isFavorite={true} />,
      thClassName: "w-7",
    },
    {
      key: "code",
      label: "Code",
      sortable: true,
      sortValue: (item) => item.product_code,
      render: (item) => (
        <span className="text-xs font-mono text-zinc-500">{item.product_code}</span>
      ),
    },
    {
      key: "description",
      label: "Description",
      sortable: true,
      sortValue: (item) => item.description ?? "",
      render: (item) => (
        <div>
          <ProductLink code={item.product_code} distributor={distributor} className="hover:underline font-medium text-brand-navy hover:text-brand-orange text-left">
            {item.description ?? "Unknown"}
          </ProductLink>
          <div className="mt-0.5">
            <BuySignalBadge signal={item.buy_signal} reasons={item.buy_reasons ?? []} />
          </div>
        </div>
      ),
    },
    {
      key: "brand",
      label: "Brand",
      sortable: true,
      sortValue: (item) => item.brand_display ?? "",
      hideBelow: "sm" as const,
      render: (item) => (
        <span className="text-zinc-600 text-xs">{item.brand_display ?? "\u2014"}</span>
      ),
    },
    {
      key: "size",
      label: "Size",
      sortable: true,
      sortValue: (item) => item.size ?? "",
      hideBelow: "sm" as const,
      render: (item) => (
        <span className="text-zinc-600 text-xs">{item.size ?? ""}{item.pack ? ` / ${item.pack}pk` : ""}</span>
      ),
    },
    {
      key: "case_cost",
      label: "Case Cost",
      sortable: true,
      align: "right" as const,
      sortValue: (item) => parseFloat(item.case_cost ?? "999999"),
      render: (item) => (
        <div>
          <span className="tabular-nums">{money(item.case_cost)}</span>
          <div className="mt-0.5"><PriceTrend item={item} /></div>
        </div>
      ),
    },
    {
      key: "btl_cost",
      label: "Btl Cost",
      sortable: true,
      align: "right" as const,
      hideBelow: "md" as const,
      sortValue: (item) => parseFloat(item.btl_cost ?? "999999"),
      render: (item) => (
        <span className="tabular-nums text-xs text-zinc-600">{money(item.btl_cost)}</span>
      ),
    },
    {
      key: "rip_save",
      label: "RIP Save",
      sortable: true,
      align: "right" as const,
      sortValue: (item) => parseFloat(item.rip_save_amount ?? "0"),
      render: (item) => {
        const rips = item.all_rips ?? [];
        if (!item.has_rip || rips.length === 0) return <span className="text-zinc-300 text-xs">{"\u2014"}</span>;
        const best = rips[rips.length - 1];
        return (
          <div className="text-right">
            <span className="text-emerald-700 font-medium text-xs tabular-nums">{money(item.rip_save_amount)}</span>
            <div className="text-[10px] text-zinc-400">{best.tier_cases}CS min{rips.length > 1 ? ` \u00b7 ${rips.length} tiers` : ""}</div>
          </div>
        );
      },
    },
    {
      key: "effective",
      label: "Effective",
      sortable: true,
      align: "right" as const,
      sortValue: (item) => parseFloat(item.effective_case ?? item.case_cost ?? "999999"),
      render: (item) => {
        if (!item.effective_case) return <span className="text-zinc-300 text-xs">{"\u2014"}</span>;
        return (
          <span className="tabular-nums font-medium text-emerald-700">{money(item.effective_case)}</span>
        );
      },
    },
    {
      key: "qty",
      label: "Qty",
      align: "center" as const,
      render: (item) => {
        const qty = getQty(item.product_code);
        return (
          <div className="flex flex-col gap-1 text-xs">
            <div className="flex items-center gap-1">
              <span className="w-8 text-zinc-500 text-[10px]">Btl</span>
              <button onClick={() => setQty(item.product_code, { bottles: Math.max(0, qty.bottles - 1) })} className="rounded border border-zinc-300 bg-white w-5 h-5 flex items-center justify-center hover:bg-zinc-100 disabled:opacity-40 text-xs" disabled={qty.bottles === 0}>-</button>
              <input
                type="number" min={0} value={qty.bottles}
                onChange={(e) => setQty(item.product_code, { bottles: Math.max(0, parseInt(e.target.value) || 0) })}
                className="w-8 text-center tabular-nums font-medium text-xs rounded border border-zinc-200 bg-white py-0 focus:border-zinc-400 focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
              />
              <button onClick={() => setQty(item.product_code, { bottles: qty.bottles + 1 })} className="rounded border border-zinc-300 bg-white w-5 h-5 flex items-center justify-center hover:bg-zinc-100 text-xs">+</button>
            </div>
            <div className="flex items-center gap-1">
              <span className="w-8 text-zinc-500 text-[10px]">Case</span>
              <button onClick={() => setQty(item.product_code, { cases: Math.max(0, qty.cases - 1) })} className="rounded border border-zinc-300 bg-white w-5 h-5 flex items-center justify-center hover:bg-zinc-100 disabled:opacity-40 text-xs" disabled={qty.cases === 0}>-</button>
              <input
                type="number" min={0} value={qty.cases}
                onChange={(e) => setQty(item.product_code, { cases: Math.max(0, parseInt(e.target.value) || 0) })}
                className="w-8 text-center tabular-nums font-medium text-xs rounded border border-zinc-200 bg-white py-0 focus:border-zinc-400 focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
              />
              <button onClick={() => setQty(item.product_code, { cases: qty.cases + 1 })} className="rounded border border-zinc-300 bg-white w-5 h-5 flex items-center justify-center hover:bg-zinc-100 text-xs">+</button>
            </div>
            <RipProgress item={item} cartCases={qty.cases} />
          </div>
        );
      },
    },
    {
      key: "notes",
      label: "Notes",
      render: (item) => <InlineNote code={item.product_code} initial={item.notes} />,
    },
    {
      key: "target",
      label: "Target",
      align: "right" as const,
      hideBelow: "md" as const,
      render: (item) => (
        <TargetPrice code={item.product_code} field="target_case_price" initial={item.target_case_price} />
      ),
    },
    {
      key: "add_to_order",
      label: "",
      render: (item) => {
        const qty = getQty(item.product_code);
        return (
          <AddToOrderButton
            code={item.product_code}
            qty={qty}
            draftOrders={draftOrders}
            onAdded={() => {
              qc.invalidateQueries({ queryKey: ["orders"] });
              qc.invalidateQueries({ queryKey: ["order-detail"] });
            }}
          />
        );
      },
    },
  ], [cart, draftOrders, qc]); // eslint-disable-line react-hooks/exhaustive-deps -- getQty/setQty use cart

  const allItems = useMemo(() => (q.data ? sorted(q.data, columns) : []), [q.data, sorted, columns]);
  const items = useMemo(() => allItems.slice(0, rowLimit), [allItems, rowLimit]);

  const summary = useMemo(() => {
    let totalItems = 0, totalCost = 0;
    const byCat: Record<string, { items: number; cost: number }> = {};
    for (const item of items) {
      const qty = cart.get(item.product_code);
      if (!qty || qty.bottles + qty.cases === 0) continue;
      totalItems += qty.bottles + qty.cases;
      // Use qualifying RIP tier price based on cart cases
      const rips = item.all_rips ?? [];
      const qualified = qty.cases > 0
        ? [...rips].reverse().find((r) => qty.cases >= r.tier_cases)
        : null;
      const casePrice = qualified ? parseFloat(qualified.effective_case ?? item.case_cost ?? "0") : parseFloat(item.case_cost ?? "0");
      const btlPrice = qualified ? parseFloat(qualified.effective_btl ?? item.btl_cost ?? "0") : parseFloat(item.btl_cost ?? "0");
      const lineCost = qty.bottles * btlPrice + qty.cases * casePrice;
      totalCost += lineCost;
      const cat = item.category_display ?? "Uncategorized";
      if (!byCat[cat]) byCat[cat] = { items: 0, cost: 0 };
      byCat[cat].items += qty.bottles + qty.cases;
      byCat[cat].cost += lineCost;
    }
    return { totalItems, totalCost, byCat };
  }, [items, cart]);

  // Signal summary
  const signalCounts = useMemo(() => {
    const c = { BUY_NOW: 0, GOOD_BUY: 0, HOLD: 0, DEFER: 0 };
    for (const item of items) if (item.buy_signal in c) c[item.buy_signal as keyof typeof c]++;
    return c;
  }, [items]);

  // Template actions
  const saveTemplate = useCallback(() => {
    if (!templateName.trim()) return;
    const t: OrderTemplate = { name: templateName.trim(), cart: cartToRecord(cart), savedAt: new Date().toISOString() };
    const updated = [t, ...templates.filter((x) => x.name !== t.name)];
    saveTemplates(updated);
    setTemplatesState(updated);
    setTemplateName("");
  }, [templateName, cart, templates]);

  const loadTemplate = useCallback((t: OrderTemplate) => { setCart(recordToMap(t.cart)); setShowTemplates(false); }, []);
  const deleteTemplate = useCallback((name: string) => { const u = templates.filter((t) => t.name !== name); saveTemplates(u); setTemplatesState(u); }, [templates]);

  const [savingOrder, setSavingOrder] = useState(false);
  const navigate = useNavigate();

  const saveToHistory = useCallback(async () => {
    if (!items.length) return;
    const name = window.prompt("Enter a name for this order:", `Order ${new Date().toLocaleDateString()}`);
    if (!name || !name.trim()) return;
    setSavingOrder(true);
    try {
      // 1. Create real order via API
      const order = await ordersApi.create({ name: name.trim() });
      // 2. Copy ALL tracked items into the order
      const copyResult = await ordersApi.copyFromWatchlist(order.id);
      if (copyResult.added === 0) {
        // Tracked items might already be in the order — try adding individually
        for (const item of items) {
          try {
            const cq = cart.get(item.product_code);
            await ordersApi.addItem(order.id, {
              code: item.product_code,
              qty_cases: cq?.cases ?? 0,
              qty_bottles: cq?.bottles ?? 0,
            });
          } catch { /* item may already exist, that's fine */ }
        }
      }
      // 3. Update quantities for items that have qty set in cart
      const cartRecord = cartToRecord(cart);
      const updatePromises = Object.entries(cartRecord).map(([code, qty]) =>
        ordersApi.updateItem(order.id, code, { qty_cases: qty.cases, qty_bottles: qty.bottles })
          .catch(() => { /* item may not be in this order */ })
      );
      await Promise.all(updatePromises);
      // 4. Invalidate orders cache so Order page shows the new order
      qc.invalidateQueries({ queryKey: ["orders"] });
      qc.invalidateQueries({ queryKey: ["order-detail"] });
      // 5. Save to localStorage history with order ID
      const itemCount = items.length;
      const entry: OrderHistoryEntry = {
        id: Date.now().toString(36),
        orderId: order.id,
        name: name.trim(),
        cart: cartRecord,
        totalCost: summary.totalCost,
        itemCount,
        savedAt: new Date().toISOString(),
      };
      const updated = [entry, ...history];
      saveHistory(updated);
      setHistoryState(updated);
      // 6. Navigate to order detail
      navigate(`/orders/${order.id}`);
    } catch (err) {
      alert(`Failed to create order: ${err instanceof Error ? err.message : "Unknown error"}`);
    } finally {
      setSavingOrder(false);
    }
  }, [cart, items, summary, history, navigate, qc]);

  const loadFromHistory = useCallback((entry: OrderHistoryEntry) => { setCart(recordToMap(entry.cart)); setShowHistory(false); }, []);

  // Persist & restore cart
  useEffect(() => {
    const r = cartToRecord(cart);
    if (Object.keys(r).length > 0) localStorage.setItem("lpb_current_cart", JSON.stringify(r));
  }, [cart]);

  useEffect(() => {
    try { const s = localStorage.getItem("lpb_current_cart"); if (s) setCart(recordToMap(JSON.parse(s))); } catch { /* ignore */ }
  }, []);

  // Grouped view
  const groupedItems = useMemo(() => {
    if (!groupByCategory) return null;
    const groups: Record<string, OrderItem[]> = {};
    for (const item of items) {
      const cat = item.category_display ?? "Uncategorized";
      if (!groups[cat]) groups[cat] = [];
      groups[cat].push(item);
    }
    return Object.entries(groups).sort(([a], [b]) => a.localeCompare(b));
  }, [items, groupByCategory]);

  return (
    <div className="space-y-4">
      <header className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-xl sm:text-2xl font-semibold tracking-tight text-brand-navy">My Order List</h1>
          <p className="text-sm text-zinc-600">
            {q.data ? `${q.data.length} saved product${q.data.length === 1 ? "" : "s"}` : "Loading..."}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button onClick={() => setShowTemplates(!showTemplates)} className="rounded-md border border-zinc-300 bg-brand-tan text-brand-navy px-3 py-1.5 text-xs hover:bg-zinc-200">Templates</button>
          <button onClick={() => setShowHistory(!showHistory)} className="rounded-md border border-zinc-300 bg-brand-tan text-brand-navy px-3 py-1.5 text-xs hover:bg-zinc-200">History</button>
          <button onClick={() => exportCsv(items, cart)} disabled={summary.totalItems === 0} className="rounded-md border border-zinc-300 bg-brand-tan text-brand-navy px-3 py-1.5 text-xs hover:bg-zinc-200 disabled:opacity-40">Export CSV</button>
        </div>
      </header>

      {/* Buy Signal Summary */}
      {items.length > 0 && (
        <div className="flex flex-wrap gap-2 sm:gap-3 text-xs">
          {signalCounts.BUY_NOW > 0 && (
            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 border border-emerald-300 px-2.5 py-1 text-emerald-800 font-medium">
              {signalCounts.BUY_NOW} BUY NOW
            </span>
          )}
          {signalCounts.GOOD_BUY > 0 && (
            <span className="inline-flex items-center gap-1 rounded-full bg-sky-50 border border-sky-200 px-2.5 py-1 text-sky-800 font-medium">
              {signalCounts.GOOD_BUY} Good Buy
            </span>
          )}
          {signalCounts.HOLD > 0 && (
            <span className="inline-flex items-center gap-1 rounded-full bg-zinc-100 border border-zinc-200 px-2.5 py-1 text-zinc-600">
              {signalCounts.HOLD} Hold
            </span>
          )}
          {signalCounts.DEFER > 0 && (
            <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 border border-amber-200 px-2.5 py-1 text-amber-800">
              {signalCounts.DEFER} Wait
            </span>
          )}
        </div>
      )}

      {/* Templates Panel */}
      {showTemplates && (
        <div className="rounded-xl shadow-sm border border-zinc-200 bg-white p-4 space-y-3">
          <h3 className="text-sm font-medium text-brand-navy">Order Templates</h3>
          <div className="flex gap-2">
            <input type="text" value={templateName} onChange={(e) => setTemplateName(e.target.value)} placeholder="Template name..."
              className="flex-1 rounded-md border border-zinc-300 px-2.5 py-1.5 text-sm focus:border-brand-orange focus:outline-none"
              onKeyDown={(e) => { if (e.key === "Enter") saveTemplate(); }} />
            <button onClick={saveTemplate} disabled={!templateName.trim() || summary.totalItems === 0} className="rounded-md bg-brand-orange px-3 py-1.5 text-xs text-white hover:bg-brand-orange-dark disabled:opacity-40">Save Cart</button>
          </div>
          {templates.length === 0 ? (
            <p className="text-xs text-zinc-400">No templates yet.</p>
          ) : (
            <div className="divide-y divide-zinc-100">
              {templates.map((t) => (
                <div key={t.name} className="flex items-center justify-between py-2">
                  <div>
                    <span className="text-sm font-medium text-zinc-700">{t.name}</span>
                    <span className="ml-2 text-xs text-zinc-400">{Object.keys(t.cart).length} items · {new Date(t.savedAt).toLocaleDateString()}</span>
                  </div>
                  <div className="flex gap-2">
                    <button onClick={() => loadTemplate(t)} className="rounded border border-zinc-300 bg-brand-tan text-brand-navy px-2 py-1 text-xs hover:bg-zinc-200">Load</button>
                    <button onClick={() => deleteTemplate(t.name)} className="rounded border border-red-200 px-2 py-1 text-xs text-red-600 hover:bg-red-50">Delete</button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* History Panel */}
      {showHistory && (
        <div className="rounded-xl shadow-sm border border-zinc-200 bg-white p-4 space-y-3">
          <h3 className="text-sm font-medium text-brand-navy">Order History</h3>
          {history.length === 0 ? (
            <p className="text-xs text-zinc-400">No saved orders yet.</p>
          ) : (
            <div className="divide-y divide-zinc-100">
              {history.map((h) => (
                <div key={h.id} className="flex items-center justify-between py-2">
                  <div>
                    {h.orderId ? (
                      <Link to={`/orders/${h.orderId}`} className="text-sm text-zinc-900 font-medium hover:underline">
                        {h.name ?? new Date(h.savedAt).toLocaleDateString()}
                      </Link>
                    ) : (
                      <span className="text-sm text-zinc-700">
                        {new Date(h.savedAt).toLocaleDateString()} {new Date(h.savedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                      </span>
                    )}
                    <span className="ml-2 text-xs text-zinc-400">
                      {new Date(h.savedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} · {h.itemCount} items · {money(h.totalCost)}
                    </span>
                  </div>
                  <div className="flex gap-2">
                    {h.orderId && (
                      <Link to={`/orders/${h.orderId}`} className="rounded border border-zinc-300 bg-brand-tan text-brand-navy px-2 py-1 text-xs hover:bg-zinc-200">
                        View Order
                      </Link>
                    )}
                    <button onClick={() => loadFromHistory(h)} className="rounded border border-zinc-300 bg-brand-tan text-brand-navy px-2 py-1 text-xs hover:bg-zinc-200">Re-order</button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-col md:flex-row gap-3 md:items-center">
        <input type="text" placeholder="Search products..." value={search} onChange={(e) => setSearch(e.target.value)}
          className="flex-1 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm focus:border-brand-orange focus:outline-none" />
        <select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)} className="rounded-md border border-zinc-300 bg-white px-2.5 py-2 text-sm focus:border-brand-orange focus:outline-none">
          <option value="">All categories</option>
          {categories.map(([slug, display]) => (<option key={slug} value={slug}>{display}</option>))}
        </select>
        <label className="flex items-center gap-1.5 text-sm text-zinc-600 cursor-pointer">
          <input type="checkbox" checked={groupByCategory} onChange={(e) => setGroupByCategory(e.target.checked)} className="rounded border-zinc-300 text-brand-orange focus:ring-brand-orange" />
          Group by category
        </label>
      </div>

      {/* Table */}
      <div className="rounded-xl shadow-sm border border-zinc-200 bg-white overflow-hidden">
        {q.isLoading ? (
          <div className="text-center py-12 text-zinc-500">Loading...</div>
        ) : groupedItems ? (
          /* Grouped view: render a SortableTable per category group */
          <div>
            {groupedItems.map(([cat, catItems]) => (
              <div key={cat}>
                <div className="bg-brand-tan px-4 py-2 text-xs font-semibold text-brand-navy uppercase tracking-wide border-b border-zinc-200">
                  {cat} ({catItems.length})
                  {summary.byCat[cat] && <span className="ml-3 font-normal normal-case text-zinc-500">Subtotal: {money(summary.byCat[cat].cost)}</span>}
                </div>
                <SortableTable<OrderItem>
                  columns={columns}
                  data={catItems}
                  sort={sortConfig}
                  onSort={toggleSort}
                  rowKey={(item) => item.product_code}
                  emptyMessage="No items in this category."
                />
              </div>
            ))}
          </div>
        ) : (
          <SortableTable<OrderItem>
            columns={columns}
            data={items}
            sort={sortConfig}
            onSort={toggleSort}
            rowKey={(item) => item.product_code}
            emptyMessage={`No items yet. Browse the Catalog and star products to add them.`}
          />
        )}

        <RowLimitSelect total={allItems.length} limit={rowLimit} onChange={setRowLimit} />

        {/* Summary bar */}
        {items.length > 0 && (
          <div className="border-t border-zinc-200 bg-brand-cream px-3 sm:px-4 py-3 space-y-2">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 text-sm">
              <div className="text-zinc-700">
                {summary.totalItems > 0 ? (
                  <span className="font-medium">{summary.totalItems} item{summary.totalItems === 1 ? "" : "s"} in cart · Estimated total: <span className="tabular-nums">{money(summary.totalCost)}</span></span>
                ) : (
                  <span className="text-zinc-500">{items.length} tracked product{items.length === 1 ? "" : "s"} · Set quantities or save all to an order</span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <button onClick={saveToHistory} disabled={savingOrder} className="rounded-md bg-brand-orange text-white px-3 py-1.5 text-xs font-medium hover:bg-brand-orange-dark disabled:opacity-50">
                  {savingOrder ? "Creating Order..." : "Save as Order"}
                </button>
              </div>
            </div>
            {Object.keys(summary.byCat).length > 1 && (
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-zinc-500">
                {Object.entries(summary.byCat).sort(([a], [b]) => a.localeCompare(b)).map(([cat, data]) => (
                  <span key={cat}>{cat}: {data.items} items · {money(data.cost)}</span>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
