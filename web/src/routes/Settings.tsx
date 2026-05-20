import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "../lib/auth";
import { salesRepsApi, type SalesRepOut } from "../lib/api";

const DIVISIONS = ["L", "S", "D", "GS", "FB", "JD", "IV"] as const;

function RepRow({
  rep,
  onDelete,
}: {
  rep: SalesRepOut;
  onDelete: (id: string) => void;
}) {
  const [confirm, setConfirm] = useState(false);
  return (
    <tr className="border-b border-zinc-100 last:border-0">
      <td className="px-3 py-2 text-sm">{rep.name}</td>
      <td className="px-3 py-2 text-sm text-zinc-600">{rep.email}</td>
      <td className="px-3 py-2 text-sm text-zinc-500 hidden sm:table-cell">{rep.phone || "—"}</td>
      <td className="px-3 py-2 text-sm hidden sm:table-cell">
        {rep.division ? (
          <span className="inline-flex px-1.5 py-0.5 rounded text-xs font-medium bg-zinc-100">
            {rep.division}
          </span>
        ) : (
          <span className="text-zinc-400">All</span>
        )}
      </td>
      <td className="px-3 py-2 text-right">
        {confirm ? (
          <span className="space-x-2">
            <button
              onClick={() => onDelete(rep.id)}
              className="text-xs text-red-600 font-medium hover:underline"
            >
              Confirm
            </button>
            <button
              onClick={() => setConfirm(false)}
              className="text-xs text-zinc-500 hover:underline"
            >
              Cancel
            </button>
          </span>
        ) : (
          <button
            onClick={() => setConfirm(true)}
            className="text-xs text-zinc-500 hover:text-red-600"
          >
            Delete
          </button>
        )}
      </td>
    </tr>
  );
}

function AddRepForm({ onAdded }: { onAdded: () => void }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [division, setDivision] = useState("");

  const addMut = useMutation({
    mutationFn: () =>
      salesRepsApi.create({
        name: name.trim(),
        email: email.trim(),
        phone: phone.trim() || undefined,
        division: division || undefined,
      }),
    onSuccess: () => {
      setName("");
      setEmail("");
      setPhone("");
      setDivision("");
      onAdded();
    },
  });

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (name.trim() && email.trim()) addMut.mutate();
      }}
      className="flex flex-col sm:flex-row flex-wrap gap-2 items-start sm:items-end"
    >
      <div>
        <label className="block text-xs text-zinc-500 mb-1">Name *</label>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          placeholder="John Smith"
          className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm w-44"
        />
      </div>
      <div>
        <label className="block text-xs text-zinc-500 mb-1">Email *</label>
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          placeholder="john@distributor.com"
          className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm w-52"
        />
      </div>
      <div>
        <label className="block text-xs text-zinc-500 mb-1">Phone</label>
        <input
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          placeholder="(555) 123-4567"
          className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm w-36"
        />
      </div>
      <div>
        <label className="block text-xs text-zinc-500 mb-1">Division</label>
        <select
          value={division}
          onChange={(e) => setDivision(e.target.value)}
          className="rounded-md border border-zinc-300 px-2 py-1.5 text-sm"
        >
          <option value="">All divisions</option>
          {DIVISIONS.map((d) => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>
      </div>
      <button
        type="submit"
        disabled={addMut.isPending || !name.trim() || !email.trim()}
        className="rounded-md bg-zinc-900 px-4 py-1.5 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-50"
      >
        {addMut.isPending ? "Adding..." : "Add Rep"}
      </button>
      {addMut.isError && (
        <span className="text-xs text-red-500">
          {addMut.error instanceof Error ? addMut.error.message : "Failed"}
        </span>
      )}
    </form>
  );
}

export default function Settings() {
  const { username, logout } = useAuth();
  const navigate = useNavigate();
  const qc = useQueryClient();

  const repsQ = useQuery({
    queryKey: ["sales-reps"],
    queryFn: () => salesRepsApi.list(),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => salesRepsApi.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sales-reps"] }),
  });

  return (
    <div className="space-y-8 max-w-4xl">
      <div>
        <h1 className="text-xl sm:text-2xl font-bold tracking-tight">Settings</h1>
        <p className="text-sm text-zinc-500 mt-1">Account and distributor preferences.</p>
      </div>

      {/* Account section */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-500">Account</h2>
        <div className="bg-white rounded-lg border border-zinc-200 p-4 space-y-3">
          <div className="text-zinc-700">
            Signed in as <span className="font-medium">{username ?? "—"}</span>
          </div>
          <button
            type="button"
            onClick={() => {
              logout();
              navigate("/login", { replace: true });
            }}
            className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm font-medium text-zinc-700 hover:bg-zinc-50"
          >
            Sign out
          </button>
        </div>
      </section>

      {/* Sales Reps section */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-500">
          Sales Reps
        </h2>
        <p className="text-sm text-zinc-500">
          Register distributor sales reps by division. You can email orders directly to them from the Orders page.
        </p>

        <div className="bg-white rounded-lg border border-zinc-200 overflow-hidden">
          {repsQ.isLoading ? (
            <div className="p-4 text-sm text-zinc-400">Loading...</div>
          ) : repsQ.data && repsQ.data.length > 0 ? (
            <table className="w-full text-left">
              <thead>
                <tr className="bg-zinc-50 border-b border-zinc-200">
                  <th className="px-3 py-2 text-xs font-medium text-zinc-500 uppercase">Name</th>
                  <th className="px-3 py-2 text-xs font-medium text-zinc-500 uppercase">Email</th>
                  <th className="px-3 py-2 text-xs font-medium text-zinc-500 uppercase hidden sm:table-cell">Phone</th>
                  <th className="px-3 py-2 text-xs font-medium text-zinc-500 uppercase hidden sm:table-cell">Division</th>
                  <th className="px-3 py-2 text-xs font-medium text-zinc-500 uppercase text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {repsQ.data.map((rep) => (
                  <RepRow
                    key={rep.id}
                    rep={rep}
                    onDelete={(id) => deleteMut.mutate(id)}
                  />
                ))}
              </tbody>
            </table>
          ) : (
            <div className="p-4 text-sm text-zinc-400">
              No sales reps registered yet. Add one below.
            </div>
          )}
        </div>

        <AddRepForm onAdded={() => qc.invalidateQueries({ queryKey: ["sales-reps"] })} />
      </section>
    </div>
  );
}
