import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Ref } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import PageStub from "../components/PageStub";
import { ApiError, adminApi } from "../lib/api";
import type { IngestRun } from "../lib/api";

const POLL_MS = 2_000;

export default function AdminIngest() {
  const qc = useQueryClient();
  const [selectedDistributor, setSelectedDistributor] = useState("nj-allied");
  const [lastResult, setLastResult] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const distributors = useQuery({
    queryKey: ["distributors"],
    queryFn: adminApi.listDistributors,
  });

  const runsQuery = useQuery<IngestRun[]>({
    queryKey: ["ingest-runs"],
    queryFn: () => adminApi.listRuns(20),
    refetchInterval: ({ state }) => {
      const data = state.data;
      if (!data) return false;
      const anyActive = data.some((r) => r.status === "pending" || r.status === "running");
      return anyActive ? POLL_MS : false;
    },
  });

  const uploadMutation = useMutation({
    mutationFn: ({ file, distributor }: { file: File; distributor: string }) =>
      adminApi.uploadIngest(file, distributor),
    onSuccess: (res) => {
      setErrorMsg(null);
      setLastResult(
        res.reused_existing_edition
          ? `Re-enqueued ingest for existing edition ${res.year}-${String(res.month).padStart(2, "0")}`
          : `Uploaded ${res.year}-${String(res.month).padStart(2, "0")} (${res.content_hash.slice(0, 8)}…) and enqueued ingest`,
      );
      qc.invalidateQueries({ queryKey: ["ingest-runs"] });
      if (fileInputRef.current) fileInputRef.current.value = "";
    },
    onError: (err) => {
      setLastResult(null);
      setErrorMsg(err instanceof ApiError ? err.message : "Upload failed");
    },
  });

  const retryMutation = useMutation({
    mutationFn: (id: string) => adminApi.retryRun(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ingest-runs"] }),
  });

  const onFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      uploadMutation.mutate({ file, distributor: selectedDistributor });
    },
    [selectedDistributor, uploadMutation],
  );

  const distributorOptions = useMemo(
    () => (distributors.data ?? []).map((d) => ({ slug: d.slug, label: `${d.name} (${d.slug})` })),
    [distributors.data],
  );

  return (
    <PageStub
      title="Admin · Ingest"
      subtitle="Upload a price-book PDF. The API scrapes, normalises, and writes to the database in the background."
    >
      <div className="space-y-6">
        <UploadCard
          distributorOptions={distributorOptions}
          selectedDistributor={selectedDistributor}
          onSelectDistributor={setSelectedDistributor}
          fileInputRef={fileInputRef}
          onFileChange={onFileChange}
          isUploading={uploadMutation.isPending}
          lastResult={lastResult}
          errorMsg={errorMsg}
        />

        <RunsList
          runs={runsQuery.data ?? []}
          loading={runsQuery.isLoading}
          onRetry={(id) => retryMutation.mutate(id)}
          retryingId={retryMutation.variables ?? null}
        />
      </div>
    </PageStub>
  );
}

// ---------- subcomponents -------------------------------------------------

function UploadCard({
  distributorOptions,
  selectedDistributor,
  onSelectDistributor,
  fileInputRef,
  onFileChange,
  isUploading,
  lastResult,
  errorMsg,
}: {
  distributorOptions: { slug: string; label: string }[];
  selectedDistributor: string;
  onSelectDistributor: (slug: string) => void;
  fileInputRef: Ref<HTMLInputElement>;
  onFileChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  isUploading: boolean;
  lastResult: string | null;
  errorMsg: string | null;
}) {
  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-5">
      <h2 className="text-base font-medium text-zinc-900">Upload a new price book</h2>
      <p className="mt-1 text-sm text-zinc-500">
        PDF filename should include the edition (e.g. <code className="text-xs">2026-05 Price Book.pdf</code>).
      </p>

      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-[180px_1fr]">
        <div>
          <label className="block text-xs font-medium text-zinc-600">Distributor</label>
          <select
            className="mt-1 block w-full rounded-md border border-zinc-300 bg-white px-2.5 py-2 text-sm"
            value={selectedDistributor}
            onChange={(e) => onSelectDistributor(e.target.value)}
            disabled={isUploading}
          >
            {distributorOptions.map((opt) => (
              <option key={opt.slug} value={opt.slug}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-zinc-600">Price-book PDF</label>
          <input
            ref={fileInputRef}
            type="file"
            accept="application/pdf"
            onChange={onFileChange}
            disabled={isUploading}
            className="mt-1 block w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-zinc-900 file:px-3 file:py-2 file:text-sm file:font-medium file:text-white hover:file:bg-zinc-800"
          />
        </div>
      </div>

      <div className="mt-4 min-h-[1.5rem] text-sm">
        {isUploading ? <span className="text-zinc-600">Uploading…</span> : null}
        {lastResult ? <span className="text-emerald-700">{lastResult}</span> : null}
        {errorMsg ? <span className="text-red-700">{errorMsg}</span> : null}
      </div>
    </div>
  );
}

function RunsList({
  runs,
  loading,
  onRetry,
  retryingId,
}: {
  runs: IngestRun[];
  loading: boolean;
  onRetry: (id: string) => void;
  retryingId: string | null;
}) {
  return (
    <div className="rounded-lg border border-zinc-200 bg-white">
      <div className="border-b border-zinc-200 px-5 py-3">
        <h2 className="text-base font-medium text-zinc-900">Recent ingest runs</h2>
        <p className="text-xs text-zinc-500 mt-0.5">
          Live status: pending → running → completed (refreshes every 2s while active).
        </p>
      </div>
      <ul className="divide-y divide-zinc-100">
        {loading ? (
          <li className="px-5 py-6 text-center text-zinc-500 text-sm">Loading…</li>
        ) : runs.length === 0 ? (
          <li className="px-5 py-6 text-center text-zinc-500 text-sm">
            No ingest runs yet. Upload a PDF above to kick one off.
          </li>
        ) : (
          runs.map((r) => (
            <RunRow key={r.id} run={r} onRetry={onRetry} retrying={retryingId === r.id} />
          ))
        )}
      </ul>
    </div>
  );
}

function RunRow({
  run,
  onRetry,
  retrying,
}: {
  run: IngestRun;
  onRetry: (id: string) => void;
  retrying: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const rowCounts = run.rows_by_section ?? {};
  const totalRows = useMemo(
    () => Object.values(rowCounts).reduce((a, b) => a + (b ?? 0), 0),
    [rowCounts],
  );
  const dur = duration(run.started_at, run.finished_at);
  const editionLabel =
    run.book_year && run.book_month
      ? `${run.book_year}-${String(run.book_month).padStart(2, "0")}`
      : "—";
  const stuck =
    run.status === "pending" &&
    Date.now() - new Date(run.created_at).getTime() > 120_000;

  return (
    <li className="px-5 py-3">
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <StatusBadge status={run.status} />
        <span className="font-mono text-xs text-zinc-700 tabular-nums">
          {editionLabel}
        </span>
        <span className="text-zinc-600 flex-1 truncate" title={run.source_filename ?? ""}>
          {run.distributor_name ?? run.distributor_slug ?? "—"} ·{" "}
          {run.source_filename ?? "—"}
        </span>
        <span className="text-xs text-zinc-500 tabular-nums">
          {run.status === "completed"
            ? `${totalRows.toLocaleString()} rows · ${dur}`
            : run.status === "running"
              ? `running · ${dur}`
              : run.status === "failed"
                ? "failed"
                : run.status === "pending"
                  ? stuck
                    ? "pending (stuck?)"
                    : "queued"
                  : run.status}
        </span>
        <button
          onClick={() => setExpanded((v) => !v)}
          className="text-xs text-zinc-500 hover:text-zinc-900"
        >
          {expanded ? "Hide" : "Details"}
        </button>
        {(run.status === "failed" || stuck) ? (
          <button
            onClick={() => onRetry(run.id)}
            disabled={retrying}
            className="text-xs text-amber-700 hover:text-amber-900 disabled:opacity-50"
          >
            {retrying ? "Retrying…" : "Retry"}
          </button>
        ) : null}
      </div>

      {expanded ? (
        <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
          <DetailBlock label="Run ID" value={run.id} mono />
          <DetailBlock label="Book edition ID" value={run.book_edition_id} mono />
          <DetailBlock
            label="Created"
            value={new Date(run.created_at).toLocaleString()}
          />
          <DetailBlock
            label="Started"
            value={run.started_at ? new Date(run.started_at).toLocaleString() : "—"}
          />
          <DetailBlock
            label="Finished"
            value={run.finished_at ? new Date(run.finished_at).toLocaleString() : "—"}
          />
          <DetailBlock label="Source" value={run.source_filename ?? "—"} mono />
          {Object.keys(rowCounts).length > 0 ? (
            <div className="md:col-span-2">
              <div className="text-zinc-500 mb-1">Rows by section</div>
              <div className="rounded-md border border-zinc-200 bg-zinc-50 p-2">
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-x-4 gap-y-1 font-mono text-[11px]">
                  {Object.entries(rowCounts).map(([k, v]) => (
                    <div key={k} className="flex justify-between">
                      <span className="text-zinc-600">{k}</span>
                      <span className="tabular-nums text-zinc-900">
                        {(v ?? 0).toLocaleString()}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : null}
          {run.error ? (
            <div className="md:col-span-2">
              <div className="text-zinc-500 mb-1">Error</div>
              <pre className="rounded-md border border-red-200 bg-red-50 p-2 text-[11px] text-red-900 overflow-x-auto">
                {JSON.stringify(run.error, null, 2)}
              </pre>
            </div>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}

function DetailBlock({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div>
      <div className="text-zinc-500">{label}</div>
      <div className={`text-zinc-800 ${mono ? "font-mono" : ""}`}>{value}</div>
    </div>
  );
}

function StatusBadge({ status }: { status: IngestRun["status"] }) {
  const cls =
    status === "completed"
      ? "bg-emerald-50 text-emerald-700 border-emerald-200"
      : status === "running"
        ? "bg-blue-50 text-blue-700 border-blue-200"
        : status === "pending"
          ? "bg-zinc-50 text-zinc-600 border-zinc-200"
          : status === "failed"
            ? "bg-red-50 text-red-700 border-red-200"
            : "bg-zinc-100 text-zinc-700 border-zinc-300";
  return (
    <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${cls}`}>
      {status}
    </span>
  );
}

function duration(start: string | null, end: string | null): string {
  if (!start) return "—";
  const s = new Date(start).getTime();
  const e = end ? new Date(end).getTime() : Date.now();
  const sec = Math.max(0, Math.round((e - s) / 1000));
  if (sec < 60) return `${sec}s`;
  return `${Math.floor(sec / 60)}m ${sec % 60}s`;
}

// Refetch on mount when the user navigates into this page.
export function useAdminIngestPagePrefetch() {
  const qc = useQueryClient();
  useEffect(() => {
    qc.prefetchQuery({ queryKey: ["distributors"], queryFn: adminApi.listDistributors });
  }, [qc]);
}
