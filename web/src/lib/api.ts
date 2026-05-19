/** Typed API client for LiquorPriceBook. Attaches the bearer token from
 * lpb_auth on every request and proxies through Vite's dev proxy in dev.
 */

import { getAuthHeader } from "./auth";

const API_BASE: string = (import.meta.env.VITE_API_URL as string | undefined) ?? "";

type FetchOpts = RequestInit & { json?: unknown };

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

function _qs(params: Record<string, unknown>): string {
  const search = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) {
      for (const item of v) search.append(k, String(item));
    } else {
      search.set(k, String(v));
    }
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}

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

// ---------- typed wrappers ----------

export type Distributor = { id: string; slug: string; name: string; state: string };

export type IngestRun = {
  id: string;
  book_edition_id: string;
  status: "pending" | "running" | "completed" | "failed" | "superseded";
  started_at: string | null;
  finished_at: string | null;
  rows_by_section: Record<string, number>;
  error: Record<string, unknown> | null;
  created_at: string;
  distributor_slug?: string | null;
  distributor_name?: string | null;
  book_year?: number | null;
  book_month?: number | null;
  source_filename?: string | null;
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

export type Edition = {
  id: string;
  distributor_id: string;
  distributor_slug: string;
  year: number;
  month: number;
  label: string;
  is_current: boolean;
};

export type Category = {
  id: string;
  slug: string;
  display_name: string;
  sort_order: number;
  product_count: number;
};

export type Brand = {
  id: string;
  slug: string;
  display_name: string;
  product_count: number;
};

export type ProductRow = {
  code: string;
  description: string | null;
  size: string | null;
  pack: number | null;
  case_cost: string | null;
  btl_cost: string | null;
  category_slug: string | null;
  brand_slug: string | null;
  has_rip: boolean;
  top_rip_save: string | null;
  top_rip_tier: string | null;
  case_cost_pct: string | null;
};

export type ProductList = {
  items: ProductRow[];
  total: number;
  limit: number;
  offset: number;
  edition: Edition;
};

export type PriceHistoryPoint = {
  year: number;
  month: number;
  label: string;
  case_cost: string | null;
  btl_cost: string | null;
};

export type RipDetail = {
  tier: string;
  tier_cases: number;
  save_amount: string;
  case_price: string | null;
  btl_price: string | null;
};

export type Partial = {
  kind: "pricing" | "rip";
  description: string | null;
  start_date: string;
  end_date: string;
  best_case_price?: string | null;
  best_case_tier?: string | null;
  best_btl_price?: string | null;
  tier?: string | null;
  rip_price?: string | null;
  match_confidence?: string | null;
};

export type ProductDetail = {
  code: string;
  distributor_slug: string;
  description: string | null;
  size: string | null;
  pack: number | null;
  category_slug: string | null;
  category_display: string | null;
  brand_slug: string | null;
  brand_display: string | null;
  case_cost: string | null;
  btl_cost: string | null;
  prev_case_cost: string | null;
  case_cost_pct: string | null;
  price_history: PriceHistoryPoint[];
  current_rips: RipDetail[];
  active_partials: Partial[];
};

export type RipRow = {
  code: string;
  description: string | null;
  size: string | null;
  pack: number | null;
  category_slug: string | null;
  brand_slug: string | null;
  case_cost: string | null;
  tier: string;
  tier_cases: number;
  save_amount: string;
  case_price: string | null;
  btl_price: string | null;
  effective_pct: number | null;
  stable: boolean | null;
};

export type CloseoutRow = {
  code: string;
  description: string | null;
  size: string | null;
  pack: number | null;
  original_case: string | null;
  best_case: string | null;
  case_save: string | null;
  pct_off: number | null;
  days_on_list: number;
};

export type MoverRow = {
  code: string;
  description: string | null;
  category_slug: string | null;
  brand_slug: string | null;
  case_cost: string | null;
  prev_case_cost: string | null;
  case_cost_pct: string | null;
};

export type AlertEvent = {
  id: string;
  rule_type: string;
  score: string | null;
  payload: Record<string, unknown>;
  fired_at: string;
  read_at: string | null;
  product_code: string | null;
};

export type WatchlistItem = {
  product_code: string;
  product_description?: string | null;
  target_case_price: string | null;
  target_btl_price: string | null;
  notes: string | null;
  created_at: string;
};

export type Note = {
  id: string;
  product_code: string;
  body: string;
  created_at: string;
  updated_at: string;
};

export type Verdict = {
  verdict: "BUY_NOW" | "DEFER" | "HOLD" | "PASS";
  confidence: string;
  rationale: string;
  factors: Record<string, unknown>;
  model: string;
  generated_at: string;
  cached: boolean;
};

// ---------- API surface ----------

export const adminApi = {
  listDistributors: () => api<Distributor[]>("/api/v1/admin/distributors"),
  listRuns: (limit = 50) => api<IngestRun[]>(`/api/v1/admin/ingest/runs?limit=${limit}`),
  getRun: (id: string) => api<IngestRun>(`/api/v1/admin/ingest/runs/${id}`),
  retryRun: (id: string) =>
    api<IngestRun>(`/api/v1/admin/ingest/runs/${id}/retry`, { method: "POST" }),
  uploadIngest: (file: File, distributorSlug: string) => {
    const fd = new FormData();
    fd.append("pdf", file);
    fd.append("distributor", distributorSlug);
    return apiUpload<IngestEnqueueResult>("/api/v1/admin/ingest", fd);
  },
};

export const catalogApi = {
  editions: () => api<Edition[]>("/api/v1/catalog/editions"),
  categories: (distributor = "nj-allied") =>
    api<Category[]>(`/api/v1/catalog/categories${_qs({ distributor })}`),
  brands: (params: { distributor?: string; q?: string; limit?: number } = {}) =>
    api<Brand[]>(`/api/v1/catalog/brands${_qs(params)}`),
  products: (params: {
    distributor?: string;
    category?: string[];
    brand?: string[];
    size?: string[];
    search?: string;
    has_rip?: boolean;
    min_case_cost?: number;
    max_case_cost?: number;
    sort?: string;
    limit?: number;
    offset?: number;
  }) => api<ProductList>(`/api/v1/catalog/products${_qs(params)}`),
  product: (code: string, distributor = "nj-allied") =>
    api<ProductDetail>(`/api/v1/catalog/products/${code}${_qs({ distributor })}`),
};

export const insightsApi = {
  rips: (params: {
    distributor?: string;
    category?: string[];
    min_pct?: number;
    tier_cases_max?: number;
    limit?: number;
  } = {}) => api<RipRow[]>(`/api/v1/rips${_qs(params)}`),
  closeouts: (params: { distributor?: string; min_pct?: number; limit?: number } = {}) =>
    api<CloseoutRow[]>(`/api/v1/closeouts${_qs(params)}`),
  movers: (params: { distributor?: string; direction?: "up" | "down" | "any"; limit?: number } = {}) =>
    api<MoverRow[]>(`/api/v1/dashboard/movers${_qs(params)}`),
  watchlistMovers: (distributor = "nj-allied") =>
    api<MoverRow[]>(`/api/v1/dashboard/watchlist-movers${_qs({ distributor })}`),
  alerts: (params: { limit?: number; unread_only?: boolean } = {}) =>
    api<AlertEvent[]>(`/api/v1/dashboard/alerts${_qs(params)}`),
};

export const watchlistApi = {
  list: () => api<WatchlistItem[]>("/api/v1/watchlist"),
  add: (body: {
    code: string;
    distributor?: string;
    target_case_price?: number | null;
    target_btl_price?: number | null;
    notes?: string | null;
  }) => api<WatchlistItem>("/api/v1/watchlist/items", { method: "POST", json: body }),
  update: (
    code: string,
    body: {
      target_case_price?: number | null;
      target_btl_price?: number | null;
      notes?: string | null;
    },
    distributor = "nj-allied",
  ) =>
    api<WatchlistItem>(
      `/api/v1/watchlist/items/${code}${_qs({ distributor })}`,
      { method: "PATCH", json: body },
    ),
  remove: (code: string, distributor = "nj-allied") =>
    api<void>(`/api/v1/watchlist/items/${code}${_qs({ distributor })}`, { method: "DELETE" }),
};

export const notesApi = {
  list: (code: string, distributor = "nj-allied") =>
    api<Note[]>(`/api/v1/products/${code}/notes${_qs({ distributor })}`),
  add: (code: string, body: string, distributor = "nj-allied") =>
    api<Note>(
      `/api/v1/products/${code}/notes${_qs({ distributor })}`,
      { method: "POST", json: { body } },
    ),
  update: (id: string, body: string) =>
    api<Note>(`/api/v1/notes/${id}`, { method: "PATCH", json: { body } }),
  remove: (id: string) => api<void>(`/api/v1/notes/${id}`, { method: "DELETE" }),
};

export const aiApi = {
  verdict: (code: string, distributor = "nj-allied", refresh = false) =>
    api<Verdict>(
      `/api/v1/products/${code}/verdict${_qs({ distributor, refresh: refresh || undefined })}`,
    ),
};
