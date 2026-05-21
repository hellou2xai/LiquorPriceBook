import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { decisionsApi } from "../lib/api";

type Props = {
  code: string;
  distributor?: string;
  /** Compact mode: just icons + counts, no labels */
  compact?: boolean;
};

export default function RipRating({ code, distributor = "nj-allied", compact = false }: Props) {
  const qc = useQueryClient();

  const { data } = useQuery({
    queryKey: ["rip-rating", code, distributor],
    queryFn: () => decisionsApi.getRating(code, distributor),
    staleTime: 60_000,
    retry: false,
  });

  const rate = useMutation({
    mutationFn: (rating: number) =>
      decisionsApi.rateRip({ product_code: code, distributor, rating }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["rip-rating", code, distributor] });
      qc.invalidateQueries({ queryKey: ["rip-ratings-bulk"] });
    },
  });

  const remove = useMutation({
    mutationFn: () => decisionsApi.deleteRating(code, distributor),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["rip-rating", code, distributor] });
      qc.invalidateQueries({ queryKey: ["rip-ratings-bulk"] });
    },
  });

  if (!data) return null;

  const handleClick = (val: number) => {
    if (data.my_rating === val) {
      remove.mutate(); // Toggle off
    } else {
      rate.mutate(val);
    }
  };

  const total = data.thumbs_up + data.thumbs_down;
  const isUp = data.my_rating === 1;
  const isDown = data.my_rating === -1;

  if (compact) {
    return (
      <span className="inline-flex items-center gap-1.5">
        <button
          onClick={(e) => { e.stopPropagation(); e.preventDefault(); handleClick(1); }}
          disabled={rate.isPending || remove.isPending}
          className={`inline-flex items-center gap-0.5 rounded px-1 py-0.5 text-xs transition-colors ${
            isUp
              ? "bg-emerald-100 text-emerald-700 border border-emerald-300"
              : "text-zinc-400 hover:text-emerald-600 hover:bg-emerald-50"
          }`}
          title="Good RIP deal"
        >
          <svg className="w-3 h-3" viewBox="0 0 20 20" fill="currentColor">
            <path d="M2 10.5a1.5 1.5 0 113 0v6a1.5 1.5 0 01-3 0v-6zM6 10.333v5.43a2 2 0 001.106 1.79l.05.025A4 4 0 008.943 18h5.416a2 2 0 001.962-1.608l1.2-6A2 2 0 0015.56 8H12V4a2 2 0 00-2-2 1 1 0 00-1 1v.667a4 4 0 01-.8 2.4L6.8 7.933a4 4 0 00-.8 2.4z" />
          </svg>
          {data.thumbs_up > 0 && <span>{data.thumbs_up}</span>}
        </button>
        <button
          onClick={(e) => { e.stopPropagation(); e.preventDefault(); handleClick(-1); }}
          disabled={rate.isPending || remove.isPending}
          className={`inline-flex items-center gap-0.5 rounded px-1 py-0.5 text-xs transition-colors ${
            isDown
              ? "bg-red-100 text-red-700 border border-red-300"
              : "text-zinc-400 hover:text-red-600 hover:bg-red-50"
          }`}
          title="Bad RIP deal"
        >
          <svg className="w-3 h-3 rotate-180" viewBox="0 0 20 20" fill="currentColor">
            <path d="M2 10.5a1.5 1.5 0 113 0v6a1.5 1.5 0 01-3 0v-6zM6 10.333v5.43a2 2 0 001.106 1.79l.05.025A4 4 0 008.943 18h5.416a2 2 0 001.962-1.608l1.2-6A2 2 0 0015.56 8H12V4a2 2 0 00-2-2 1 1 0 00-1 1v.667a4 4 0 01-.8 2.4L6.8 7.933a4 4 0 00-.8 2.4z" />
          </svg>
          {data.thumbs_down > 0 && <span>{data.thumbs_down}</span>}
        </button>
        {total > 0 && (
          <span className={`text-[10px] font-medium ${data.score >= 60 ? "text-emerald-600" : data.score >= 40 ? "text-zinc-500" : "text-red-500"}`}>
            {data.score}%
          </span>
        )}
      </span>
    );
  }

  return (
    <div className="flex items-center gap-3">
      <div className="flex items-center gap-1">
        <button
          onClick={() => handleClick(1)}
          disabled={rate.isPending || remove.isPending}
          className={`flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-sm font-medium transition-all ${
            isUp
              ? "bg-emerald-100 text-emerald-800 border border-emerald-300 shadow-sm"
              : "border border-zinc-200 text-zinc-500 hover:text-emerald-600 hover:border-emerald-300 hover:bg-emerald-50"
          }`}
        >
          <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor">
            <path d="M2 10.5a1.5 1.5 0 113 0v6a1.5 1.5 0 01-3 0v-6zM6 10.333v5.43a2 2 0 001.106 1.79l.05.025A4 4 0 008.943 18h5.416a2 2 0 001.962-1.608l1.2-6A2 2 0 0015.56 8H12V4a2 2 0 00-2-2 1 1 0 00-1 1v.667a4 4 0 01-.8 2.4L6.8 7.933a4 4 0 00-.8 2.4z" />
          </svg>
          {data.thumbs_up}
        </button>
        <button
          onClick={() => handleClick(-1)}
          disabled={rate.isPending || remove.isPending}
          className={`flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-sm font-medium transition-all ${
            isDown
              ? "bg-red-100 text-red-800 border border-red-300 shadow-sm"
              : "border border-zinc-200 text-zinc-500 hover:text-red-600 hover:border-red-300 hover:bg-red-50"
          }`}
        >
          <svg className="w-4 h-4 rotate-180" viewBox="0 0 20 20" fill="currentColor">
            <path d="M2 10.5a1.5 1.5 0 113 0v6a1.5 1.5 0 01-3 0v-6zM6 10.333v5.43a2 2 0 001.106 1.79l.05.025A4 4 0 008.943 18h5.416a2 2 0 001.962-1.608l1.2-6A2 2 0 0015.56 8H12V4a2 2 0 00-2-2 1 1 0 00-1 1v.667a4 4 0 01-.8 2.4L6.8 7.933a4 4 0 00-.8 2.4z" />
          </svg>
          {data.thumbs_down}
        </button>
      </div>
      {total > 0 && (
        <div className="flex items-center gap-1.5">
          <div className="w-16 h-2 rounded-full bg-zinc-200 overflow-hidden">
            <div
              className={`h-full rounded-full ${data.score >= 60 ? "bg-emerald-500" : data.score >= 40 ? "bg-amber-400" : "bg-red-400"}`}
              style={{ width: `${data.score}%` }}
            />
          </div>
          <span className={`text-xs font-medium ${data.score >= 60 ? "text-emerald-600" : data.score >= 40 ? "text-zinc-500" : "text-red-500"}`}>
            {data.score}%
          </span>
        </div>
      )}
    </div>
  );
}
