import { useState, useRef, useEffect } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { watchlistApi } from "../lib/api";

type Props = {
  code: string;
  isFavorite: boolean;
  note?: string | null;
  showNote?: boolean;
};

export default function FavoriteButton({ code, isFavorite, note, showNote = false }: Props) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [noteText, setNoteText] = useState("");
  const popRef = useRef<HTMLDivElement>(null);
  const btnRef = useRef<HTMLButtonElement>(null);

  const add = useMutation({
    mutationFn: (notes?: string) => watchlistApi.add({ code, notes: notes || null }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["watchlist"] });
      qc.invalidateQueries({ queryKey: ["watchlist-order"] });
      setOpen(false);
      setNoteText("");
    },
  });
  const remove = useMutation({
    mutationFn: () => watchlistApi.remove(code),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["watchlist"] });
      qc.invalidateQueries({ queryKey: ["watchlist-order"] });
    },
  });
  const busy = add.isPending || remove.isPending;

  // Close popover on outside click
  useEffect(() => {
    if (!open) return;
    function handler(e: MouseEvent) {
      if (
        popRef.current &&
        !popRef.current.contains(e.target as Node) &&
        btnRef.current &&
        !btnRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
        setNoteText("");
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  function handleClick(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (isFavorite) {
      remove.mutate();
    } else {
      setOpen(true);
    }
  }

  return (
    <span className="relative inline-block">
      <button
        ref={btnRef}
        onClick={handleClick}
        disabled={busy}
        className={`text-lg leading-none transition-colors ${isFavorite ? "text-amber-500 hover:text-amber-600" : "text-zinc-300 hover:text-amber-400"} disabled:opacity-50`}
        title={isFavorite ? "Remove from list" : "Add to list"}
      >
        {isFavorite ? "\u2605" : "\u2606"}
      </button>

      {/* Note indicator */}
      {showNote && note && (
        <span className="ml-1 text-xs text-zinc-500 italic truncate max-w-[120px] inline-block align-middle" title={note}>
          {note}
        </span>
      )}

      {/* Add-with-note popover */}
      {open && (
        <div
          ref={popRef}
          className="absolute left-0 top-full mt-1 z-50 w-64 rounded-lg border border-zinc-200 bg-white shadow-lg p-3 space-y-2"
          onClick={(e) => e.stopPropagation()}
        >
          <p className="text-xs font-medium text-zinc-700">Add to Order List</p>
          <textarea
            autoFocus
            value={noteText}
            onChange={(e) => setNoteText(e.target.value)}
            placeholder="Why are you adding this? (optional)"
            rows={2}
            className="w-full rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-xs placeholder:text-zinc-400 focus:border-zinc-900 focus:outline-none resize-none"
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                add.mutate(noteText);
              }
              if (e.key === "Escape") {
                setOpen(false);
                setNoteText("");
              }
            }}
          />
          <div className="flex justify-end gap-2">
            <button
              onClick={() => { setOpen(false); setNoteText(""); }}
              className="rounded px-2 py-1 text-xs text-zinc-500 hover:text-zinc-700"
            >
              Cancel
            </button>
            <button
              onClick={() => add.mutate(noteText)}
              disabled={busy}
              className="rounded bg-zinc-900 px-3 py-1 text-xs text-white hover:bg-zinc-800 disabled:opacity-50"
            >
              {busy ? "Adding…" : "Add"}
            </button>
          </div>
        </div>
      )}
    </span>
  );
}
