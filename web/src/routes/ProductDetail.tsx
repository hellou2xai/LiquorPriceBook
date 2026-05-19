import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { aiApi, catalogApi, notesApi, watchlistApi } from "../lib/api";
import { money, pct, pctClass } from "../lib/fmt";

export default function ProductDetail() {
  const { code = "" } = useParams<{ code: string }>();
  const qc = useQueryClient();

  const detailQ = useQuery({
    queryKey: ["product", code],
    queryFn: () => catalogApi.product(code),
    enabled: !!code,
  });

  const verdictQ = useQuery({
    queryKey: ["verdict", code],
    queryFn: () => aiApi.verdict(code),
    enabled: !!code,
  });

  const watchQ = useQuery({
    queryKey: ["watchlist"],
    queryFn: () => watchlistApi.list(),
    staleTime: 30_000,
  });
  const onWatchlist = (watchQ.data ?? []).some((w) => w.product_code === code);

  const notesQ = useQuery({
    queryKey: ["notes", code],
    queryFn: () => notesApi.list(code),
    enabled: !!code,
  });

  const addWatch = useMutation({
    mutationFn: () => watchlistApi.add({ code }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlist"] }),
  });
  const removeWatch = useMutation({
    mutationFn: () => watchlistApi.remove(code),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlist"] }),
  });

  const addNote = useMutation({
    mutationFn: (body: string) => notesApi.add(code, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notes", code] }),
  });

  if (!detailQ.data && detailQ.isLoading) {
    return <div className="text-zinc-500">Loading…</div>;
  }
  if (detailQ.isError) {
    return <div className="text-red-700">Failed to load product.</div>;
  }
  const d = detailQ.data!;
  const chartData = d.price_history.map((p) => ({
    label: p.label,
    case_cost: p.case_cost ? parseFloat(p.case_cost) : null,
  }));

  return (
    <div className="space-y-6">
      <header className="flex flex-col md:flex-row md:items-end md:justify-between gap-3">
        <div className="space-y-1">
          <div className="text-xs uppercase tracking-wide text-zinc-500">
            {d.category_display ?? "Uncategorised"}
            {d.brand_display ? <span> · {d.brand_display}</span> : null}
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">
            {d.description ?? "Product"}
          </h1>
          <div className="text-sm text-zinc-600 font-mono">
            {d.code} · {d.size ?? "—"} · pack {d.pack ?? "—"}
          </div>
        </div>
        <div className="flex gap-2">
          {onWatchlist ? (
            <button
              onClick={() => removeWatch.mutate()}
              disabled={removeWatch.isPending}
              className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm hover:bg-zinc-50 disabled:opacity-50"
            >
              Remove from watchlist
            </button>
          ) : (
            <button
              onClick={() => addWatch.mutate()}
              disabled={addWatch.isPending}
              className="rounded-md bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-60"
            >
              Add to watchlist
            </button>
          )}
        </div>
      </header>

      {/* Price summary + verdict */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <PriceCard label="Case cost" value={money(d.case_cost)}>
          {d.prev_case_cost ? (
            <div className="text-xs text-zinc-500">
              was {money(d.prev_case_cost)} ·{" "}
              <span className={pctClass(d.case_cost_pct)}>{pct(d.case_cost_pct)}</span>
            </div>
          ) : null}
        </PriceCard>
        <PriceCard label="Bottle cost" value={money(d.btl_cost)} />
        <VerdictCard verdict={verdictQ.data} loading={verdictQ.isLoading} />
      </div>

      {/* Price history chart */}
      <section className="rounded-lg border border-zinc-200 bg-white p-4">
        <h2 className="text-sm font-medium text-zinc-700 mb-2">Price history (case)</h2>
        <div className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData}>
              <XAxis dataKey="label" stroke="#52525b" fontSize={11} />
              <YAxis stroke="#52525b" fontSize={11} domain={["dataMin", "dataMax"]} />
              <Tooltip />
              <Line
                type="monotone"
                dataKey="case_cost"
                stroke="#0a0a0a"
                strokeWidth={2}
                dot={{ r: 3 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </section>

      {/* Current RIPs */}
      {d.current_rips.length > 0 ? (
        <section className="rounded-lg border border-zinc-200 bg-white">
          <header className="border-b border-zinc-200 px-4 py-2 text-sm font-medium text-zinc-700">
            Current RIP tiers
          </header>
          <table className="min-w-full text-sm">
            <thead className="text-xs uppercase text-zinc-500">
              <tr>
                <th className="px-4 py-2 text-left">Tier</th>
                <th className="px-4 py-2 text-right">Save</th>
                <th className="px-4 py-2 text-right">Case after RIP</th>
                <th className="px-4 py-2 text-right">Btl after RIP</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {d.current_rips.map((r) => (
                <tr key={r.tier}>
                  <td className="px-4 py-2 font-mono">{r.tier}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{money(r.save_amount)}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{money(r.case_price)}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{money(r.btl_price)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}

      {/* Active partials */}
      {d.active_partials.length > 0 ? (
        <section className="rounded-lg border border-zinc-200 bg-white">
          <header className="border-b border-zinc-200 px-4 py-2 text-sm font-medium text-zinc-700">
            Active partials
          </header>
          <ul className="divide-y divide-zinc-100">
            {d.active_partials.map((p, i) => (
              <li key={i} className="px-4 py-2 text-sm">
                <span className="inline-flex items-center rounded-md border px-1.5 py-0.5 text-xs font-medium mr-2 bg-amber-50 border-amber-200 text-amber-800">
                  {p.kind}
                </span>
                {p.description}
                <span className="text-zinc-500"> · {p.start_date} → {p.end_date}</span>
                {p.best_case_price ? (
                  <span className="text-zinc-700"> · case {money(p.best_case_price)}</span>
                ) : null}
                {p.rip_price ? (
                  <span className="text-zinc-700"> · rip {p.tier ?? ""} {money(p.rip_price)}</span>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {/* Notes */}
      <section className="rounded-lg border border-zinc-200 bg-white">
        <header className="border-b border-zinc-200 px-4 py-2 text-sm font-medium text-zinc-700">
          Notes
        </header>
        <NoteForm onAdd={(b) => addNote.mutate(b)} disabled={addNote.isPending} />
        <ul className="divide-y divide-zinc-100">
          {(notesQ.data ?? []).length === 0 ? (
            <li className="px-4 py-3 text-sm text-zinc-500">No notes yet.</li>
          ) : (
            (notesQ.data ?? []).map((n) => (
              <li key={n.id} className="px-4 py-3 text-sm">
                <div className="text-zinc-800 whitespace-pre-wrap">{n.body}</div>
                <div className="mt-1 text-xs text-zinc-500">
                  {new Date(n.created_at).toLocaleString()}
                </div>
              </li>
            ))
          )}
        </ul>
      </section>
    </div>
  );
}

function PriceCard({
  label,
  value,
  children,
}: {
  label: string;
  value: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4">
      <div className="text-xs uppercase text-zinc-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold tracking-tight tabular-nums">{value}</div>
      {children}
    </div>
  );
}

function VerdictCard({
  verdict,
  loading,
}: {
  verdict: ReturnType<typeof useQuery<Awaited<ReturnType<typeof aiApi.verdict>>>>["data"];
  loading: boolean;
}) {
  if (loading) {
    return (
      <div className="rounded-lg border border-zinc-200 bg-white p-4 text-sm text-zinc-500">
        Analysing…
      </div>
    );
  }
  if (!verdict) {
    return (
      <div className="rounded-lg border border-zinc-200 bg-white p-4 text-sm text-zinc-500">
        Verdict unavailable.
      </div>
    );
  }
  const color =
    verdict.verdict === "BUY_NOW"
      ? "bg-emerald-50 border-emerald-200 text-emerald-900"
      : verdict.verdict === "DEFER"
        ? "bg-amber-50 border-amber-200 text-amber-900"
        : verdict.verdict === "PASS"
          ? "bg-zinc-100 border-zinc-300 text-zinc-700"
          : "bg-sky-50 border-sky-200 text-sky-900";
  return (
    <div className={`rounded-lg border p-4 ${color}`}>
      <div className="flex items-center justify-between">
        <div className="text-xs uppercase">AI verdict</div>
        <div className="text-xs">
          confidence {(parseFloat(verdict.confidence) * 100).toFixed(0)}%
        </div>
      </div>
      <div className="mt-1 text-xl font-semibold tracking-tight">
        {verdict.verdict.replace("_", " ")}
      </div>
      <p className="mt-1 text-sm">{verdict.rationale}</p>
      <div className="mt-2 text-[10px] uppercase tracking-wide opacity-70">
        {verdict.cached ? "cached" : "fresh"} · {verdict.model}
      </div>
    </div>
  );
}

function NoteForm({ onAdd, disabled }: { onAdd: (body: string) => void; disabled: boolean }) {
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        const fd = new FormData(e.currentTarget);
        const body = String(fd.get("body") ?? "").trim();
        if (!body) return;
        onAdd(body);
        e.currentTarget.reset();
      }}
      className="border-b border-zinc-200 p-3 flex gap-2"
    >
      <input
        name="body"
        type="text"
        placeholder="Add a note for this product…"
        className="flex-1 rounded-md border border-zinc-300 bg-white px-2.5 py-2 text-sm"
      />
      <button
        type="submit"
        disabled={disabled}
        className="rounded-md bg-zinc-900 px-3 py-2 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-50"
      >
        Save
      </button>
    </form>
  );
}
