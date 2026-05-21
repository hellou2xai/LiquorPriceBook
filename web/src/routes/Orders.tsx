import { useState, useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ordersApi } from "../lib/api";
import type { OrderSummary } from "../lib/api";
import { money } from "../lib/fmt";
import SortableTable, { useSort, Column } from "../components/SortableTable";
import RowLimitSelect, { useRowLimit } from "../components/RowLimitSelect";

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

export default function Orders() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [divisionFilter, setDivisionFilter] = useState<DivisionFilter>("all");
  const [showCreate, setShowCreate] = useState(false);
  const [showHidden, setShowHidden] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  // Create form state
  const [newName, setNewName] = useState("");
  const [newDivision, setNewDivision] = useState("");
  const [newNotes, setNewNotes] = useState("");

  const { sort, toggle, sorted } = useSort<OrderSummary>({ key: "updated_at", direction: "desc" });
  const { limit: rowLimit, setLimit: setRowLimit } = useRowLimit(100);

  const ordersQ = useQuery({
    queryKey: ["orders", { status: statusFilter === "all" ? undefined : statusFilter, division: divisionFilter === "all" ? undefined : divisionFilter, include_hidden: showHidden || undefined }],
    queryFn: () =>
      ordersApi.list({
        status: statusFilter === "all" ? undefined : statusFilter,
        division: divisionFilter === "all" ? undefined : divisionFilter,
        include_hidden: showHidden || undefined,
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

  const hideMut = useMutation({
    mutationFn: (id: string) => ordersApi.hide(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["orders"] }),
  });

  const unhideMut = useMutation({
    mutationFn: (id: string) => ordersApi.unhide(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["orders"] }),
  });

  const cloneMut = useMutation({
    mutationFn: (id: string) => ordersApi.clone(id),
    onSuccess: (order) => {
      queryClient.invalidateQueries({ queryKey: ["orders"] });
      navigate(`/orders/${order.id}`);
    },
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => ordersApi.remove(id),
    onSuccess: () => {
      setConfirmDelete(null);
      queryClient.invalidateQueries({ queryKey: ["orders"] });
    },
  });

  const columns: Column<OrderSummary>[] = useMemo(() => [
    {
      key: "name",
      label: "Name",
      sortable: true,
      render: (o: OrderSummary) => (
        <div className="flex items-center gap-2">
          <Link to={`/orders/${o.id}`} className="font-medium text-zinc-900 hover:underline" onClick={(e) => e.stopPropagation()}>
            {o.name}
          </Link>
          {o.hidden_at && (
            <span className="inline-flex items-center rounded-full bg-brand-navy/5 border border-brand-navy/10 px-1.5 py-0.5 text-[10px] text-brand-navy">hidden</span>
          )}
        </div>
      ),
      sortValue: (o: OrderSummary) => o.name.toLowerCase(),
    },
    {
      key: "division",
      label: "Div",
      sortable: true,
      hideBelow: "sm" as const,
      render: (o: OrderSummary) => (
        <span className="font-mono text-xs text-zinc-600">{o.division ?? "\u2014"}</span>
      ),
      sortValue: (o: OrderSummary) => o.division ?? "",
    },
    {
      key: "status",
      label: "Status",
      sortable: true,
      render: (o: OrderSummary) => <StatusBadge status={o.status} />,
      sortValue: (o: OrderSummary) => o.status,
    },
    {
      key: "items",
      label: "Items",
      sortable: true,
      align: "right" as const,
      hideBelow: "sm" as const,
      render: (o: OrderSummary) => <span className="tabular-nums">{o.item_count}</span>,
      sortValue: (o: OrderSummary) => o.item_count,
    },
    {
      key: "cases",
      label: "Cases",
      sortable: true,
      align: "right" as const,
      hideBelow: "sm" as const,
      render: (o: OrderSummary) => <span className="tabular-nums">{o.total_cases}</span>,
      sortValue: (o: OrderSummary) => o.total_cases,
    },
    {
      key: "invoice_total",
      label: "Invoice",
      sortable: true,
      align: "right" as const,
      hideBelow: "md" as const,
      render: (o: OrderSummary) => <span className="tabular-nums">{money(o.invoice_total)}</span>,
      sortValue: (o: OrderSummary) => (o.invoice_total ? parseFloat(o.invoice_total) : null),
    },
    {
      key: "rip_rebate",
      label: "RIP Rebate",
      sortable: true,
      align: "right" as const,
      hideBelow: "md" as const,
      render: (o: OrderSummary) => (
        <span className="tabular-nums text-emerald-700">{money(o.rip_rebate_total)}</span>
      ),
      sortValue: (o: OrderSummary) => (o.rip_rebate_total ? parseFloat(o.rip_rebate_total) : null),
    },
    {
      key: "effective",
      label: "Effective",
      sortable: true,
      align: "right" as const,
      render: (o: OrderSummary) => (
        <span className="tabular-nums font-medium">{money(o.effective_total)}</span>
      ),
      sortValue: (o: OrderSummary) => (o.effective_total ? parseFloat(o.effective_total) : null),
    },
    {
      key: "updated_at",
      label: "Updated",
      sortable: true,
      hideBelow: "lg" as const,
      render: (o: OrderSummary) => (
        <span className="text-xs text-zinc-500">
          {new Date(o.updated_at).toLocaleDateString("en-US", {
            month: "short",
            day: "numeric",
            year: "numeric",
          })}
        </span>
      ),
      sortValue: (o: OrderSummary) => new Date(o.updated_at).getTime(),
    },
    {
      key: "actions",
      label: "",
      render: (o: OrderSummary) => (
        <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
          {o.hidden_at ? (
            <button
              onClick={() => unhideMut.mutate(o.id)}
              disabled={unhideMut.isPending}
              className="rounded border border-zinc-300 bg-brand-tan text-brand-navy px-2 py-0.5 text-[10px] hover:bg-zinc-200 disabled:opacity-50"
              title="Unhide this order"
            >
              Unhide
            </button>
          ) : (
            <button
              onClick={() => hideMut.mutate(o.id)}
              disabled={hideMut.isPending}
              className="rounded border border-zinc-300 bg-brand-tan text-brand-navy px-2 py-0.5 text-[10px] hover:bg-zinc-200 disabled:opacity-50"
              title="Hide this order from the list"
            >
              Hide
            </button>
          )}
          <button
            onClick={() => cloneMut.mutate(o.id)}
            disabled={cloneMut.isPending}
            className="rounded border border-zinc-300 bg-brand-tan text-brand-navy px-2 py-0.5 text-[10px] hover:bg-zinc-200 disabled:opacity-50"
            title="Clone this order"
          >
            Clone
          </button>
          {confirmDelete === o.id ? (
            <span className="flex items-center gap-1">
              <button
                onClick={() => deleteMut.mutate(o.id)}
                disabled={deleteMut.isPending}
                className="rounded bg-red-600 px-2 py-0.5 text-[10px] text-white hover:bg-red-700 disabled:opacity-50"
              >
                {deleteMut.isPending ? "..." : "Confirm"}
              </button>
              <button
                onClick={() => setConfirmDelete(null)}
                className="rounded border border-zinc-300 bg-brand-tan text-brand-navy px-2 py-0.5 text-[10px] hover:bg-zinc-200"
              >
                Cancel
              </button>
            </span>
          ) : (
            <button
              onClick={() => setConfirmDelete(o.id)}
              className="rounded border border-red-200 bg-white px-2 py-0.5 text-[10px] text-red-600 hover:bg-red-50"
              title="Permanently delete this order"
            >
              Delete
            </button>
          )}
        </div>
      ),
    },
  ], [confirmDelete, hideMut, unhideMut, cloneMut, deleteMut]);

  const allRows = useMemo(() => {
    const data = ordersQ.data ?? [];
    return sorted(data, columns);
  }, [ordersQ.data, sorted, columns]);
  const rows = useMemo(() => allRows.slice(0, rowLimit), [allRows, rowLimit]);

  const hiddenCount = useMemo(() => {
    if (!showHidden || !ordersQ.data) return 0;
    return ordersQ.data.filter((o) => o.hidden_at).length;
  }, [ordersQ.data, showHidden]);

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
    <div className="space-y-4 sm:space-y-5">
      <header className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-xl sm:text-2xl font-semibold tracking-tight text-brand-navy">Orders</h1>
          <p className="text-sm text-zinc-600">
            Create named orders with quantities, division targeting, and payment analysis.
            Star products on the <Link to="/watchlist" className="text-brand-orange underline hover:text-brand-orange-dark">Tracked</Link> page, then copy them into orders here.
          </p>
        </div>
        <button
          onClick={() => setShowCreate((v) => !v)}
          className="rounded-md bg-brand-orange px-3.5 py-1.5 text-sm font-medium text-white hover:bg-brand-orange-dark transition-colors self-start whitespace-nowrap"
        >
          {showCreate ? "Cancel" : "New Order"}
        </button>
      </header>

      {/* Create form (collapsible) */}
      {showCreate && (
        <form
          onSubmit={handleCreate}
          className="rounded-xl shadow-sm border border-zinc-200 bg-white p-4 space-y-3"
        >
          <h2 className="text-sm font-medium text-brand-navy">Create New Order</h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <label className="block text-xs text-zinc-500 mb-1">Order Name *</label>
              <input
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="e.g. Week 21 Restock"
                required
                className="w-full rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm placeholder:text-zinc-400 focus:border-brand-orange focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 mb-1">Division</label>
              <select
                value={newDivision}
                onChange={(e) => setNewDivision(e.target.value)}
                className="w-full rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm focus:border-brand-orange focus:outline-none"
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
                className="w-full rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm placeholder:text-zinc-400 focus:border-brand-orange focus:outline-none"
              />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="submit"
              disabled={createMut.isPending || !newName.trim()}
              className="rounded-md bg-brand-orange px-3.5 py-1.5 text-sm font-medium text-white hover:bg-brand-orange-dark disabled:opacity-50 transition-colors"
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
      <div className="space-y-2 sm:space-y-3">
        {/* Status pills */}
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-xs text-zinc-500 mr-1">Status</span>
          {STATUSES.map((s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={`rounded-md px-2.5 py-1 text-xs font-medium capitalize transition-colors ${
                statusFilter === s
                  ? "bg-brand-navy text-white"
                  : "text-zinc-600 hover:bg-brand-tan"
              }`}
            >
              {s}
            </button>
          ))}
        </div>

        {/* Division pills */}
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-xs text-zinc-500 mr-1">Division</span>
          {DIVISIONS.map((d) => (
            <button
              key={d}
              onClick={() => setDivisionFilter(d)}
              className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                divisionFilter === d
                  ? "bg-brand-navy text-white"
                  : "text-zinc-600 hover:bg-brand-tan"
              }`}
            >
              {d === "all" ? "All" : d}
            </button>
          ))}
        </div>

        {/* Show hidden toggle */}
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1.5 text-sm text-zinc-600 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={showHidden}
              onChange={(e) => setShowHidden(e.target.checked)}
              className="rounded border-zinc-300 h-3.5 w-3.5 text-brand-orange focus:ring-brand-orange"
            />
            Show hidden orders
          </label>
          {showHidden && hiddenCount > 0 && (
            <span className="text-xs text-zinc-400">({hiddenCount} hidden)</span>
          )}
        </div>
      </div>

      {/* Table */}
      <div className="rounded-xl shadow-sm border border-zinc-200 bg-white overflow-hidden">
        {ordersQ.isLoading ? (
          <div className="text-center py-12 text-zinc-500">Loading orders...</div>
        ) : ordersQ.isError ? (
          <div className="text-center py-12 text-red-600">
            Failed to load orders: {(ordersQ.error as Error).message}
          </div>
        ) : rows.length === 0 ? (
            <div className="py-12 sm:py-16 text-center space-y-4 px-4">
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
                className="rounded-md bg-brand-orange px-4 py-2 text-sm font-medium text-white hover:bg-brand-orange-dark transition-colors"
              >
                Create Your First Order
              </button>
            </div>
        ) : (
          <>
            <SortableTable
              columns={columns}
              data={rows}
              sort={sort}
              onSort={toggle}
              rowKey={(o) => o.id}
              emptyMessage="No orders match your filters."
              onRowClick={(o) => navigate(`/orders/${o.id}`)}
            />
            <RowLimitSelect total={allRows.length} limit={rowLimit} onChange={setRowLimit} />
          </>
        )}
      </div>
    </div>
  );
}
