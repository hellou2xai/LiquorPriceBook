import { useState, useMemo } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ordersApi } from "../lib/api";
import type { OrderLine, OrderRecommendation } from "../lib/api";
import { money } from "../lib/fmt";
import SortableTable, { useSort, Column } from "../components/SortableTable";

// ── Constants ──

const DIVISIONS = ["L", "S", "D", "GS", "FB", "JD", "IV"] as const;

const STATUS_STYLE: Record<string, string> = {
  draft: "bg-zinc-100 border-zinc-300 text-zinc-700",
  submitted: "bg-blue-50 border-blue-200 text-blue-800",
  completed: "bg-emerald-50 border-emerald-200 text-emerald-800",
};

const DIVISION_COLORS: Record<string, string> = {
  L: "bg-violet-100 text-violet-800",
  S: "bg-sky-100 text-sky-800",
  D: "bg-amber-100 text-amber-800",
  GS: "bg-emerald-100 text-emerald-800",
  FB: "bg-rose-100 text-rose-800",
  JD: "bg-orange-100 text-orange-800",
  IV: "bg-indigo-100 text-indigo-800",
};

const REC_STYLE: Record<string, string> = {
  closeout: "bg-rose-50 border-rose-200 text-rose-800",
  defer: "bg-amber-50 border-amber-200 text-amber-800",
  rip_optimizer: "bg-sky-50 border-sky-200 text-sky-800",
};

// ── Inline editable name ──

function InlineName({
  value,
  onSave,
}: {
  value: string;
  onSave: (v: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);

  if (!editing) {
    return (
      <h1
        className="text-2xl font-semibold tracking-tight cursor-pointer hover:underline decoration-zinc-300 underline-offset-4"
        onClick={() => {
          setDraft(value);
          setEditing(true);
        }}
        title="Click to rename"
      >
        {value}
      </h1>
    );
  }

  return (
    <input
      autoFocus
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => {
        setEditing(false);
        if (draft.trim() && draft.trim() !== value) onSave(draft.trim());
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          setEditing(false);
          if (draft.trim() && draft.trim() !== value) onSave(draft.trim());
        }
        if (e.key === "Escape") {
          setEditing(false);
          setDraft(value);
        }
      }}
      className="text-2xl font-semibold tracking-tight border-b-2 border-zinc-400 bg-transparent outline-none w-full max-w-md"
    />
  );
}

// ── Inline editable note for a line item ──

function InlineLineNote({
  value,
  onSave,
}: {
  value: string | null;
  onSave: (v: string) => void;
}) {
  const [draft, setDraft] = useState(value ?? "");

  function handleBlur() {
    if (draft !== (value ?? "")) onSave(draft);
  }

  return (
    <input
      type="text"
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={handleBlur}
      placeholder="Add note..."
      className="w-full min-w-[80px] rounded border border-transparent bg-transparent px-1.5 py-0.5 text-xs text-zinc-600 placeholder:text-zinc-300 hover:border-zinc-200 focus:border-zinc-400 focus:bg-white focus:outline-none"
    />
  );
}

// ── Qty stepper ──

function QtyStepper({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="flex items-center gap-1">
      <span className="w-7 text-zinc-500 text-[10px]">{label}</span>
      <button
        onClick={() => onChange(Math.max(0, value - 1))}
        disabled={value === 0}
        className="rounded border border-zinc-300 bg-white w-5 h-5 flex items-center justify-center hover:bg-zinc-100 disabled:opacity-40 text-xs"
      >
        -
      </button>
      <span className="w-6 text-center tabular-nums font-medium text-xs">
        {value}
      </span>
      <button
        onClick={() => onChange(value + 1)}
        className="rounded border border-zinc-300 bg-white w-5 h-5 flex items-center justify-center hover:bg-zinc-100 text-xs"
      >
        +
      </button>
    </div>
  );
}

// ── Recommendation badge ──

function RecBadge({ rec }: { rec: OrderRecommendation }) {
  const style = REC_STYLE[rec.type] ?? "bg-zinc-50 border-zinc-200 text-zinc-700";
  return (
    <span
      className={`inline-flex items-center rounded-md border px-1.5 py-0.5 text-[10px] font-medium ${style}`}
      title={rec.message}
    >
      {rec.type === "closeout" ? "CLO" : rec.type === "defer" ? "WAIT" : "RIP"}
    </span>
  );
}

// ── Collapsible recommendation banners ──

function RecommendationBanners({ recs }: { recs: OrderRecommendation[] }) {
  const [collapsed, setCollapsed] = useState(false);

  if (recs.length === 0) return null;

  return (
    <section className="space-y-2">
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="flex items-center gap-2 text-sm font-medium text-zinc-700 hover:text-zinc-900"
      >
        <svg
          className={`h-3.5 w-3.5 transition-transform ${collapsed ? "" : "rotate-90"}`}
          viewBox="0 0 12 12"
          fill="currentColor"
        >
          <path d="M4 2l5 4-5 4V2z" />
        </svg>
        Recommendations ({recs.length})
      </button>
      {!collapsed && (
        <div className="space-y-2">
          {recs.map((rec, i) => {
            const style =
              REC_STYLE[rec.type] ?? "bg-zinc-50 border-zinc-200 text-zinc-700";
            return (
              <div
                key={i}
                className={`rounded-lg border px-4 py-3 text-sm ${style}`}
              >
                <span className="font-medium uppercase text-[10px] tracking-wide mr-2">
                  {rec.type}
                </span>
                <span className="text-[10px] uppercase tracking-wide text-zinc-400 mr-2">
                  {rec.priority}
                </span>
                {rec.message}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

// ══════════════════ Main Component ══════════════════

export default function OrderDetailPage() {
  const { id = "" } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();

  const [divisionFilter, setDivisionFilter] = useState<string>("");
  const [addCode, setAddCode] = useState("");

  // ── Queries ──

  const orderQ = useQuery({
    queryKey: ["order-detail", id],
    queryFn: () => ordersApi.get(id),
    enabled: !!id,
  });

  const order = orderQ.data;
  const isDraft = order?.status === "draft";

  // ── Mutations ──

  const invalidate = () => qc.invalidateQueries({ queryKey: ["order-detail", id] });

  const updateOrder = useMutation({
    mutationFn: (body: Parameters<typeof ordersApi.update>[1]) =>
      ordersApi.update(id, body),
    onSuccess: invalidate,
  });

  const deleteOrder = useMutation({
    mutationFn: () => ordersApi.remove(id),
    onSuccess: () => navigate("/orders"),
  });

  const copyFromWatchlist = useMutation({
    mutationFn: () => ordersApi.copyFromWatchlist(id),
    onSuccess: invalidate,
  });

  const submitOrder = useMutation({
    mutationFn: () => ordersApi.submit(id),
    onSuccess: invalidate,
  });

  const updateItem = useMutation({
    mutationFn: ({
      code,
      body,
    }: {
      code: string;
      body: Parameters<typeof ordersApi.updateItem>[2];
    }) => ordersApi.updateItem(id, code, body),
    onSuccess: invalidate,
  });

  const addItem = useMutation({
    mutationFn: (code: string) => ordersApi.addItem(id, { code }),
    onSuccess: () => {
      setAddCode("");
      invalidate();
    },
  });

  const removeItem = useMutation({
    mutationFn: (code: string) => ordersApi.removeItem(id, code),
    onSuccess: invalidate,
  });

  // ── Export via fetch + blob ──

  async function handleExport() {
    const url = ordersApi.exportUrl(id, "xlsx", divisionFilter || undefined);
    try {
      const res = await fetch(url, {
        headers: {
          Authorization:
            localStorage.getItem("lpb_auth_token")
              ? `Bearer ${localStorage.getItem("lpb_auth_token")}`
              : "",
        },
      });
      if (!res.ok) throw new Error("Export failed");
      const blob = await res.blob();
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = `order-${order?.name ?? id}.xlsx`;
      a.click();
      URL.revokeObjectURL(blobUrl);
    } catch {
      window.open(url, "_blank");
    }
  }

  // ── Filtered items ──

  const filteredItems = useMemo(() => {
    if (!order) return [];
    if (!divisionFilter) return order.items;
    return order.items.filter((item) => {
      if (!item.divisions) return false;
      return item.divisions
        .split(/[\s,]+/)
        .some((d) => d.toUpperCase() === divisionFilter.toUpperCase());
    });
  }, [order, divisionFilter]);

  // ── Sort ──

  const { sort, toggle, sorted } = useSort<OrderLine>({ key: "description", direction: "asc" });

  // ── Columns ──

  const columns: Column<OrderLine>[] = useMemo(
    () => [
      {
        key: "description",
        label: "Product",
        sortable: true,
        sortValue: (item) => item.description ?? "",
        render: (item) => (
          <div>
            <Link
              to={`/catalog/${item.product_code}`}
              className="font-medium text-zinc-900 hover:underline"
            >
              {item.description ?? "Unknown"}
            </Link>
            <div className="text-[10px] text-zinc-400 mt-0.5">
              {item.size ?? ""}{item.pack ? ` / ${item.pack}pk` : ""} ·{" "}
              <span className="font-mono">{item.product_code}</span>
            </div>
          </div>
        ),
      },
      {
        key: "brand",
        label: "Brand",
        sortable: true,
        sortValue: (item) => item.brand_display ?? "",
        render: (item) => (
          <span className="text-xs text-zinc-600">{item.brand_display ?? "\u2014"}</span>
        ),
      },
      {
        key: "category",
        label: "Category",
        sortable: true,
        sortValue: (item) => item.category_display ?? "",
        render: (item) => (
          <span className="text-xs text-zinc-600">{item.category_display ?? "\u2014"}</span>
        ),
      },
      {
        key: "divisions",
        label: "Div",
        sortable: true,
        sortValue: (item) => item.divisions ?? "",
        render: (item) => (
          <span className="text-[10px] font-mono text-zinc-500">
            {item.divisions ?? "\u2014"}
          </span>
        ),
      },
      {
        key: "case_cost",
        label: "Case Cost",
        sortable: true,
        align: "right" as const,
        sortValue: (item) =>
          item.case_cost ? parseFloat(item.case_cost) : null,
        render: (item) => (
          <span className="tabular-nums">{money(item.case_cost)}</span>
        ),
      },
      {
        key: "rip_save",
        label: "RIP Save",
        sortable: true,
        align: "right" as const,
        sortValue: (item) =>
          item.best_rip_save ? parseFloat(item.best_rip_save) : null,
        render: (item) =>
          item.has_rip && item.best_rip_save ? (
            <span className="text-emerald-700 font-medium tabular-nums">
              {money(item.best_rip_save)}
            </span>
          ) : (
            <span className="text-zinc-300">\u2014</span>
          ),
      },
      {
        key: "line_effective_unit",
        label: "After RIP",
        sortable: true,
        align: "right" as const,
        sortValue: (item) => {
          if (!item.case_cost) return null;
          const base = parseFloat(item.case_cost);
          const save = item.best_rip_save ? parseFloat(item.best_rip_save) : 0;
          return base - save;
        },
        render: (item) => {
          if (!item.case_cost) return <span className="text-zinc-300">\u2014</span>;
          const base = parseFloat(item.case_cost);
          const save = item.best_rip_save ? parseFloat(item.best_rip_save) : 0;
          const after = base - save;
          return (
            <span
              className={`tabular-nums font-medium ${save > 0 ? "text-emerald-700" : ""}`}
            >
              {money(after)}
            </span>
          );
        },
      },
      {
        key: "qty_cases",
        label: "Qty Cases",
        sortable: true,
        align: "center" as const,
        sortValue: (item) => item.qty_cases,
        render: (item) => (
          <QtyStepper
            label="CS"
            value={item.qty_cases}
            onChange={(v) =>
              updateItem.mutate({
                code: item.product_code,
                body: { qty_cases: v },
              })
            }
          />
        ),
      },
      {
        key: "qty_bottles",
        label: "Qty Btls",
        sortable: true,
        align: "center" as const,
        sortValue: (item) => item.qty_bottles,
        render: (item) => (
          <QtyStepper
            label="Btl"
            value={item.qty_bottles}
            onChange={(v) =>
              updateItem.mutate({
                code: item.product_code,
                body: { qty_bottles: v },
              })
            }
          />
        ),
      },
      {
        key: "line_invoice",
        label: "Line Invoice",
        sortable: true,
        align: "right" as const,
        sortValue: (item) =>
          item.line_invoice ? parseFloat(item.line_invoice) : null,
        render: (item) => (
          <span className="tabular-nums">{money(item.line_invoice)}</span>
        ),
      },
      {
        key: "line_rip_rebate",
        label: "Line RIP",
        sortable: true,
        align: "right" as const,
        sortValue: (item) =>
          item.line_rip_rebate ? parseFloat(item.line_rip_rebate) : null,
        render: (item) =>
          item.line_rip_rebate &&
          parseFloat(item.line_rip_rebate) > 0 ? (
            <span className="tabular-nums text-amber-700 font-medium">
              {money(item.line_rip_rebate)}
            </span>
          ) : (
            <span className="text-zinc-300">\u2014</span>
          ),
      },
      {
        key: "line_effective",
        label: "Line Effective",
        sortable: true,
        align: "right" as const,
        sortValue: (item) =>
          item.line_effective ? parseFloat(item.line_effective) : null,
        render: (item) => (
          <span className="tabular-nums font-medium text-emerald-700">
            {money(item.line_effective)}
          </span>
        ),
      },
      {
        key: "notes",
        label: "Notes",
        sortable: false,
        render: (item) => (
          <InlineLineNote
            value={item.notes}
            onSave={(v) =>
              updateItem.mutate({
                code: item.product_code,
                body: { notes: v },
              })
            }
          />
        ),
      },
      {
        key: "recs",
        label: "Recs",
        sortable: false,
        render: (item) => (
          <div className="flex gap-1 flex-wrap">
            {item.recommendations.map((r, i) => (
              <RecBadge key={i} rec={r} />
            ))}
            {isDraft && (
              <button
                onClick={() => removeItem.mutate(item.product_code)}
                className="ml-1 rounded text-zinc-400 hover:text-red-600 text-xs"
                title="Remove item"
              >
                <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="currentColor">
                  <path d="M5.5 5.5A.5.5 0 016 6v6a.5.5 0 01-1 0V6a.5.5 0 01.5-.5zm2.5 0a.5.5 0 01.5.5v6a.5.5 0 01-1 0V6a.5.5 0 01.5-.5zm3 .5a.5.5 0 00-1 0v6a.5.5 0 001 0V6z" />
                  <path
                    fillRule="evenodd"
                    d="M14.5 3a1 1 0 01-1 1H13v9a2 2 0 01-2 2H5a2 2 0 01-2-2V4h-.5a1 1 0 010-2H6a1 1 0 011-1h2a1 1 0 011 1h3.5a1 1 0 011 1zM4.118 4L4 4.059V13a1 1 0 001 1h6a1 1 0 001-1V4.059L11.882 4H4.118zM2.5 3a.5.5 0 000 1h11a.5.5 0 000-1h-11z"
                  />
                </svg>
              </button>
            )}
          </div>
        ),
      },
    ],
    [isDraft, updateItem, removeItem],
  );

  const sortedItems = sorted(filteredItems, columns);

  // ── Summaries ──

  const totals = useMemo(() => {
    if (!order) return { items: 0, cases: 0, bottles: 0 };
    return {
      items: filteredItems.length,
      cases: filteredItems.reduce((s, i) => s + i.qty_cases, 0),
      bottles: filteredItems.reduce((s, i) => s + i.qty_bottles, 0),
    };
  }, [order, filteredItems]);

  // ── Loading / Error states ──

  if (!orderQ.data && orderQ.isLoading) {
    return (
      <div className="flex items-center justify-center py-24 text-zinc-500">
        Loading order...
      </div>
    );
  }
  if (orderQ.isError) {
    return (
      <div className="flex items-center justify-center py-24 text-red-700">
        Failed to load order.
      </div>
    );
  }
  if (!order) return null;

  const payment = order.payment;

  return (
    <div className="space-y-6">
      {/* ── 1. Header Bar ── */}
      <header className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-3">
          <Link
            to="/orders"
            className="flex items-center justify-center rounded-md border border-zinc-200 bg-white w-8 h-8 hover:bg-zinc-50"
            title="Back to orders"
          >
            <svg className="h-4 w-4 text-zinc-600" viewBox="0 0 16 16" fill="currentColor">
              <path
                fillRule="evenodd"
                d="M11.354 1.646a.5.5 0 010 .708L5.707 8l5.647 5.646a.5.5 0 01-.708.708l-6-6a.5.5 0 010-.708l6-6a.5.5 0 01.708 0z"
              />
            </svg>
          </Link>
          <div className="space-y-1">
            <div className="flex items-center gap-2 flex-wrap">
              <InlineName
                value={order.name}
                onSave={(name) => updateOrder.mutate({ name })}
              />
              {order.division && (
                <span
                  className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-[10px] font-bold tracking-wide ${DIVISION_COLORS[order.division] ?? "bg-zinc-100 text-zinc-700"}`}
                >
                  {order.division}
                </span>
              )}
              <span
                className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-[10px] font-medium tracking-wide ${STATUS_STYLE[order.status] ?? STATUS_STYLE.draft}`}
              >
                {order.status.toUpperCase()}
              </span>
            </div>
            <div className="text-xs text-zinc-500">
              Created {new Date(order.created_at).toLocaleDateString()} · Updated{" "}
              {new Date(order.updated_at).toLocaleDateString()}
              {order.submitted_at &&
                ` · Submitted ${new Date(order.submitted_at).toLocaleDateString()}`}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={() => copyFromWatchlist.mutate()}
            disabled={copyFromWatchlist.isPending}
            className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-xs font-medium hover:bg-zinc-50 disabled:opacity-50"
          >
            {copyFromWatchlist.isPending ? "Copying..." : "Copy from Tracked"}
          </button>
          <button
            onClick={handleExport}
            className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-xs font-medium hover:bg-zinc-50"
          >
            Export Excel
          </button>
          {isDraft && (
            <button
              onClick={() => submitOrder.mutate()}
              disabled={submitOrder.isPending}
              className="rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {submitOrder.isPending ? "Submitting..." : "Submit Order"}
            </button>
          )}
          {isDraft && (
            <button
              onClick={() => {
                if (window.confirm("Delete this order? This cannot be undone.")) {
                  deleteOrder.mutate();
                }
              }}
              disabled={deleteOrder.isPending}
              className="rounded-md border border-red-200 bg-white px-3 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-50"
            >
              Delete
            </button>
          )}
        </div>
      </header>

      {/* ── 2. Division Selector ── */}
      <div className="flex items-center gap-2 flex-wrap">
        <button
          onClick={() => setDivisionFilter("")}
          className={`rounded-full px-3 py-1 text-xs font-medium border transition-colors ${
            !divisionFilter
              ? "bg-zinc-900 text-white border-zinc-900"
              : "bg-white text-zinc-600 border-zinc-300 hover:bg-zinc-50"
          }`}
        >
          All
        </button>
        {DIVISIONS.map((div) => (
          <button
            key={div}
            onClick={() =>
              setDivisionFilter(divisionFilter === div ? "" : div)
            }
            className={`rounded-full px-3 py-1 text-xs font-medium border transition-colors ${
              divisionFilter === div
                ? "bg-zinc-900 text-white border-zinc-900"
                : "bg-white text-zinc-600 border-zinc-300 hover:bg-zinc-50"
            }`}
          >
            {div}
          </button>
        ))}
      </div>

      {/* ── 3. Payment Analysis Panel ── */}
      <section className="space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Invoice total */}
          <div className="rounded-lg border border-zinc-200 bg-white p-4">
            <div className="text-[10px] uppercase tracking-wide text-zinc-500">
              Payment Needed Now (Invoice)
            </div>
            <div className="mt-1 text-2xl font-semibold tracking-tight tabular-nums text-zinc-900">
              {money(payment.invoice_total)}
            </div>
          </div>
          {/* RIP Rebate */}
          <div className="rounded-lg border border-amber-200 bg-amber-50/50 p-4">
            <div className="text-[10px] uppercase tracking-wide text-amber-700">
              RIP Rebate (cheque later)
            </div>
            <div className="mt-1 text-2xl font-semibold tracking-tight tabular-nums text-amber-800">
              {money(payment.rip_rebate_total)}
            </div>
          </div>
          {/* Effective Cost */}
          <div className="rounded-lg border border-emerald-200 bg-emerald-50/50 p-4">
            <div className="text-[10px] uppercase tracking-wide text-emerald-700">
              Effective Cost
            </div>
            <div className="mt-1 text-2xl font-bold tracking-tight tabular-nums text-emerald-800">
              {money(payment.effective_total)}
            </div>
          </div>
        </div>

        {/* RIP as % of order */}
        {payment.rip_pct_of_order && (
          <div className="text-sm text-zinc-600">
            RIP as % of order:{" "}
            <span className="font-medium text-amber-700">
              {parseFloat(payment.rip_pct_of_order).toFixed(1)}%
            </span>
          </div>
        )}

        {/* By Category breakdown */}
        {payment.by_category.length > 0 && (
          <div className="rounded-lg border border-zinc-200 bg-white overflow-hidden">
            <div className="border-b border-zinc-200 px-4 py-2 text-xs font-medium text-zinc-700 uppercase tracking-wide">
              By Category
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm divide-y divide-zinc-100">
                <thead className="bg-zinc-50/80 text-[10px] uppercase tracking-wide text-zinc-500">
                  <tr>
                    <th className="px-4 py-2 text-left font-medium">Category</th>
                    <th className="px-4 py-2 text-right font-medium">Items</th>
                    <th className="px-4 py-2 text-right font-medium">Invoice</th>
                    <th className="px-4 py-2 text-right font-medium">Rebate</th>
                    <th className="px-4 py-2 text-right font-medium">Effective</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-100">
                  {payment.by_category.map((cat) => (
                    <tr key={cat.category} className="hover:bg-zinc-50">
                      <td className="px-4 py-2 text-zinc-700">{cat.category}</td>
                      <td className="px-4 py-2 text-right tabular-nums text-zinc-600">
                        {cat.item_count}
                      </td>
                      <td className="px-4 py-2 text-right tabular-nums">
                        {money(cat.invoice)}
                      </td>
                      <td className="px-4 py-2 text-right tabular-nums text-amber-700">
                        {money(cat.rebate)}
                      </td>
                      <td className="px-4 py-2 text-right tabular-nums font-medium text-emerald-700">
                        {money(cat.effective)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>

      {/* ── 4. Recommendations Banner ── */}
      <RecommendationBanners recs={order.recommendations} />

      {/* ── 5. Product Table ── */}
      <section className="rounded-lg border border-zinc-200 bg-white overflow-hidden">
        <SortableTable<OrderLine>
          columns={columns}
          data={sortedItems}
          sort={sort}
          onSort={toggle}
          rowKey={(item) => item.product_code}
          emptyMessage="No items in this order yet."
          className={sortedItems.some((i) => i.is_closeout) ? "[&_tr]:relative" : ""}
        />
      </section>

      {/* ── 6. Add Product Panel ── */}
      {isDraft && (
        <section className="rounded-lg border border-zinc-200 bg-white p-4">
          <div className="text-xs font-medium text-zinc-700 uppercase tracking-wide mb-3">
            Add Product
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const code = addCode.trim();
              if (code) addItem.mutate(code);
            }}
            className="flex gap-2"
          >
            <input
              type="text"
              value={addCode}
              onChange={(e) => setAddCode(e.target.value)}
              placeholder="Product code (e.g. 12345)"
              className="flex-1 max-w-xs rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm focus:border-zinc-900 focus:outline-none"
            />
            <button
              type="submit"
              disabled={!addCode.trim() || addItem.isPending}
              className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-50"
            >
              {addItem.isPending ? "Adding..." : "Add"}
            </button>
          </form>
          {addItem.isError && (
            <div className="mt-2 text-xs text-red-600">
              Failed to add item. Check the product code and try again.
            </div>
          )}
        </section>
      )}

      {/* ── 7. Summary Footer ── */}
      <footer className="rounded-lg border border-zinc-200 bg-zinc-50 p-4">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
          <div className="flex gap-6 text-sm text-zinc-600">
            <div>
              <span className="text-zinc-400 text-xs uppercase tracking-wide mr-1">
                Items
              </span>
              <span className="font-medium text-zinc-900">{totals.items}</span>
            </div>
            <div>
              <span className="text-zinc-400 text-xs uppercase tracking-wide mr-1">
                Cases
              </span>
              <span className="font-medium text-zinc-900 tabular-nums">
                {totals.cases}
              </span>
            </div>
            <div>
              <span className="text-zinc-400 text-xs uppercase tracking-wide mr-1">
                Bottles
              </span>
              <span className="font-medium text-zinc-900 tabular-nums">
                {totals.bottles}
              </span>
            </div>
          </div>
          <div className="flex gap-6 text-sm">
            <div>
              <span className="text-zinc-400 text-xs uppercase tracking-wide mr-1">
                Invoice
              </span>
              <span className="font-medium tabular-nums">
                {money(payment.invoice_total)}
              </span>
            </div>
            <div>
              <span className="text-amber-600 text-xs uppercase tracking-wide mr-1">
                RIP Rebate
              </span>
              <span className="font-medium tabular-nums text-amber-700">
                {money(payment.rip_rebate_total)}
              </span>
            </div>
            <div>
              <span className="text-emerald-600 text-xs uppercase tracking-wide mr-1">
                Effective
              </span>
              <span className="font-bold tabular-nums text-emerald-800">
                {money(payment.effective_total)}
              </span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
