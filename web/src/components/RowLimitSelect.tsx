import { useState } from "react";

const ROW_OPTIONS = [25, 50, 100, 250, 500, 1000] as const;
const DEFAULT_LIMIT = 100;

export function useRowLimit(initial = DEFAULT_LIMIT) {
  const [limit, setLimit] = useState(initial);
  return { limit, setLimit };
}

export default function RowLimitSelect({
  total,
  limit,
  onChange,
}: {
  total: number;
  limit: number;
  onChange: (n: number) => void;
}) {
  return (
    <div className="flex items-center justify-between px-4 py-2 text-xs text-zinc-500 border-t border-zinc-100">
      <span>
        Showing {Math.min(limit, total)} of {total.toLocaleString()}
      </span>
      <div className="flex items-center gap-1.5">
        <label className="text-xs text-zinc-500">Rows</label>
        <select
          value={limit}
          onChange={(e) => onChange(Number(e.target.value))}
          className="rounded border border-zinc-300 bg-white px-1.5 py-1 text-xs focus:border-brand-orange focus:outline-none"
        >
          {ROW_OPTIONS.map((n) => (
            <option key={n} value={n}>{n}</option>
          ))}
        </select>
      </div>
    </div>
  );
}
