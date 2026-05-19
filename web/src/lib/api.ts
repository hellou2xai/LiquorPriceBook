/** Tiny API client. Reads VITE_API_URL (empty by default; the Vite dev proxy
 * forwards /api to the local FastAPI) and attaches the bearer token from
 * lpb_auth on every request.
 */

import { getAuthHeader } from "./auth";

const API_BASE: string = (import.meta.env.VITE_API_URL as string | undefined) ?? "";

type FetchOpts = RequestInit & { json?: unknown };

export async function api<T>(path: string, opts: FetchOpts = {}): Promise<T> {
  const headers = new Headers(opts.headers);
  const auth = getAuthHeader();
  if (auth) headers.set("Authorization", auth);
  if (opts.json !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const init: RequestInit = {
    ...opts,
    headers,
    body: opts.json !== undefined ? JSON.stringify(opts.json) : opts.body,
  };
  delete (init as FetchOpts).json;

  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    const detail = await res
      .json()
      .then((b) => b.detail ?? res.statusText)
      .catch(() => res.statusText);
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export async function apiUpload<T>(path: string, formData: FormData): Promise<T> {
  const headers = new Headers();
  const auth = getAuthHeader();
  if (auth) headers.set("Authorization", auth);
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers,
    body: formData,
  });
  if (!res.ok) {
    const detail = await res
      .json()
      .then((b) => b.detail ?? res.statusText)
      .catch(() => res.statusText);
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return (await res.json()) as T;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

// ---------- typed wrappers ----------

export type Distributor = {
  id: string;
  slug: string;
  name: string;
  state: string;
};

export type IngestRun = {
  id: string;
  book_edition_id: string;
  status: "pending" | "running" | "completed" | "failed" | "superseded";
  started_at: string | null;
  finished_at: string | null;
  rows_by_section: Record<string, number>;
  error: Record<string, unknown> | null;
  created_at: string;
};

export type IngestEnqueueResult = {
  ingest_run_id: string;
  book_edition_id: string;
  distributor_slug: string;
  year: number;
  month: number;
  content_hash: string;
  reused_existing_edition: boolean;
};

export const adminApi = {
  listDistributors: () => api<Distributor[]>("/api/v1/admin/distributors"),
  listRuns: (limit = 50) => api<IngestRun[]>(`/api/v1/admin/ingest/runs?limit=${limit}`),
  getRun: (id: string) => api<IngestRun>(`/api/v1/admin/ingest/runs/${id}`),
  uploadIngest: (file: File, distributorSlug: string) => {
    const fd = new FormData();
    fd.append("pdf", file);
    fd.append("distributor", distributorSlug);
    return apiUpload<IngestEnqueueResult>("/api/v1/admin/ingest", fd);
  },
};
