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
  divisions: string | null;
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
  divisions: string | null;
  case_cost: string | null;
  btl_cost: string | null;
  prev_case_cost: string | null;
  case_cost_pct: string | null;
  price_history: PriceHistoryPoint[];
  current_rips: RipDetail[];
  active_partials: Partial[];
};

export type DivisionFacet = { code: string; product_count: number };
export type SizeFacet = { size: string; product_count: number };
export type BrandFacet = { slug: string; display_name: string; product_count: number };
export type Facets = {
  divisions: DivisionFacet[];
  sizes: SizeFacet[];
  brands: BrandFacet[];
  price_min: number | null;
  price_max: number | null;
  total_products: number;
  total_with_rip: number;
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

export type ComboRow = {
  sku: string;
  subcategory: string | null;
  item_code: string | null;
  contains: string | null;
  front_line_price: string | null;
};

export type DashboardSummary = {
  edition_label: string;
  edition_year: number;
  edition_month: number;
  total_products: number;
  total_rips: number;
  total_closeouts: number;
  total_combos: number;
  products_price_down: number;
  products_price_up: number;
  products_price_flat: number;
  avg_price_change_pct: number | null;
  rip_total_potential_savings: number;
  rip_avg_discount_pct: number | null;
  top_rip_categories: { category: string; count: number; avg_save: number }[];
  watchlist_count: number;
  watchlist_buy_now: number;
  category_product_counts: { category: string; count: number }[];
  top_price_drops: { code: string; description: string | null; case_cost: string | null; prev_case_cost: string | null; pct_change: string | null }[];
  top_price_increases: { code: string; description: string | null; case_cost: string | null; prev_case_cost: string | null; pct_change: string | null }[];
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

export type RipTier = {
  tier: string;
  tier_cases: number;
  save_amount: string;
  case_price: string | null;
  btl_price: string | null;
  effective_case: string | null;
  effective_btl: string | null;
  discount_pct: string | null;
};

export type OrderItem = {
  product_code: string;
  description: string | null;
  size: string | null;
  pack: number | null;
  category_slug: string | null;
  category_display: string | null;
  brand_slug: string | null;
  brand_display: string | null;
  divisions: string | null;
  case_cost: string | null;
  btl_cost: string | null;
  has_rip: boolean;
  rip_tier: string | null;
  rip_tier_cases: number | null;
  rip_save_amount: string | null;
  rip_case_price: string | null;
  rip_btl_price: string | null;
  effective_case: string | null;
  effective_btl: string | null;
  rip_discount_pct: string | null;
  all_rips: RipTier[];
  // Buy-timing intelligence
  prev_case_cost: string | null;
  price_pct_change: string | null;
  price_direction: string | null;
  low_12m: string | null;
  high_12m: string | null;
  avg_12m: string | null;
  months_at_price: number | null;
  at_12m_low: boolean;
  at_12m_high: boolean;
  had_rip_prev: boolean;
  buy_signal: string;
  buy_reasons: string[];
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

export type WebSpecial = {
  id: string;
  kind: "pricing" | "rip";
  description: string;
  size: string | null;
  start_date: string;
  end_date: string;
  days_remaining: number;
  best_case_price: string | null;
  best_case_tier: string | null;
  best_btl_price: string | null;
  tier: string | null;
  rip_price: string | null;
  rip_raw: string | null;
  product_code: string | null;
  product_description: string | null;
  product_case_cost: string | null;
  product_btl_cost: string | null;
  match_confidence: string | null;
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
    division?: string[];
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
  facets: (distributor = "nj-allied") =>
    api<Facets>(`/api/v1/catalog/facets${_qs({ distributor })}`),
};

export const insightsApi = {
  summary: (distributor = "nj-allied") =>
    api<DashboardSummary>(`/api/v1/dashboard/summary${_qs({ distributor })}`),
  rips: (params: {
    distributor?: string;
    category?: string[];
    min_pct?: number;
    tier_cases_max?: number;
    limit?: number;
  } = {}) => api<RipRow[]>(`/api/v1/rips${_qs(params)}`),
  closeouts: (params: { distributor?: string; min_pct?: number; limit?: number } = {}) =>
    api<CloseoutRow[]>(`/api/v1/closeouts${_qs(params)}`),
  combos: (params: { distributor?: string; subcategory?: string; search?: string; limit?: number } = {}) =>
    api<ComboRow[]>(`/api/v1/combos${_qs(params)}`),
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
  order: (params: { search?: string; category?: string; sort?: string; distributor?: string } = {}) =>
    api<OrderItem[]>(`/api/v1/watchlist/order${_qs(params)}`),
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

export const specialsApi = {
  active: (distributor = "nj-allied") =>
    api<WebSpecial[]>(`/api/v1/specials${_qs({ distributor })}`),
};

// ---------- Orders (named orders with division + payment analysis) ----------

export type OrderSummary = {
  id: string;
  name: string;
  division: string | null;
  status: string;
  order_notes: string | null;
  item_count: number;
  total_cases: number;
  total_bottles: number;
  invoice_total: string | null;
  rip_rebate_total: string | null;
  effective_total: string | null;
  created_at: string;
  updated_at: string;
  submitted_at: string | null;
  hidden_at: string | null;
};

export type OrderRipTier = {
  tier: string;
  tier_cases: number;
  save_amount: string;
  case_price: string | null;
  btl_price: string | null;
};

export type OrderRecommendation = {
  type: string;
  message: string;
  priority: string;
};

export type OrderLine = {
  product_code: string;
  description: string | null;
  size: string | null;
  pack: number | null;
  category_slug: string | null;
  category_display: string | null;
  brand_slug: string | null;
  brand_display: string | null;
  divisions: string | null;
  case_cost: string | null;
  btl_cost: string | null;
  qty_cases: number;
  qty_bottles: number;
  selected_rip_tier: string | null;
  notes: string | null;
  has_rip: boolean;
  rip_tiers: OrderRipTier[];
  best_rip_save: string | null;
  line_invoice: string | null;
  line_rip_rebate: string | null;
  line_effective: string | null;
  recommendations: OrderRecommendation[];
  is_closeout: boolean;
};

export type PaymentCategoryBreakdown = {
  category: string;
  invoice: string;
  rebate: string;
  effective: string;
  item_count: number;
};

export type PaymentAnalysis = {
  invoice_total: string;
  rip_rebate_total: string;
  effective_total: string;
  rip_pct_of_order: string | null;
  by_category: PaymentCategoryBreakdown[];
};

export type OrderDetail = {
  id: string;
  name: string;
  division: string | null;
  status: string;
  order_notes: string | null;
  created_at: string;
  updated_at: string;
  submitted_at: string | null;
  items: OrderLine[];
  payment: PaymentAnalysis;
  recommendations: OrderRecommendation[];
};

export const ordersApi = {
  list: (params: { status?: string; division?: string; include_hidden?: boolean } = {}) =>
    api<OrderSummary[]>(`/api/v1/orders${_qs(params)}`),
  create: (body: { name: string; division?: string; order_notes?: string }) =>
    api<OrderSummary>("/api/v1/orders", { method: "POST", json: body }),
  get: (id: string) => api<OrderDetail>(`/api/v1/orders/${id}`),
  update: (id: string, body: { name?: string; division?: string; status?: string; order_notes?: string }) =>
    api<OrderSummary>(`/api/v1/orders/${id}`, { method: "PATCH", json: body }),
  remove: (id: string) => api<void>(`/api/v1/orders/${id}`, { method: "DELETE" }),
  addItem: (id: string, body: { code: string; qty_cases?: number; qty_bottles?: number; selected_rip_tier?: string; notes?: string }) =>
    api<{ status: string }>(`/api/v1/orders/${id}/items`, { method: "POST", json: body }),
  updateItem: (id: string, code: string, body: { qty_cases?: number; qty_bottles?: number; selected_rip_tier?: string; notes?: string }) =>
    api<{ status: string }>(`/api/v1/orders/${id}/items/${code}`, { method: "PATCH", json: body }),
  removeItem: (id: string, code: string) =>
    api<void>(`/api/v1/orders/${id}/items/${code}`, { method: "DELETE" }),
  copyFromWatchlist: (id: string) =>
    api<{ added: number }>(`/api/v1/orders/${id}/copy-from-watchlist`, { method: "POST" }),
  submit: (id: string) =>
    api<{ status: string }>(`/api/v1/orders/${id}/submit`, { method: "POST" }),
  hide: (id: string) =>
    api<OrderSummary>(`/api/v1/orders/${id}/hide`, { method: "POST" }),
  unhide: (id: string) =>
    api<OrderSummary>(`/api/v1/orders/${id}/unhide`, { method: "POST" }),
  exportUrl: (id: string, format = "xlsx", division?: string) =>
    `${API_BASE}/api/v1/orders/${id}/export${_qs({ format, division })}`,
};

// ---------- Pricing Analytics ----------

export type AnalyticsRow = {
  code: string;
  description: string | null;
  size: string | null;
  brand: string | null;
  category: string | null;
  divisions: string | null;
  case_cost: string | null;
  prev_case_cost: string | null;
  pct_change: number | null;
  rip_save: string | null;
  effective_cost: string | null;
  rip_tier: string | null;
  is_closeout: boolean;
  closeout_pct_off: number | null;
  tag: string | null;
};

export type CategoryTrendRow = {
  category: string;
  product_count: number;
  avg_case_cost: string;
  prev_avg_case_cost: string;
  avg_change: string;
  avg_pct_change: number;
  drops: number;
  increases: number;
};

export type AnalyticsResponse = {
  view: string;
  edition_current: string;
  edition_previous: string | null;
  total: number;
  rows: AnalyticsRow[];
  category_rows: CategoryTrendRow[];
};

export type AnalyticsView =
  | "price_drops"
  | "price_increases"
  | "new_rips"
  | "lost_rips"
  | "best_value"
  | "closeout_rip"
  | "category_trends"
  | "new_products"
  | "discontinued"
  | "watchlist_movers";

export const analyticsApi = {
  query: (view: AnalyticsView, limit = 100, distributor = "nj-allied") =>
    api<AnalyticsResponse>(`/api/v1/analytics${_qs({ view, limit, distributor })}`),
};

// ---------- Price History ----------

export type PriceDataPoint = {
  edition_label: string;
  year: number;
  month: number;
  case_cost: number | null;
  btl_cost: number | null;
  best_rip_save: number | null;
  effective_cost: number | null;
  has_rip: boolean;
  has_closeout: boolean;
};

export type PriceHistorySummary = {
  min_case_cost: number | null;
  max_case_cost: number | null;
  avg_case_cost: number | null;
  current_case_cost: number | null;
  total_editions: number;
  price_trend: "rising" | "falling" | "stable";
};

export type PriceHistoryResponse = {
  code: string;
  description: string;
  brand: string | null;
  data_points: PriceDataPoint[];
  summary: PriceHistorySummary;
};

export const priceHistoryApi = {
  get: (code: string, distributor = "nj-allied") =>
    api<PriceHistoryResponse>(`/api/v1/catalog/${code}/price-history${_qs({ distributor })}`),
};

// ---------- Sales Reps ----------

export type SalesRepOut = {
  id: string;
  name: string;
  email: string;
  phone: string | null;
  division: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

export type EmailData = {
  to: string;
  subject: string;
  body: string;
};

export const salesRepsApi = {
  list: (division?: string) =>
    api<SalesRepOut[]>(`/api/v1/sales-reps${_qs({ division })}`),
  create: (body: { name: string; email: string; phone?: string; division?: string; notes?: string }) =>
    api<SalesRepOut>("/api/v1/sales-reps", { method: "POST", json: body }),
  update: (id: string, body: { name?: string; email?: string; phone?: string; division?: string; notes?: string }) =>
    api<SalesRepOut>(`/api/v1/sales-reps/${id}`, { method: "PATCH", json: body }),
  remove: (id: string) =>
    api<void>(`/api/v1/sales-reps/${id}`, { method: "DELETE" }),
  generateEmail: (orderId: string, repId?: string) =>
    api<EmailData>(`/api/v1/orders/${orderId}/email${_qs({ rep_id: repId })}`),
};
