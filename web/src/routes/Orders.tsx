import { useState, useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ordersApi } from "../lib/api";
import type { OrderSummary } from "../lib/api";
import { money } from "../lib/fmt";
import SortableTable, { useSort, Column } from "../components/SortableTable";

const STATUSES = ["all", "draft", "submitted", "completed"] as const;
const DIVISIONS = ["all", "L", "S", "D", "GS", "FB", "JD", "IV"] as const;

type StatusFilter = (typeof STATUSES)[number];
type DivisionFilter = (typeof DIVISIONS)[number];

const statusBadge: Record<string, string> = {
  draft: "bg-zinc-100 text-zinc-600 border-zinc-200",
  submitted: "bg-blue-50 text-blue-700 border-blue-200",
  completed: "bg-emerald-50 text-emerald-700 border-emerald-200",
};

function StatusBadge({ status }: { status: string }) {
  const cls = statusBadge[status] ?? "bg-zinc-100 text-zinc-600 border-zinc-200";
  return (
    <span className={`inline-flex items-center rounded-md border px-1.5 py-0.5 text-xs font-medium capitalize ${cls}`}>
      {status}
    </span>
  );
}

const columns: Column<OrderSummary>[] = [
  {
    key: "name",
    label: "Name",
    sortable: true,
    render: (o) => (
      <Link to={`/orders/${o.id}`} className="font-medium text-zinc-900 hover:underline" onClick={(e) => e.stopPropagation()}>
        {o.name}
      </Link>
    ),
    sortValue: (o) => o.name.toLowerCase(),
  },
  {
    key: "division",
    label: "Division",
    sortable: true,
    render: (o) => (
      <span className="font-mono text-xs text-zinc-600">{o.division ?? "\u2014"}</span>
    ),
    sortValue: (o) => o.division ?? "",
  },
  {
    key: "status",
    label: "Status",
    sortable: true,
    render: (o) => <StatusBadge status={o.status} />,
    sortValue: (o) => o.status,
  },
  {
    key: "items",
    label: "Items",
    sortable: true,
    align: "right",
    render: (o) => <span className="tabular-nums">{o.item_count}</span>,
    sortValue: (o) => o.item_count,
  },
  {
    key: "cases",
    label: "Cases",
    sortable: true,
    align: "right",
    render: (o) => <span className="tabular-nums">{o.total_cases}</span>,
    sortValue: (o) => o.total_cases,
  },
  {
    key: "invoice_total",
    label: "Invoice Total",
    sortable: true,
    align: "right",
    render: (o) => <span className="tabular-nums">{money(o.invoice_total)}</span>,
    sortValue: (o) => (o.invoice_total ? parseFloat(o.invoice_total) : null),
  },
  {
    key: "rip_rebate",
    label: "RIP Rebate",
    sortable: true,
    align: "right",
    render: (o) => (
      <span className="tabular-nums text-emerald-700">{money(o.rip_rebate_total)}</span>
    ),
    sortValue: (o) => (o.rip_rebate_total ? parseFloat(o.rip_rebate_total) : null),
  },
  {
    key: "effective",
    label: "Effective",
    sortable: true,
    align: "right",
    render: (o) => (
      <span className="tabular-nums font-medium">{money(o.effective_total)}</span>
    ),
    sortValue: (o) => (o.effective_total ? parseFloat(o.effective_total) : null),
  },
  {
    key: "updated_at",
    label: "Updated",
    sortable: true,
    render: (o) => (
      <span className="text-xs text-zinc-500">
        {new Date(o.updated_at).toLocaleDateString("en-US", {
          month: "short",
          day: "numeric",
          year: "numeric",
        })}
      </span>
    ),
    sortValue: (o) => new Date(o.updated_at).getTime(),
  },
];

export default function Orders() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [divisionFilter, setDivisionFilter] = useState<DivisionFilter>("all");
  const [showCreate, setShowCreate] = useState(false);

  // Create form state
  const [newName, setNewName] = useState("");
  const [newDivision, setNewDivision] = useState("");
  const [newNotes, setNewNotes] = useState("");

  const { sort, toggle, sorted } = useSort<OrderSummary>({ key: "updated_at", direction: "desc" });

  const ordersQ = useQuery({
    queryKey: ["orders", { status: statusFilter === "all" ? undefined : statusFilter, division: divisionFilter === "all" ? undefined : divisionFilter }],
    queryFn: () =>
      ordersApi.list({
        status: statusFilter === "all" ? undefined : statusFilter,
        division: divisionFilter === "all" ? undefined : divisionFilter,
      }),
  });

  const createMut = useMutation({
    mutationFn: (body: { name: string; division?: string; order_notes?: string }) =>
      ordersApi.create(body),
    onSuccess: (order) => {
      queryClient.invalidateQueries({ queryKey: ["orders"] });
      setShowCreate(false);
      setNewName("");
      setNewDivision("");
      setNewNotes("");
      navigate(`/orders/${order.id}`);
    },
  });

  const rows = useMemo(() => {
    const data = ordersQ.data ?? [];
    return sorted(data, columns);
  }, [ordersQ.data, sorted]);

  function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!newName.trim()) return;
    createMut.mutate({
      name: newName.trim(),
      division: newDivision || undefined,
      order_notes: newNotes.trim() || undefined,
    });
  }

  return (
    <div className="space-y-5">
      <header className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Orders</h1>
          <p className="text-sm text-zinc-600">
            Create named orders with quantities, division targeting, and payment analysis.
            Star products on the <Link to="/watchlist" className="text-zinc-900 underline hover:text-zinc-700">Tracked</Link> page, then copy them into orders here.
          </p>
        </div>
        <button
          onClick={() => setShowCreate((v) => !v)}
          className="rounded-md bg-zinc-900 px-3.5 py-1.5 text-sm font-medium text-white hover:bg-zinc-800 transition-colors"
        >
          {showCreate ? "Cancel" : "New Order"}
        </button>
      </header>

      {/* Create form (collapsible) */}
      {showCreate && (
        <form
          onSubmit={handleCreate}
          className="rounded-lg border border-zinc-200 bg-white p-4 space-y-3"
        >
          <h2 className="text-sm font-medium text-zinc-900">Create New Order</h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <label className="block text-xs text-zinc-500 mb-1">Order Name *</label>
              <input
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="e.g. Week 21 Restock"
                required
                className="w-full rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm placeholder:text-zinc-400 focus:border-zinc-900 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 mb-1">Division</label>
              <select
                value={newDivision}
                onChange={(e) => setNewDivision(e.target.value)}
                className="w-full rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm"
              >
                <option value="">None</option>
                {DIVISIONS.filter((d) => d !== "all").map((d) => (
                  <option key={d} value={d}>{d}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs text-zinc-500 mb-1">Notes</label>
              <input
                type="text"
                value={newNotes}
                onChange={(e) => setNewNotes(e.target.value)}
                placeholder="Optional notes..."
                className="w-full rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm placeholder:text-zinc-400 focus:border-zinc-900 focus:outline-none"
              />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="submit"
              disabled={createMut.isPending || !newName.trim()}
              className="rounded-md bg-zinc-900 px-3.5 py-1.5 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-50 transition-colors"
            >
              {createMut.isPending ? "Creating..." : "Create Order"}
            </button>
            {createMut.isError && (
              <span className="text-sm text-red-600">{(createMut.error as Error).message}</span>
            )}
          </div>
        </form>
      )}

      {/* Filters */}
      <div className="space-y-3">
        {/* Status pills */}
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-zinc-500 mr-1">Status</span>
          {STATUSES.map((s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={`rounded-md px-2.5 py-1 text-xs font-medium capitalize transition-colors ${
                statusFilter === s
                  ? "bg-zinc-900 text-white"
                  : "bg-zinc-100 text-zinc-600 hover:bg-zinc-200"
              }`}
            >
              {s}
            </button>
          ))}
        </div>

        {/* Division pills */}
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-zinc-500 mr-1">Division</span>
          {DIVISIONS.map((d) => (
            <button
              key={d}
              onClick={() => setDivisionFilter(d)}
              className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                divisionFilter === d
                  ? "bg-zinc-900 text-white"
                  : "bg-zinc-100 text-zinc-600 hover:bg-zinc-200"
              }`}
            >
              {d === "all" ? "All" : d}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="rounded-lg border border-zinc-200 bg-white overflow-hidden">
        {ordersQ.isLoading ? (
          <div className="text-center py-12 text-zinc-500">Loading orders...</div>
        ) : ordersQ.isError ? (
          <div className="text-center py-12 text-red-600">
            Failed to load orders: {(ordersQ.error as Error).message}
          </div>
        ) : rows.length === 0 ? (
            <div className="py-16 text-center space-y-4">
              <div className="text-zinc-400 text-4xl">📋</div>
              <div className="space-y-1">
                <p className="text-zinc-700 font-medium">No orders yet</p>
                <p className="text-sm text-zinc-500 max-w-md mx-auto">
                  Create a new order to start building your next purchase.
                  You can add products from the Catalog or copy items from your Tracked list.
                </p>
              </div>
              <button
                onClick={() => setShowCreate(true)}
                className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 transition-colors"
              >
                Create Your First Order
              </button>
            </div>
        ) : (
          <SortableTable
            columns={columns}
            data={rows}
            sort={sort}
            onSort={toggle}
            rowKey={(o) => o.id}
            emptyMessage="No orders match your filters."
            onRowClick={(o) => navigate(`/orders/${o.id}`)}
          />
        )}
      </div>
    </div>
  );
}
