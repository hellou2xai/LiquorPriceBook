import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { salesRepsApi, type SalesRepOut } from "../lib/api";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DIVISIONS = ["L", "S", "D", "GS", "FB", "JD", "IV"] as const;
type Division = (typeof DIVISIONS)[number];

// ---------------------------------------------------------------------------
// Icons (inline SVG — no extra deps)
// ---------------------------------------------------------------------------

function MailIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 20 20"
      fill="currentColor"
      className={className ?? "h-4 w-4"}
    >
      <path d="M3 4a2 2 0 0 0-2 2v.217l9 5.25 9-5.25V6a2 2 0 0 0-2-2H3Z" />
      <path d="m1 8.268 8.438 4.922a1.25 1.25 0 0 0 1.124 0L19 8.268V14a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8.268Z" />
    </svg>
  );
}

function PhoneIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 20 20"
      fill="currentColor"
      className={className ?? "h-4 w-4"}
    >
      <path
        fillRule="evenodd"
        d="M2 3.5A1.5 1.5 0 0 1 3.5 2h1.148a1.5 1.5 0 0 1 1.465 1.175l.716 3.223a1.5 1.5 0 0 1-1.052 1.767l-.933.267c-.41.117-.643.555-.48.95a11.542 11.542 0 0 0 6.254 6.254c.395.163.833-.07.95-.48l.267-.933a1.5 1.5 0 0 1 1.767-1.052l3.223.716A1.5 1.5 0 0 1 18 16.352V17.5a1.5 1.5 0 0 1-1.5 1.5H15c-1.149 0-2.263-.15-3.326-.43A13.022 13.022 0 0 1 2.43 8.326 13.019 13.019 0 0 1 2 5V3.5Z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function UserGroupIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="currentColor"
      className={className ?? "h-12 w-12"}
    >
      <path d="M4.5 6.375a4.125 4.125 0 1 1 8.25 0 4.125 4.125 0 0 1-8.25 0ZM14.25 8.625a3.375 3.375 0 1 1 6.75 0 3.375 3.375 0 0 1-6.75 0ZM1.5 19.125a7.125 7.125 0 0 1 14.25 0v.003l-.001.119a.75.75 0 0 1-.363.63 13.067 13.067 0 0 1-6.761 1.873c-2.472 0-4.786-.684-6.76-1.873a.75.75 0 0 1-.364-.63l-.001-.122ZM17.25 19.128l-.001.144a2.25 2.25 0 0 1-.233.96 10.088 10.088 0 0 0 5.06-1.01.75.75 0 0 0 .42-.643 4.875 4.875 0 0 0-6.957-4.611 8.586 8.586 0 0 1 1.71 5.157v.003Z" />
    </svg>
  );
}

function PencilIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 20 20"
      fill="currentColor"
      className={className ?? "h-3.5 w-3.5"}
    >
      <path d="m5.433 13.917 1.262-3.155A4 4 0 0 1 7.58 9.42l6.92-6.918a2.121 2.121 0 0 1 3 3l-6.92 6.918c-.383.383-.84.685-1.343.886l-3.154 1.262a.5.5 0 0 1-.65-.65Z" />
      <path d="M3.5 5.75c0-.69.56-1.25 1.25-1.25H10A.75.75 0 0 0 10 3H4.75A2.75 2.75 0 0 0 2 5.75v9.5A2.75 2.75 0 0 0 4.75 18h9.5A2.75 2.75 0 0 0 17 15.25V10a.75.75 0 0 0-1.5 0v5.25c0 .69-.56 1.25-1.25 1.25h-9.5c-.69 0-1.25-.56-1.25-1.25v-9.5Z" />
    </svg>
  );
}

function TrashIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 20 20"
      fill="currentColor"
      className={className ?? "h-3.5 w-3.5"}
    >
      <path
        fillRule="evenodd"
        d="M8.75 1A2.75 2.75 0 0 0 6 3.75v.443c-.795.077-1.584.176-2.365.298a.75.75 0 1 0 .23 1.482l.149-.022.841 10.518A2.75 2.75 0 0 0 7.596 19h4.807a2.75 2.75 0 0 0 2.742-2.53l.841-10.52.149.023a.75.75 0 0 0 .23-1.482A41.03 41.03 0 0 0 14 4.193V3.75A2.75 2.75 0 0 0 11.25 1h-2.5ZM10 4c.84 0 1.673.025 2.5.075V3.75c0-.69-.56-1.25-1.25-1.25h-2.5c-.69 0-1.25.56-1.25 1.25v.325C8.327 4.025 9.16 4 10 4ZM8.58 7.72a.75.75 0 0 0-1.5.06l.3 7.5a.75.75 0 1 0 1.5-.06l-.3-7.5Zm4.34.06a.75.75 0 1 0-1.5-.06l-.3 7.5a.75.75 0 1 0 1.5.06l.3-7.5Z"
        clipRule="evenodd"
      />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const inputCls =
  "w-full rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-800 placeholder:text-zinc-400 focus:border-brand-orange focus:ring-1 focus:ring-brand-orange/30 focus:outline-none transition-colors";

const labelCls = "block text-sm font-medium text-brand-navy mb-1";

function DivisionBadge({ division }: { division: string | null }) {
  if (!division) {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-brand-navy/10 text-brand-navy">
        All Divisions
      </span>
    );
  }
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-brand-orange/10 text-brand-orange">
      {division}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Form state type
// ---------------------------------------------------------------------------

type RepFormState = {
  name: string;
  email: string;
  phone: string;
  division: string;
  notes: string;
};

const emptyForm = (): RepFormState => ({
  name: "",
  email: "",
  phone: "",
  division: "",
  notes: "",
});

function formFromRep(rep: SalesRepOut): RepFormState {
  return {
    name: rep.name,
    email: rep.email,
    phone: rep.phone ?? "",
    division: rep.division ?? "",
    notes: rep.notes ?? "",
  };
}

// ---------------------------------------------------------------------------
// Add / Edit Modal
// ---------------------------------------------------------------------------

interface RepModalProps {
  initial?: SalesRepOut | null;
  onClose: () => void;
  onSave: (form: RepFormState) => void;
  isPending: boolean;
  error: string | null;
}

function RepModal({ initial, onClose, onSave, isPending, error }: RepModalProps) {
  const [form, setForm] = useState<RepFormState>(
    initial ? formFromRep(initial) : emptyForm(),
  );

  function set(key: keyof RepFormState, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.name.trim() || !form.email.trim()) return;
    onSave(form);
  }

  const isEdit = Boolean(initial);

  return (
    // Backdrop
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm px-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      {/* Modal card */}
      <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full mx-4 p-6 space-y-5">
        {/* Header */}
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold text-brand-navy">
            {isEdit ? "Edit Sales Rep" : "Add Sales Rep"}
          </h2>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-zinc-400 hover:text-zinc-600 hover:bg-zinc-100 transition-colors"
            aria-label="Close"
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="h-5 w-5">
              <path d="M6.28 5.22a.75.75 0 0 0-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 1 0 1.06 1.06L10 11.06l3.72 3.72a.75.75 0 1 0 1.06-1.06L11.06 10l3.72-3.72a.75.75 0 0 0-1.06-1.06L10 8.94 6.28 5.22Z" />
            </svg>
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Name */}
          <div>
            <label className={labelCls}>
              Name <span className="text-brand-rose">*</span>
            </label>
            <input
              type="text"
              value={form.name}
              onChange={(e) => set("name", e.target.value)}
              placeholder="Jane Smith"
              required
              className={inputCls}
            />
          </div>

          {/* Email */}
          <div>
            <label className={labelCls}>
              Email <span className="text-brand-rose">*</span>
            </label>
            <input
              type="email"
              value={form.email}
              onChange={(e) => set("email", e.target.value)}
              placeholder="jane@distributor.com"
              required
              className={inputCls}
            />
          </div>

          {/* Phone */}
          <div>
            <label className={labelCls}>Phone</label>
            <input
              type="tel"
              value={form.phone}
              onChange={(e) => set("phone", e.target.value)}
              placeholder="(555) 123-4567"
              className={inputCls}
            />
          </div>

          {/* Division */}
          <div>
            <label className={labelCls}>Division</label>
            <select
              value={form.division}
              onChange={(e) => set("division", e.target.value)}
              className={inputCls}
            >
              <option value="">All divisions</option>
              {DIVISIONS.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </div>

          {/* Notes */}
          <div>
            <label className={labelCls}>Notes</label>
            <textarea
              value={form.notes}
              onChange={(e) => set("notes", e.target.value)}
              placeholder="Any relevant notes..."
              rows={3}
              className={`${inputCls} resize-none`}
            />
          </div>

          {/* Error */}
          {error && (
            <p className="text-sm text-brand-rose bg-brand-rose/5 border border-brand-rose/20 rounded-lg px-3 py-2">
              {error}
            </p>
          )}

          {/* Actions */}
          <div className="flex items-center gap-2 pt-1">
            <button
              type="submit"
              disabled={isPending || !form.name.trim() || !form.email.trim()}
              className="flex-1 rounded-lg bg-brand-orange px-4 py-2 text-sm font-medium text-white hover:bg-brand-orange-dark disabled:opacity-50 transition-colors"
            >
              {isPending ? (isEdit ? "Saving..." : "Adding...") : isEdit ? "Save Changes" : "Add Rep"}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="flex-1 rounded-lg bg-brand-tan px-4 py-2 text-sm font-medium text-brand-navy hover:bg-zinc-200 transition-colors"
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Delete Confirmation Modal
// ---------------------------------------------------------------------------

interface DeleteModalProps {
  rep: SalesRepOut;
  onClose: () => void;
  onConfirm: () => void;
  isPending: boolean;
}

function DeleteModal({ rep, onClose, onConfirm, isPending }: DeleteModalProps) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm px-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="bg-white rounded-2xl shadow-2xl max-w-sm w-full mx-4 p-6 space-y-4">
        <div className="flex items-start gap-3">
          <div className="flex-shrink-0 flex items-center justify-center h-10 w-10 rounded-full bg-brand-rose/10">
            <TrashIcon className="h-5 w-5 text-brand-rose" />
          </div>
          <div className="space-y-1">
            <h2 className="text-base font-semibold text-brand-navy">Remove Sales Rep</h2>
            <p className="text-sm text-zinc-600">
              Are you sure you want to remove{" "}
              <span className="font-medium text-zinc-800">{rep.name}</span>? This action cannot be
              undone.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 pt-1">
          <button
            onClick={onConfirm}
            disabled={isPending}
            className="flex-1 rounded-lg bg-brand-rose px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50 transition-opacity"
          >
            {isPending ? "Removing..." : "Remove"}
          </button>
          <button
            onClick={onClose}
            className="flex-1 rounded-lg bg-brand-tan px-4 py-2 text-sm font-medium text-brand-navy hover:bg-zinc-200 transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Rep Card
// ---------------------------------------------------------------------------

interface RepCardProps {
  rep: SalesRepOut;
  onEdit: (rep: SalesRepOut) => void;
  onDelete: (rep: SalesRepOut) => void;
}

function RepCard({ rep, onEdit, onDelete }: RepCardProps) {
  return (
    <div className="rounded-xl border border-zinc-200/80 bg-white shadow-sm p-5 hover:shadow-md transition-shadow flex flex-col gap-3">
      {/* Top row: name + division badge */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-lg font-semibold text-brand-navy truncate">{rep.name}</h3>
        </div>
        <div className="flex-shrink-0">
          <DivisionBadge division={rep.division} />
        </div>
      </div>

      {/* Contact details */}
      <div className="space-y-1.5">
        {/* Email */}
        <div className="flex items-center gap-2 text-sm">
          <MailIcon className="h-3.5 w-3.5 text-zinc-400 flex-shrink-0" />
          <a
            href={`mailto:${rep.email}`}
            className="text-brand-orange hover:underline truncate"
            title={rep.email}
          >
            {rep.email}
          </a>
        </div>

        {/* Phone (conditional) */}
        {rep.phone && (
          <div className="flex items-center gap-2 text-sm">
            <PhoneIcon className="h-3.5 w-3.5 text-zinc-400 flex-shrink-0" />
            <a
              href={`tel:${rep.phone}`}
              className="text-zinc-600 hover:text-zinc-800 hover:underline"
            >
              {rep.phone}
            </a>
          </div>
        )}
      </div>

      {/* Notes (conditional) */}
      {rep.notes && (
        <p className="text-xs italic text-zinc-500 border-t border-zinc-100 pt-2 line-clamp-2">
          {rep.notes}
        </p>
      )}

      {/* Footer: actions */}
      <div className="flex items-center justify-between pt-1 border-t border-zinc-100 mt-auto">
        <span className="text-[11px] text-zinc-400">
          Added{" "}
          {new Date(rep.created_at).toLocaleDateString("en-US", {
            month: "short",
            day: "numeric",
            year: "numeric",
          })}
        </span>
        <div className="flex items-center gap-3">
          <button
            onClick={() => onEdit(rep)}
            className="flex items-center gap-1 text-xs font-medium text-brand-navy hover:underline transition-colors"
          >
            <PencilIcon className="h-3 w-3" />
            Edit
          </button>
          <button
            onClick={() => onDelete(rep)}
            className="flex items-center gap-1 text-xs font-medium text-zinc-400 hover:text-brand-rose transition-colors"
          >
            <TrashIcon className="h-3 w-3" />
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Empty State
// ---------------------------------------------------------------------------

function EmptyState({
  filtered,
  onAdd,
}: {
  filtered: boolean;
  onAdd: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-20 px-4 text-center">
      <div className="rounded-full bg-brand-tan p-5 mb-4">
        <UserGroupIcon className="h-10 w-10 text-brand-navy/30" />
      </div>
      <h3 className="text-base font-semibold text-brand-navy mb-1">
        {filtered ? "No reps in this division" : "No sales reps yet"}
      </h3>
      <p className="text-sm text-zinc-500 max-w-xs mb-5">
        {filtered
          ? "Try selecting a different division filter, or add a new rep for this division."
          : "Add your distributor sales reps here so you can email orders directly to them from the Orders page."}
      </p>
      {!filtered && (
        <button
          onClick={onAdd}
          className="rounded-lg bg-brand-orange px-4 py-2 text-sm font-medium text-white hover:bg-brand-orange-dark transition-colors"
        >
          Add Your First Rep
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function SalesReps() {
  const qc = useQueryClient();

  // Division filter state (URL-independent)
  const [divFilter, setDivFilter] = useState<Division | "All">("All");

  // Modal state
  const [showAddModal, setShowAddModal] = useState(false);
  const [editRep, setEditRep] = useState<SalesRepOut | null>(null);
  const [deleteRep, setDeleteRep] = useState<SalesRepOut | null>(null);

  // Query
  const repsQ = useQuery({
    queryKey: ["sales-reps", divFilter === "All" ? undefined : divFilter],
    queryFn: () =>
      salesRepsApi.list(divFilter === "All" ? undefined : divFilter),
  });

  // Mutations
  const createMut = useMutation({
    mutationFn: (form: RepFormState) =>
      salesRepsApi.create({
        name: form.name.trim(),
        email: form.email.trim(),
        phone: form.phone.trim() || undefined,
        division: form.division || undefined,
        notes: form.notes.trim() || undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sales-reps"] });
      setShowAddModal(false);
    },
  });

  const updateMut = useMutation({
    mutationFn: ({ id, form }: { id: string; form: RepFormState }) =>
      salesRepsApi.update(id, {
        name: form.name.trim(),
        email: form.email.trim(),
        phone: form.phone.trim() || undefined,
        division: form.division || undefined,
        notes: form.notes.trim() || undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sales-reps"] });
      setEditRep(null);
    },
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => salesRepsApi.remove(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sales-reps"] });
      setDeleteRep(null);
    },
  });

  const reps = repsQ.data ?? [];
  const isFiltered = divFilter !== "All";

  return (
    <>
      {/* ----------------------------------------------------------------- */}
      {/* Page                                                               */}
      {/* ----------------------------------------------------------------- */}
      <div className="space-y-5 sm:space-y-6">

        {/* Header */}
        <header className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
          <div className="space-y-1">
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-brand-navy">
              Sales Representatives
            </h1>
            <p className="text-sm text-zinc-500">
              Manage your distributor sales reps by division.
            </p>
          </div>
          <button
            onClick={() => setShowAddModal(true)}
            className="self-start rounded-lg bg-brand-orange px-4 py-2 text-sm font-medium text-white hover:bg-brand-orange-dark transition-colors whitespace-nowrap"
          >
            + Add Sales Rep
          </button>
        </header>

        {/* Division filter pills */}
        <div className="flex items-center gap-1.5 flex-wrap">
          {(["All", ...DIVISIONS] as const).map((d) => (
            <button
              key={d}
              onClick={() => setDivFilter(d)}
              className={`rounded-full px-3 py-1 text-xs font-medium border transition-colors ${
                divFilter === d
                  ? "bg-brand-navy text-white border-brand-navy"
                  : "bg-white border-zinc-200 text-zinc-600 hover:bg-brand-tan"
              }`}
            >
              {d}
            </button>
          ))}
        </div>

        {/* Body */}
        {repsQ.isLoading ? (
          // Loading skeleton
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {Array.from({ length: 3 }).map((_, i) => (
              <div
                key={i}
                className="rounded-xl border border-zinc-200/80 bg-white shadow-sm p-5 space-y-3 animate-pulse"
              >
                <div className="flex justify-between">
                  <div className="h-5 w-36 bg-zinc-100 rounded" />
                  <div className="h-5 w-12 bg-zinc-100 rounded-full" />
                </div>
                <div className="space-y-2">
                  <div className="h-4 w-48 bg-zinc-100 rounded" />
                  <div className="h-4 w-32 bg-zinc-100 rounded" />
                </div>
                <div className="h-px bg-zinc-100" />
                <div className="flex justify-between">
                  <div className="h-3.5 w-24 bg-zinc-100 rounded" />
                  <div className="h-3.5 w-20 bg-zinc-100 rounded" />
                </div>
              </div>
            ))}
          </div>
        ) : repsQ.isError ? (
          <div className="rounded-xl border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-700">
            Failed to load sales reps:{" "}
            {repsQ.error instanceof Error ? repsQ.error.message : "Unknown error"}
          </div>
        ) : reps.length === 0 ? (
          <EmptyState filtered={isFiltered} onAdd={() => setShowAddModal(true)} />
        ) : (
          <>
            {/* Count summary */}
            <p className="text-xs text-zinc-400">
              {reps.length} {reps.length === 1 ? "rep" : "reps"}
              {isFiltered ? ` in division ${divFilter}` : " total"}
            </p>

            {/* Cards grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {reps.map((rep) => (
                <RepCard
                  key={rep.id}
                  rep={rep}
                  onEdit={(r) => setEditRep(r)}
                  onDelete={(r) => setDeleteRep(r)}
                />
              ))}
            </div>
          </>
        )}
      </div>

      {/* ----------------------------------------------------------------- */}
      {/* Add Modal                                                          */}
      {/* ----------------------------------------------------------------- */}
      {showAddModal && (
        <RepModal
          initial={null}
          onClose={() => {
            setShowAddModal(false);
            createMut.reset();
          }}
          onSave={(form) => createMut.mutate(form)}
          isPending={createMut.isPending}
          error={
            createMut.isError
              ? createMut.error instanceof Error
                ? createMut.error.message
                : "Failed to add rep"
              : null
          }
        />
      )}

      {/* ----------------------------------------------------------------- */}
      {/* Edit Modal                                                         */}
      {/* ----------------------------------------------------------------- */}
      {editRep && (
        <RepModal
          initial={editRep}
          onClose={() => {
            setEditRep(null);
            updateMut.reset();
          }}
          onSave={(form) => updateMut.mutate({ id: editRep.id, form })}
          isPending={updateMut.isPending}
          error={
            updateMut.isError
              ? updateMut.error instanceof Error
                ? updateMut.error.message
                : "Failed to save changes"
              : null
          }
        />
      )}

      {/* ----------------------------------------------------------------- */}
      {/* Delete Confirmation Modal                                          */}
      {/* ----------------------------------------------------------------- */}
      {deleteRep && (
        <DeleteModal
          rep={deleteRep}
          onClose={() => {
            setDeleteRep(null);
            deleteMut.reset();
          }}
          onConfirm={() => deleteMut.mutate(deleteRep.id)}
          isPending={deleteMut.isPending}
        />
      )}
    </>
  );
}
