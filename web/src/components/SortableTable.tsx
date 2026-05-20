import { useState, useCallback } from "react";

export type SortDirection = "asc" | "desc";
export type SortConfig = { key: string; direction: SortDirection } | null;

export type Column<T> = {
  key: string;
  label: string;
  sortable?: boolean;
  align?: "left" | "right" | "center";
  className?: string;
  thClassName?: string;
  render: (item: T, index: number) => React.ReactNode;
  sortValue?: (item: T) => string | number | null;
};

function SortArrow({ direction }: { direction: SortDirection | null }) {
  if (!direction) {
    return (
      <svg className="ml-1 inline h-3 w-3 text-zinc-300" viewBox="0 0 12 12" fill="currentColor">
        <path d="M6 1.5l3 3.5H3l3-3.5zM6 10.5l-3-3.5h6l-3 3.5z" />
      </svg>
    );
  }
  return (
    <svg className="ml-1 inline h-3 w-3 text-zinc-700" viewBox="0 0 12 12" fill="currentColor">
      {direction === "asc" ? (
        <path d="M6 2l4 5H2l4-5z" />
      ) : (
        <path d="M6 10L2 5h8l-4 5z" />
      )}
    </svg>
  );
}

export function useSort<T>(defaultSort: SortConfig = null) {
  const [sort, setSort] = useState<SortConfig>(defaultSort);

  const toggle = useCallback(
    (key: string) => {
      setSort((prev) => {
        if (prev?.key !== key) return { key, direction: "asc" };
        if (prev.direction === "asc") return { key, direction: "desc" };
        return null;
      });
    },
    [],
  );

  const sorted = useCallback(
    (data: T[], columns: Column<T>[]): T[] => {
      if (!sort) return data;
      const col = columns.find((c) => c.key === sort.key);
      if (!col?.sortValue) return data;
      const dir = sort.direction === "asc" ? 1 : -1;
      return [...data].sort((a, b) => {
        const va = col.sortValue!(a);
        const vb = col.sortValue!(b);
        if (va == null && vb == null) return 0;
        if (va == null) return 1;
        if (vb == null) return -1;
        if (typeof va === "number" && typeof vb === "number") return (va - vb) * dir;
        return String(va).localeCompare(String(vb)) * dir;
      });
    },
    [sort],
  );

  return { sort, toggle, sorted };
}

export function SortableHeader<T>({
  column,
  sort,
  onSort,
}: {
  column: Column<T>;
  sort: SortConfig;
  onSort: (key: string) => void;
}) {
  const active = sort?.key === column.key;
  const dir = active ? sort!.direction : null;
  const align = column.align ?? "left";
  const textAlign = align === "right" ? "text-right" : align === "center" ? "text-center" : "text-left";

  if (!column.sortable) {
    return (
      <th className={`px-4 py-2 text-[10px] uppercase tracking-wide text-zinc-500 font-medium ${textAlign} ${column.thClassName ?? ""}`}>
        {column.label}
      </th>
    );
  }

  return (
    <th
      className={`px-4 py-2 text-[10px] uppercase tracking-wide font-medium cursor-pointer select-none group ${textAlign} ${
        active ? "text-zinc-900" : "text-zinc-500 hover:text-zinc-700"
      } ${column.thClassName ?? ""}`}
      onClick={() => onSort(column.key)}
    >
      {column.label}
      <SortArrow direction={dir} />
    </th>
  );
}

export default function SortableTable<T>({
  columns,
  data,
  sort,
  onSort,
  rowKey,
  emptyMessage = "No items.",
  className = "",
  onRowClick,
}: {
  columns: Column<T>[];
  data: T[];
  sort: SortConfig;
  onSort: (key: string) => void;
  rowKey: (item: T, index: number) => string;
  emptyMessage?: string;
  className?: string;
  onRowClick?: (item: T) => void;
}) {
  if (data.length === 0) {
    return <div className="text-center py-12 text-zinc-500">{emptyMessage}</div>;
  }

  return (
    <div className={`overflow-x-auto ${className}`}>
      <table className="min-w-full divide-y divide-zinc-200 text-sm">
        <thead className="bg-zinc-50/80">
          <tr>
            {columns.map((col) => (
              <SortableHeader key={col.key} column={col} sort={sort} onSort={onSort} />
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-100 bg-white">
          {data.map((item, i) => (
            <tr
              key={rowKey(item, i)}
              className={`hover:bg-zinc-50 ${onRowClick ? "cursor-pointer" : ""}`}
              onClick={onRowClick ? () => onRowClick(item) : undefined}
            >
              {columns.map((col) => (
                <td
                  key={col.key}
                  className={`px-4 py-2.5 ${
                    col.align === "right" ? "text-right" : col.align === "center" ? "text-center" : ""
                  } ${col.className ?? ""}`}
                >
                  {col.render(item, i)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
