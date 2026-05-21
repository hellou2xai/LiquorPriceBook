type Props = {
  active: boolean;
  onChange: (v: boolean) => void;
  count?: number;
};

export default function TrackedOnlyToggle({ active, onChange, count }: Props) {
  return (
    <button
      onClick={() => onChange(!active)}
      className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium border transition-colors ${
        active
          ? "bg-amber-50 border-amber-300 text-amber-800"
          : "border-zinc-300 text-zinc-500 hover:border-amber-300 hover:text-amber-700"
      }`}
    >
      <span className="text-sm leading-none">{active ? "\u2605" : "\u2606"}</span>
      Tracked Only
      {active && count != null && (
        <span className="rounded-full bg-amber-200 text-amber-900 px-1.5 py-0 text-[10px] font-bold">{count}</span>
      )}
    </button>
  );
}
