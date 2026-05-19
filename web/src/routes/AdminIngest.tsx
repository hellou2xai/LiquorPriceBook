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
      subtitle="Upload a price-book PDF. The worker scrapes, normalises, and writes to the database."
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

        <RunsTable runs={runsQuery.data ?? []} loading={runsQuery.isLoading} />
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

function RunsTable({ runs, loading }: { runs: IngestRun[]; loading: boolean }) {
  return (
    <div className="rounded-lg border border-zinc-200 bg-white">
      <div className="border-b border-zinc-200 px-5 py-3">
        <h2 className="text-base font-medium text-zinc-900">Recent ingest runs</h2>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-zinc-200 text-sm">
          <thead className="bg-zinc-50 text-left text-xs uppercase tracking-wide text-zinc-500">
            <tr>
              <th className="px-4 py-2">Status</th>
              <th className="px-4 py-2">Started</th>
              <th className="px-4 py-2">Finished</th>
              <th className="px-4 py-2">Rows</th>
              <th className="px-4 py-2">Run ID</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-100">
            {loading ? (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-zinc-500">
                  Loading…
                </td>
              </tr>
            ) : runs.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-zinc-500">
                  No ingest runs yet. Upload a PDF above to kick one off.
                </td>
              </tr>
            ) : (
              runs.map((r) => <RunRow key={r.id} run={r} />)
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function RunRow({ run }: { run: IngestRun }) {
  const totalRows = useMemo(
    () => Object.values(run.rows_by_section ?? {}).reduce((a, b) => a + (b ?? 0), 0),
    [run.rows_by_section],
  );
  return (
    <tr>
      <td className="whitespace-nowrap px-4 py-2">
        <StatusBadge status={run.status} />
      </td>
      <td className="whitespace-nowrap px-4 py-2 text-zinc-700">{fmt(run.started_at)}</td>
      <td className="whitespace-nowrap px-4 py-2 text-zinc-700">{fmt(run.finished_at)}</td>
      <td className="whitespace-nowrap px-4 py-2 text-zinc-700 tabular-nums">
        {run.status === "completed" ? totalRows.toLocaleString() : "—"}
      </td>
      <td className="whitespace-nowrap px-4 py-2 font-mono text-xs text-zinc-500">{run.id.slice(0, 8)}</td>
    </tr>
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

function fmt(ts: string | null): string {
  if (!ts) return "—";
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return ts;
  }
}

// Refetch on mount when the user navigates into this page.
export function useAdminIngestPagePrefetch() {
  const qc = useQueryClient();
  useEffect(() => {
    qc.prefetchQuery({ queryKey: ["distributors"], queryFn: adminApi.listDistributors });
  }, [qc]);
}
