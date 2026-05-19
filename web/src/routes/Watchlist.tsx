import { useState, useMemo, useRef, useCallback, useEffect } from "react";
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

// ── localStorage helpers for templates & history ──

type OrderTemplate = { name: string; cart: Record<string, CartQty>; savedAt: string };
type OrderHistoryEntry = { id: string; cart: Record<string, CartQty>; totalCost: number; itemCount: number; savedAt: string };

const TEMPLATES_KEY = "lpb_order_templates";
const HISTORY_KEY = "lpb_order_history";

function loadTemplates(): OrderTemplate[] {
  try { return JSON.parse(localStorage.getItem(TEMPLATES_KEY) ?? "[]"); } catch { return []; }
}
function saveTemplates(t: OrderTemplate[]) {
  localStorage.setItem(TEMPLATES_KEY, JSON.stringify(t));
}
function loadHistory(): OrderHistoryEntry[] {
  try { return JSON.parse(localStorage.getItem(HISTORY_KEY) ?? "[]"); } catch { return []; }
}
function saveHistory(h: OrderHistoryEntry[]) {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(h.slice(0, 50)));
}

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
      <input
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onBlur={handleBlur}
        placeholder="Add note..."
        className="w-full min-w-[100px] rounded border border-transparent bg-transparent px-1.5 py-0.5 text-xs text-zinc-600 placeholder:text-zinc-300 hover:border-zinc-200 focus:border-zinc-400 focus:bg-white focus:outline-none"
      />
      {flash && (
        <span className="absolute -top-4 left-0 text-[10px] text-emerald-600 font-medium animate-pulse">Saved</span>
      )}
    </div>
  );
}

// ── Inline target price (auto-save on blur) ──

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

  const currentPrice = parseFloat(initial ?? "");
  const targetVal = parseFloat(value);
  const hit = Number.isFinite(currentPrice) && Number.isFinite(targetVal) && currentPrice <= targetVal;

  return (
    <div className="relative">
      <input
        type="text"
        inputMode="decimal"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onBlur={handleBlur}
        placeholder="—"
        className={`w-16 rounded border border-transparent bg-transparent px-1 py-0.5 text-xs tabular-nums text-right placeholder:text-zinc-300 hover:border-zinc-200 focus:border-zinc-400 focus:bg-white focus:outline-none ${hit ? "text-emerald-700 font-medium" : "text-zinc-500"}`}
      />
      {flash && (
        <span className="absolute -top-4 right-0 text-[10px] text-emerald-600 font-medium animate-pulse">Saved</span>
      )}
    </div>
  );
}

// ── RIP Tier Progress ──

function RipProgress({ item, cartCases }: { item: OrderItem; cartCases: number }) {
  if (!item.has_rip || !item.rip_tier_cases) return null;
  const needed = item.rip_tier_cases;
  const pct = Math.min(100, Math.round((cartCases / needed) * 100));
  const unlocked = cartCases >= needed;

  return (
    <div className="mt-1">
      <div className="flex items-center gap-1.5 text-[10px]">
        <div className="flex-1 h-1.5 rounded-full bg-zinc-200 overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${unlocked ? "bg-emerald-500" : "bg-amber-400"}`}
            style={{ width: `${pct}%` }}
          />
        </div>
        <span className={unlocked ? "text-emerald-700 font-medium" : "text-zinc-500"}>
          {unlocked ? "RIP unlocked!" : `${cartCases}/${needed}CS`}
        </span>
      </div>
    </div>
  );
}

// ── CSV export ──

function exportCsv(items: OrderItem[], cart: Map<string, CartQty>) {
  const rows: string[][] = [
    ["SKU", "Description", "Size", "Pack", "Category", "Brand", "Case Price", "Btl Price", "Eff. Case", "Eff. Btl", "RIP Tier", "RIP Save", "Bottles", "Cases", "Line Total", "Note"],
  ];
  let grandTotal = 0;
  for (const item of items) {
    const qty = cart.get(item.product_code);
    if (!qty || qty.bottles + qty.cases === 0) continue;
    const btlPrice = parseFloat(item.effective_btl ?? item.btl_cost ?? "0");
    const casePrice = parseFloat(item.effective_case ?? item.case_cost ?? "0");
    const lineTotal = qty.bottles * btlPrice + qty.cases * casePrice;
    grandTotal += lineTotal;
    rows.push([
      item.product_code,
      item.description ?? "",
      item.size ?? "",
      String(item.pack ?? ""),
      item.category_display ?? "",
      item.brand_display ?? "",
      item.case_cost ?? "",
      item.btl_cost ?? "",
      item.effective_case ?? item.case_cost ?? "",
      item.effective_btl ?? item.btl_cost ?? "",
      item.rip_tier ?? "",
      item.rip_save_amount ?? "",
      String(qty.bottles),
      String(qty.cases),
      lineTotal.toFixed(2),
      item.notes ?? "",
    ]);
  }
  rows.push(["", "", "", "", "", "", "", "", "", "", "", "", "", "", grandTotal.toFixed(2), "GRAND TOTAL"]);

  const csv = rows.map((r) => r.map((c) => `"${c.replace(/"/g, '""')}"`).join(",")).join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `order-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

// ── Main component ──

export default function Watchlist() {
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState<string>("");
  const [sort, setSort] = useState<SortKey>("name");
  const [cart, setCart] = useState<Map<string, CartQty>>(new Map());
  const [groupByCategory, setGroupByCategory] = useState(false);

  // Templates
  const [templates, setTemplatesState] = useState<OrderTemplate[]>(loadTemplates);
  const [showTemplates, setShowTemplates] = useState(false);
  const [templateName, setTemplateName] = useState("");

  // History
  const [history, setHistoryState] = useState<OrderHistoryEntry[]>(loadHistory);
  const [showHistory, setShowHistory] = useState(false);

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

  // Summary with category breakdown
  const summary = useMemo(() => {
    let totalItems = 0;
    let totalCost = 0;
    const byCat: Record<string, { items: number; cost: number }> = {};
    for (const item of items) {
      const qty = cart.get(item.product_code);
      if (!qty) continue;
      const { bottles, cases } = qty;
      if (bottles + cases === 0) continue;
      totalItems += bottles + cases;
      const btlPrice = parseFloat(item.effective_btl ?? item.btl_cost ?? "0");
      const casePrice = parseFloat(item.effective_case ?? item.case_cost ?? "0");
      const lineCost = bottles * btlPrice + cases * casePrice;
      totalCost += lineCost;
      const cat = item.category_display ?? "Uncategorized";
      if (!byCat[cat]) byCat[cat] = { items: 0, cost: 0 };
      byCat[cat].items += bottles + cases;
      byCat[cat].cost += lineCost;
    }
    return { totalItems, totalCost, byCat };
  }, [items, cart]);

  // Price alert check
  const priceAlerts = useMemo(() => {
    const hits: OrderItem[] = [];
    for (const item of items) {
      const target = parseFloat(item.target_case_price ?? "");
      const current = parseFloat(item.effective_case ?? item.case_cost ?? "");
      if (Number.isFinite(target) && Number.isFinite(current) && current <= target) {
        hits.push(item);
      }
    }
    return hits;
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

  const loadTemplate = useCallback((t: OrderTemplate) => {
    setCart(recordToMap(t.cart));
    setShowTemplates(false);
  }, []);

  const deleteTemplate = useCallback((name: string) => {
    const updated = templates.filter((t) => t.name !== name);
    saveTemplates(updated);
    setTemplatesState(updated);
  }, [templates]);

  // History actions
  const saveToHistory = useCallback(() => {
    if (summary.totalItems === 0) return;
    const entry: OrderHistoryEntry = {
      id: Date.now().toString(36),
      cart: cartToRecord(cart),
      totalCost: summary.totalCost,
      itemCount: summary.totalItems,
      savedAt: new Date().toISOString(),
    };
    const updated = [entry, ...history];
    saveHistory(updated);
    setHistoryState(updated);
  }, [cart, summary, history]);

  const loadFromHistory = useCallback((entry: OrderHistoryEntry) => {
    setCart(recordToMap(entry.cart));
    setShowHistory(false);
  }, []);

  // Persist cart to localStorage
  useEffect(() => {
    const r = cartToRecord(cart);
    if (Object.keys(r).length > 0) {
      localStorage.setItem("lpb_current_cart", JSON.stringify(r));
    }
  }, [cart]);

  // Restore cart on mount
  useEffect(() => {
    try {
      const saved = localStorage.getItem("lpb_current_cart");
      if (saved) setCart(recordToMap(JSON.parse(saved)));
    } catch { /* ignore */ }
  }, []);

  // Group items by category
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

  function renderRow(item: OrderItem) {
    const qty = getQty(item.product_code);
    const hasRipPrice = item.has_rip && item.effective_case;
    const targetCase = parseFloat(item.target_case_price ?? "");
    const currentCase = parseFloat(item.effective_case ?? item.case_cost ?? "");
    const hitTarget = Number.isFinite(targetCase) && Number.isFinite(currentCase) && currentCase <= targetCase;

    return (
      <tr key={item.product_code} className={`hover:bg-zinc-50 align-top ${hitTarget ? "bg-emerald-50/40" : ""}`}>
        <td className="px-3 py-2">
          <FavoriteButton code={item.product_code} isFavorite={true} />
        </td>
        <td className="px-3 py-2">
          <Link to={`/catalog/${item.product_code}`} className="hover:underline font-medium text-zinc-900">
            {item.description ?? "Unknown"}
          </Link>
          <div className="text-xs text-zinc-500 mt-0.5">
            {item.size ?? ""}{item.pack ? ` / ${item.pack}pk` : ""} · SKU {item.product_code}
          </div>
        </td>
        <td className="px-3 py-2 text-zinc-600">{item.category_display ?? "\u2014"}</td>
        <td className="px-3 py-2 text-zinc-600">{item.brand_display ?? "\u2014"}</td>
        <td className="px-3 py-2 text-right tabular-nums">{money(item.case_cost)}</td>
        <td className="px-3 py-2 text-right tabular-nums">{money(item.btl_cost)}</td>
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
        <td className={`px-3 py-2 text-right tabular-nums ${hasRipPrice ? "text-emerald-700 font-medium" : ""}`}>
          {money(item.effective_case ?? item.case_cost)}
        </td>
        <td className={`px-3 py-2 text-right tabular-nums ${hasRipPrice ? "text-emerald-700 font-medium" : ""}`}>
          {money(item.effective_btl ?? item.btl_cost)}
        </td>
        <td className="px-3 py-2">
          <TargetPrice code={item.product_code} field="target_case_price" initial={item.target_case_price} />
        </td>
        <td className="px-3 py-2">
          <InlineNote code={item.product_code} initial={item.notes} />
        </td>
        <td className="px-3 py-2">
          <div className="flex flex-col gap-1 text-xs">
            <div className="flex items-center gap-1.5">
              <span className="w-10 text-zinc-500">Btl</span>
              <button onClick={() => setQty(item.product_code, { bottles: Math.max(0, qty.bottles - 1) })} className="rounded border border-zinc-300 bg-white w-6 h-6 flex items-center justify-center hover:bg-zinc-100 disabled:opacity-40" disabled={qty.bottles === 0}>-</button>
              <span className="w-6 text-center tabular-nums font-medium">{qty.bottles}</span>
              <button onClick={() => setQty(item.product_code, { bottles: qty.bottles + 1 })} className="rounded border border-zinc-300 bg-white w-6 h-6 flex items-center justify-center hover:bg-zinc-100">+</button>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-10 text-zinc-500">Case</span>
              <button onClick={() => setQty(item.product_code, { cases: Math.max(0, qty.cases - 1) })} className="rounded border border-zinc-300 bg-white w-6 h-6 flex items-center justify-center hover:bg-zinc-100 disabled:opacity-40" disabled={qty.cases === 0}>-</button>
              <span className="w-6 text-center tabular-nums font-medium">{qty.cases}</span>
              <button onClick={() => setQty(item.product_code, { cases: qty.cases + 1 })} className="rounded border border-zinc-300 bg-white w-6 h-6 flex items-center justify-center hover:bg-zinc-100">+</button>
            </div>
            <RipProgress item={item} cartCases={qty.cases} />
          </div>
        </td>
      </tr>
    );
  }

  return (
    <div className="space-y-5">
      <header className="flex items-start justify-between">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">My Order List</h1>
          <p className="text-sm text-zinc-600">
            {q.data ? `${q.data.length} saved product${q.data.length === 1 ? "" : "s"}` : "Loading..."}
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => setShowTemplates(!showTemplates)} className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-xs hover:bg-zinc-50">
            Templates
          </button>
          <button onClick={() => setShowHistory(!showHistory)} className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-xs hover:bg-zinc-50">
            History
          </button>
          <button
            onClick={() => exportCsv(items, cart)}
            disabled={summary.totalItems === 0}
            className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-xs hover:bg-zinc-50 disabled:opacity-40"
          >
            Export CSV
          </button>
        </div>
      </header>

      {/* Price Alerts Banner */}
      {priceAlerts.length > 0 && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3">
          <p className="text-sm font-medium text-emerald-800">
            {priceAlerts.length} product{priceAlerts.length > 1 ? "s" : ""} hit your target price!
          </p>
          <div className="mt-1 flex flex-wrap gap-2">
            {priceAlerts.map((item) => (
              <span key={item.product_code} className="inline-flex items-center rounded bg-white border border-emerald-200 px-2 py-0.5 text-xs text-emerald-800">
                {item.description?.slice(0, 30)} — now {money(item.effective_case ?? item.case_cost)}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Templates Panel */}
      {showTemplates && (
        <div className="rounded-lg border border-zinc-200 bg-white p-4 space-y-3">
          <h3 className="text-sm font-medium text-zinc-700">Order Templates</h3>
          <div className="flex gap-2">
            <input
              type="text"
              value={templateName}
              onChange={(e) => setTemplateName(e.target.value)}
              placeholder="Template name..."
              className="flex-1 rounded-md border border-zinc-300 px-2.5 py-1.5 text-sm focus:border-zinc-900 focus:outline-none"
              onKeyDown={(e) => { if (e.key === "Enter") saveTemplate(); }}
            />
            <button onClick={saveTemplate} disabled={!templateName.trim() || summary.totalItems === 0} className="rounded-md bg-zinc-900 px-3 py-1.5 text-xs text-white hover:bg-zinc-800 disabled:opacity-40">
              Save Current Cart
            </button>
          </div>
          {templates.length === 0 ? (
            <p className="text-xs text-zinc-400">No saved templates yet. Add items to cart and save.</p>
          ) : (
            <div className="divide-y divide-zinc-100">
              {templates.map((t) => (
                <div key={t.name} className="flex items-center justify-between py-2">
                  <div>
                    <span className="text-sm font-medium text-zinc-700">{t.name}</span>
                    <span className="ml-2 text-xs text-zinc-400">{Object.keys(t.cart).length} items · {new Date(t.savedAt).toLocaleDateString()}</span>
                  </div>
                  <div className="flex gap-2">
                    <button onClick={() => loadTemplate(t)} className="rounded border border-zinc-300 px-2 py-1 text-xs hover:bg-zinc-50">Load</button>
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
        <div className="rounded-lg border border-zinc-200 bg-white p-4 space-y-3">
          <h3 className="text-sm font-medium text-zinc-700">Order History</h3>
          {history.length === 0 ? (
            <p className="text-xs text-zinc-400">No saved orders yet. Use "Save Order" after building your cart.</p>
          ) : (
            <div className="divide-y divide-zinc-100">
              {history.map((h) => (
                <div key={h.id} className="flex items-center justify-between py-2">
                  <div>
                    <span className="text-sm text-zinc-700">{new Date(h.savedAt).toLocaleDateString()} {new Date(h.savedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
                    <span className="ml-2 text-xs text-zinc-400">{h.itemCount} items · {money(h.totalCost)}</span>
                  </div>
                  <button onClick={() => loadFromHistory(h)} className="rounded border border-zinc-300 px-2 py-1 text-xs hover:bg-zinc-50">
                    Re-order
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-col md:flex-row gap-3 md:items-center">
        <input
          type="text"
          placeholder="Search products..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm focus:border-zinc-900 focus:outline-none"
        />
        <select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)} className="rounded-md border border-zinc-300 bg-white px-2.5 py-2 text-sm">
          <option value="">All categories</option>
          {categories.map((c) => (<option key={c} value={c}>{c}</option>))}
        </select>
        <select value={sort} onChange={(e) => setSort(e.target.value as SortKey)} className="rounded-md border border-zinc-300 bg-white px-2.5 py-2 text-sm">
          <option value="name">Product A-Z</option>
          <option value="price_asc">Price low-high</option>
          <option value="price_desc">Price high-low</option>
          <option value="rip_save">Best RIP savings</option>
        </select>
        <label className="flex items-center gap-1.5 text-sm text-zinc-600 cursor-pointer">
          <input type="checkbox" checked={groupByCategory} onChange={(e) => setGroupByCategory(e.target.checked)} className="rounded border-zinc-300" />
          Group by category
        </label>
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
                <th className="px-3 py-2 text-right">Target</th>
                <th className="px-3 py-2">Note</th>
                <th className="px-3 py-2 text-center">Qty in Cart</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {q.isLoading ? (
                <tr><td colSpan={12} className="px-4 py-6 text-center text-zinc-500">Loading...</td></tr>
              ) : items.length === 0 ? (
                <tr>
                  <td colSpan={12} className="px-4 py-6 text-center text-zinc-500">
                    No items yet. Browse the <Link to="/catalog" className="text-zinc-900 underline">Catalog</Link> and star products to add them.
                  </td>
                </tr>
              ) : groupedItems ? (
                groupedItems.map(([cat, catItems]) => (
                  <>
                    <tr key={`cat-${cat}`} className="bg-zinc-100">
                      <td colSpan={12} className="px-4 py-2 text-xs font-semibold text-zinc-700 uppercase tracking-wide">
                        {cat} ({catItems.length})
                        {summary.byCat[cat] && (
                          <span className="ml-3 font-normal normal-case text-zinc-500">
                            Subtotal: {money(summary.byCat[cat].cost)}
                          </span>
                        )}
                      </td>
                    </tr>
                    {catItems.map(renderRow)}
                  </>
                ))
              ) : (
                items.map(renderRow)
              )}
            </tbody>
          </table>
        </div>

        {/* Summary bar */}
        {summary.totalItems > 0 && (
          <div className="border-t border-zinc-200 bg-zinc-50 px-4 py-3 space-y-2">
            <div className="flex items-center justify-between text-sm">
              <div className="text-zinc-700 font-medium">
                {summary.totalItems} item{summary.totalItems === 1 ? "" : "s"} in cart
              </div>
              <div className="flex items-center gap-4">
                <button onClick={saveToHistory} className="rounded-md border border-zinc-300 bg-white px-3 py-1 text-xs hover:bg-zinc-50">
                  Save Order
                </button>
                <span className="text-zinc-900 font-semibold tabular-nums">
                  Estimated total: {money(summary.totalCost)}
                </span>
              </div>
            </div>
            {/* Category subtotals */}
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
