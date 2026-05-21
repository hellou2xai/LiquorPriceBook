/** Formatting helpers reused across pages. */

export function money(v: string | number | null | undefined, fallback = "—"): string {
  if (v === null || v === undefined || v === "") return fallback;
  const n = typeof v === "string" ? parseFloat(v) : v;
  if (!Number.isFinite(n)) return fallback;
  return n.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

export function pct(v: string | number | null | undefined, fallback = "—"): string {
  if (v === null || v === undefined || v === "") return fallback;
  const n = typeof v === "string" ? parseFloat(v) : v;
  if (!Number.isFinite(n)) return fallback;
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(1)}%`;
}

export function pctClass(v: string | number | null | undefined): string {
  if (v === null || v === undefined || v === "") return "text-zinc-500";
  const n = typeof v === "string" ? parseFloat(v) : v;
  if (!Number.isFinite(n)) return "text-zinc-500";
  if (n < 0) return "text-emerald-700";
  if (n > 0) return "text-red-700";
  return "text-zinc-500";
}

export function intOrDash(v: number | null | undefined): string {
  return v == null ? "—" : v.toLocaleString();
}

/** Shorten distributor names: "Fedway Associates" → "Fedway", "Allied Beverage Group" → "Allied" */
export function shortDist(name: string | null | undefined): string {
  if (!name) return "—";
  return name.split(/\s+/)[0];
}
