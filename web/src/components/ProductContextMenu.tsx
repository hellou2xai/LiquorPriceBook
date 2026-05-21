import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { watchlistApi, ordersApi } from "../lib/api";

export type ContextMenuTarget = {
  code: string;
  distributor?: string;
  x: number;
  y: number;
};

type Props = {
  target: ContextMenuTarget | null;
  onClose: () => void;
  isFavorite: boolean;
};

export default function ProductContextMenu({ target, onClose, isFavorite }: Props) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const ref = useRef<HTMLDivElement>(null);
  const [showOrders, setShowOrders] = useState(false);

  const draftQ = useQuery({
    queryKey: ["orders", { status: "draft" }],
    queryFn: () => ordersApi.list({ status: "draft" }),
    enabled: !!target,
    staleTime: 30_000,
  });

  const addWatch = useMutation({
    mutationFn: () => watchlistApi.add({ code: target!.code, distributor: target?.distributor }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["watchlist"] });
      onClose();
    },
  });

  const removeWatch = useMutation({
    mutationFn: () => watchlistApi.remove(target!.code, target?.distributor),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["watchlist"] });
      onClose();
    },
  });

  const addToOrder = useMutation({
    mutationFn: (orderId: string) => ordersApi.addItem(orderId, { code: target!.code }),
    onSuccess: () => {
      setShowOrders(false);
      onClose();
    },
  });

  // Close on outside click or Escape
  useEffect(() => {
    if (!target) return;
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    }
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("mousedown", handleClick);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handleClick);
      document.removeEventListener("keydown", handleKey);
    };
  }, [target, onClose]);

  if (!target) return null;

  // Position: keep menu within viewport
  const menuW = 220;
  const menuH = 240;
  const x = target.x + menuW > window.innerWidth ? target.x - menuW : target.x;
  const y = target.y + menuH > window.innerHeight ? target.y - menuH : target.y;

  const distParam = target.distributor ? `?d=${target.distributor}` : "";

  return (
    <div
      ref={ref}
      className="fixed z-[100] min-w-[200px] rounded-lg border border-zinc-200 bg-white shadow-xl py-1 text-sm"
      style={{ left: x, top: y }}
    >
      {/* View Product */}
      <button
        className="w-full text-left px-3 py-2 hover:bg-brand-tan flex items-center gap-2 text-zinc-700"
        onClick={() => { navigate(`/catalog/${target.code}${distParam}`); onClose(); }}
      >
        <svg className="w-4 h-4 text-zinc-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
        </svg>
        View Product
      </button>

      <div className="border-t border-zinc-100 my-1" />

      {/* Watch list toggle */}
      {isFavorite ? (
        <button
          className="w-full text-left px-3 py-2 hover:bg-brand-tan flex items-center gap-2 text-zinc-700"
          onClick={() => removeWatch.mutate()}
          disabled={removeWatch.isPending}
        >
          <svg className="w-4 h-4 text-amber-500" viewBox="0 0 20 20" fill="currentColor">
            <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
          </svg>
          Remove from Watch List
        </button>
      ) : (
        <button
          className="w-full text-left px-3 py-2 hover:bg-brand-tan flex items-center gap-2 text-zinc-700"
          onClick={() => addWatch.mutate()}
          disabled={addWatch.isPending}
        >
          <svg className="w-4 h-4 text-zinc-400" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={1.5}>
            <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
          </svg>
          Add to Watch List
        </button>
      )}

      {/* Add to Order — sub-menu */}
      <div className="relative">
        <button
          className="w-full text-left px-3 py-2 hover:bg-brand-tan flex items-center justify-between text-zinc-700"
          onClick={() => setShowOrders(!showOrders)}
        >
          <span className="flex items-center gap-2">
            <svg className="w-4 h-4 text-zinc-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
            Add to Order
          </span>
          <svg className="w-3 h-3 text-zinc-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
          </svg>
        </button>
        {showOrders && (
          <div className="absolute left-full top-0 ml-1 min-w-[180px] rounded-lg border border-zinc-200 bg-white shadow-xl py-1 z-[101]">
            {draftQ.data && draftQ.data.length > 0 ? (
              draftQ.data.map((o) => (
                <button
                  key={o.id}
                  onClick={() => addToOrder.mutate(o.id)}
                  disabled={addToOrder.isPending}
                  className="w-full text-left px-3 py-2 text-sm hover:bg-brand-tan flex items-center justify-between"
                >
                  <span>{o.name}</span>
                  {o.division && (
                    <span className="text-[10px] font-medium text-zinc-400">{o.division}</span>
                  )}
                </button>
              ))
            ) : (
              <div className="px-3 py-2 text-xs text-zinc-400">No draft orders</div>
            )}
          </div>
        )}
      </div>

      <div className="border-t border-zinc-100 my-1" />

      {/* Copy code */}
      <button
        className="w-full text-left px-3 py-2 hover:bg-brand-tan flex items-center gap-2 text-zinc-700"
        onClick={() => {
          navigator.clipboard.writeText(target.code);
          onClose();
        }}
      >
        <svg className="w-4 h-4 text-zinc-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15.666 3.888A2.25 2.25 0 0013.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 01-.75.75H9.75a.75.75 0 01-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 01-2.25 2.25H6.75A2.25 2.25 0 014.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 011.927-.184" />
        </svg>
        Copy Code
      </button>
    </div>
  );
}

/** Small hook to manage context menu state across pages */
export function useContextMenu() {
  const [target, setTarget] = useState<ContextMenuTarget | null>(null);

  const handleContextMenu = (
    e: React.MouseEvent,
    code: string,
    distributor?: string,
  ) => {
    e.preventDefault();
    e.stopPropagation();
    setTarget({ code, distributor, x: e.clientX, y: e.clientY });
  };

  const close = () => setTarget(null);

  return { target, handleContextMenu, close };
}
