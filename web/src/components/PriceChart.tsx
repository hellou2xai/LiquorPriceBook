import { useState } from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type PriceDataPoint = {
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

type Props = {
  data: PriceDataPoint[];
  height?: number;
};

// ---------------------------------------------------------------------------
// Brand palette
// ---------------------------------------------------------------------------

const NAVY   = "#1B2A4A";
const ORANGE = "#D04A02";
const GOLD   = "#E88D2A";
const TAN    = "#F7F4F0";
const ROSE   = "#D93954";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Round a value UP to the next "nice" increment. */
function niceRound(value: number, step: number): number {
  return Math.ceil(value / step) * step;
}

/** Pick a nice tick step for a given range. */
function niceStep(range: number): number {
  const raw = range / 4;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const norm = raw / mag;
  let step: number;
  if (norm <= 1)      step = 1;
  else if (norm <= 2) step = 2;
  else if (norm <= 5) step = 5;
  else                step = 10;
  return step * mag;
}

function fmt(v: number) {
  return "$" + v.toFixed(2);
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function PriceChart({ data, height = 240 }: Props) {
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  // -------------------------------------------------------------------------
  // Empty / insufficient state
  // -------------------------------------------------------------------------
  if (data.length < 2) {
    return (
      <div
        style={{ height }}
        className="flex items-center justify-center rounded-lg bg-[#FAFAF9] border border-zinc-100 text-sm text-zinc-400 select-none"
      >
        Not enough history for chart
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // Layout constants (internal coordinate space)
  // -------------------------------------------------------------------------
  const VIEW_W  = 600;
  const VIEW_H  = height;
  const PAD_L   = 55;
  const PAD_R   = 20;
  const PAD_T   = 20;
  const PAD_B   = 35;
  const PLOT_W  = VIEW_W - PAD_L - PAD_R;
  const PLOT_H  = VIEW_H - PAD_T - PAD_B;

  // -------------------------------------------------------------------------
  // Derived flags
  // -------------------------------------------------------------------------
  const hasRipAny      = data.some(d => d.has_rip);
  const hasCloseoutAny = data.some(d => d.has_closeout);

  // -------------------------------------------------------------------------
  // Y scale: derive min/max from all visible values, add 5% padding
  // -------------------------------------------------------------------------
  const allValues: number[] = [];
  data.forEach(d => {
    if (d.case_cost      != null) allValues.push(d.case_cost);
    if (d.effective_cost != null) allValues.push(d.effective_cost);
  });

  const rawMin = Math.min(...allValues);
  const rawMax = Math.max(...allValues);
  const range  = rawMax - rawMin || 1;
  const pad5   = range * 0.05;

  const step    = niceStep(range + pad5 * 2);
  const yMin    = Math.floor((rawMin - pad5) / step) * step;
  const yMax    = niceRound(rawMax + pad5, step);

  const yRange  = yMax - yMin;

  function toY(v: number): number {
    return PAD_T + PLOT_H - ((v - yMin) / yRange) * PLOT_H;
  }

  // -------------------------------------------------------------------------
  // X scale: evenly spaced by index
  // -------------------------------------------------------------------------
  const n = data.length;

  function toX(i: number): number {
    return PAD_L + (i / (n - 1)) * PLOT_W;
  }

  // -------------------------------------------------------------------------
  // Y-axis tick marks
  // -------------------------------------------------------------------------
  const ticks: number[] = [];
  for (let t = yMin; t <= yMax + 0.001; t += step) {
    ticks.push(parseFloat(t.toFixed(10)));
  }

  // -------------------------------------------------------------------------
  // Build SVG path strings
  // -------------------------------------------------------------------------
  function buildLinePath(
    points: Array<{ x: number; y: number } | null>
  ): string {
    let d = "";
    let penDown = false;
    points.forEach(p => {
      if (p == null) {
        penDown = false;
      } else if (!penDown) {
        d += `M ${p.x},${p.y} `;
        penDown = true;
      } else {
        d += `L ${p.x},${p.y} `;
      }
    });
    return d.trim();
  }

  const casePoints = data.map((d, i) =>
    d.case_cost != null ? { x: toX(i), y: toY(d.case_cost) } : null
  );

  const effPoints = data.map((d, i) =>
    d.effective_cost != null ? { x: toX(i), y: toY(d.effective_cost) } : null
  );

  const casePath = buildLinePath(casePoints);
  const effPath  = buildLinePath(effPoints);

  // Area fill between case_cost and effective_cost (gold RIP savings band)
  // Only draw fill where both values exist and are different
  let fillPath = "";
  if (hasRipAny) {
    // Build top edge (case_cost left-to-right) then bottom edge (effective_cost right-to-left)
    const topPts:    Array<{ x: number; y: number }> = [];
    const bottomPts: Array<{ x: number; y: number }> = [];

    data.forEach((d, i) => {
      if (d.case_cost != null && d.effective_cost != null) {
        topPts.push({ x: toX(i), y: toY(d.case_cost) });
        bottomPts.push({ x: toX(i), y: toY(d.effective_cost) });
      }
    });

    if (topPts.length >= 2) {
      const top    = topPts.map((p, idx) => (idx === 0 ? `M ${p.x},${p.y}` : `L ${p.x},${p.y}`)).join(" ");
      const bottom = [...bottomPts].reverse().map(p => `L ${p.x},${p.y}`).join(" ");
      fillPath = `${top} ${bottom} Z`;
    }
  }

  // -------------------------------------------------------------------------
  // X-axis label visibility: show all if <=6, otherwise every other
  // -------------------------------------------------------------------------
  function showLabel(i: number): boolean {
    if (n <= 6) return true;
    return i % 2 === 0;
  }

  // -------------------------------------------------------------------------
  // Tooltip data for hovered index
  // -------------------------------------------------------------------------
  const hovered = hoveredIdx != null ? data[hoveredIdx] : null;
  const hovX    = hoveredIdx != null ? toX(hoveredIdx) : 0;
  const hovY    = hoveredIdx != null && hovered?.case_cost != null
    ? toY(hovered.case_cost)
    : 0;

  // Tooltip positioning: flip to left if near right edge
  // We'll use fractional position in [0,1] to decide offset direction
  const tooltipRight = hoveredIdx != null && (hoveredIdx / (n - 1)) > 0.6;

  return (
    <div className="relative select-none" style={{ lineHeight: 1 }}>
      {/* ------------------------------------------------------------------ */}
      {/* SVG Chart                                                           */}
      {/* ------------------------------------------------------------------ */}
      <svg
        viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
        width="100%"
        style={{ display: "block", overflow: "visible" }}
        aria-label="Price history chart"
      >
        {/* Background */}
        <rect x={0} y={0} width={VIEW_W} height={VIEW_H} fill="white" rx={6} />

        {/* Plot area background */}
        <rect
          x={PAD_L} y={PAD_T}
          width={PLOT_W} height={PLOT_H}
          fill={TAN}
          opacity={0.35}
          rx={2}
        />

        {/* ---- Grid lines & Y-axis labels ---- */}
        {ticks.map(tick => {
          const y = toY(tick);
          return (
            <g key={tick}>
              <line
                x1={PAD_L} y1={y}
                x2={PAD_L + PLOT_W} y2={y}
                stroke={TAN}
                strokeWidth={1}
              />
              <text
                x={PAD_L - 6}
                y={y}
                textAnchor="end"
                dominantBaseline="middle"
                fontSize={10}
                fill="#8E8E8E"
                fontFamily="ui-sans-serif, system-ui, sans-serif"
              >
                {fmt(tick)}
              </text>
            </g>
          );
        })}

        {/* ---- Vertical grid lines (at each data point) ---- */}
        {data.map((_, i) => (
          <line
            key={i}
            x1={toX(i)} y1={PAD_T}
            x2={toX(i)} y2={PAD_T + PLOT_H}
            stroke={TAN}
            strokeWidth={0.75}
            strokeDasharray="3 3"
          />
        ))}

        {/* ---- RIP savings fill area ---- */}
        {fillPath && (
          <path
            d={fillPath}
            fill={GOLD}
            fillOpacity={0.15}
            stroke="none"
          />
        )}

        {/* ---- Effective cost line (dashed orange) ---- */}
        {hasRipAny && effPath && (
          <path
            d={effPath}
            fill="none"
            stroke={ORANGE}
            strokeWidth={2}
            strokeDasharray="6 3"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        )}

        {/* ---- Case cost line (solid navy) ---- */}
        {casePath && (
          <path
            d={casePath}
            fill="none"
            stroke={NAVY}
            strokeWidth={2.5}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        )}

        {/* ---- Closeout diamond markers ---- */}
        {data.map((d, i) => {
          if (!d.has_closeout || d.case_cost == null) return null;
          const cx = toX(i);
          const cy = toY(d.case_cost);
          const s  = 5;
          return (
            <polygon
              key={`co-${i}`}
              points={`${cx},${cy - s} ${cx + s},${cy} ${cx},${cy + s} ${cx - s},${cy}`}
              fill={ROSE}
              stroke="white"
              strokeWidth={1}
            />
          );
        })}

        {/* ---- Effective cost dots (orange) ---- */}
        {hasRipAny && data.map((d, i) => {
          if (d.effective_cost == null) return null;
          return (
            <circle
              key={`eff-${i}`}
              cx={toX(i)}
              cy={toY(d.effective_cost)}
              r={3.5}
              fill={ORANGE}
              stroke="white"
              strokeWidth={1.5}
            />
          );
        })}

        {/* ---- Case cost dots (navy) — also the hover targets ---- */}
        {data.map((d, i) => {
          if (d.case_cost == null) return null;
          const cx = toX(i);
          const cy = toY(d.case_cost);
          return (
            <g key={`cc-${i}`}>
              {/* Invisible wider hit area */}
              <circle
                cx={cx} cy={cy} r={12}
                fill="transparent"
                onMouseEnter={() => setHoveredIdx(i)}
                onMouseLeave={() => setHoveredIdx(null)}
                style={{ cursor: "crosshair" }}
              />
              {/* Visible dot */}
              <circle
                cx={cx} cy={cy} r={4}
                fill={hoveredIdx === i ? "white" : NAVY}
                stroke={NAVY}
                strokeWidth={hoveredIdx === i ? 2.5 : 0}
                style={{ pointerEvents: "none", transition: "fill 0.15s" }}
              />
            </g>
          );
        })}

        {/* ---- X-axis labels ---- */}
        {data.map((d, i) => {
          if (!showLabel(i)) return null;
          return (
            <text
              key={`xl-${i}`}
              x={toX(i)}
              y={PAD_T + PLOT_H + 14}
              textAnchor="middle"
              fontSize={10}
              fill="#8E8E8E"
              fontFamily="ui-sans-serif, system-ui, sans-serif"
            >
              {d.edition_label}
            </text>
          );
        })}

        {/* ---- Axis border lines ---- */}
        <line
          x1={PAD_L} y1={PAD_T}
          x2={PAD_L} y2={PAD_T + PLOT_H}
          stroke="#D4D4D4"
          strokeWidth={1}
        />
        <line
          x1={PAD_L} y1={PAD_T + PLOT_H}
          x2={PAD_L + PLOT_W} y2={PAD_T + PLOT_H}
          stroke="#D4D4D4"
          strokeWidth={1}
        />
      </svg>

      {/* ------------------------------------------------------------------ */}
      {/* Hover Tooltip (positioned as an overlay div)                        */}
      {/* ------------------------------------------------------------------ */}
      {hovered && hoveredIdx != null && (
        <div
          className="pointer-events-none absolute z-10 rounded-lg border border-zinc-200 bg-white shadow-lg px-3 py-2 text-xs"
          style={{
            top:    `${(hovY / VIEW_H) * 100}%`,
            left:   tooltipRight
              ? `${((hovX - 8) / VIEW_W) * 100}%`
              : `${((hovX + 8) / VIEW_W) * 100}%`,
            transform: tooltipRight
              ? "translate(-100%, -50%)"
              : "translate(0, -50%)",
            transition: "opacity 0.15s",
            minWidth: 130,
          }}
        >
          <p className="font-semibold text-zinc-800 mb-1">{hovered.edition_label}</p>

          {hovered.case_cost != null && (
            <p className="flex justify-between gap-3 text-zinc-600">
              <span>Case Cost</span>
              <span className="font-medium text-zinc-800">{fmt(hovered.case_cost)}</span>
            </p>
          )}

          {hovered.has_rip && hovered.best_rip_save != null && (
            <p className="flex justify-between gap-3 text-[#D04A02]">
              <span>RIP Save</span>
              <span className="font-medium">-{fmt(hovered.best_rip_save)}</span>
            </p>
          )}

          {hovered.effective_cost != null &&
            hovered.effective_cost !== hovered.case_cost && (
            <p className="flex justify-between gap-3 text-zinc-600">
              <span>Effective</span>
              <span className="font-medium text-zinc-800">{fmt(hovered.effective_cost)}</span>
            </p>
          )}

          {hovered.has_closeout && (
            <p className="mt-1">
              <span
                className="inline-block rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide"
                style={{ background: ROSE, color: "white" }}
              >
                Closeout
              </span>
            </p>
          )}
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Legend                                                               */}
      {/* ------------------------------------------------------------------ */}
      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 px-1" style={{ paddingLeft: PAD_L }}>
        {/* Case Cost */}
        <span className="flex items-center gap-1.5 text-xs text-zinc-500">
          <svg width="20" height="10" viewBox="0 0 20 10" aria-hidden>
            <line x1="0" y1="5" x2="20" y2="5" stroke={NAVY} strokeWidth="2.5" strokeLinecap="round" />
            <circle cx="10" cy="5" r="3.5" fill={NAVY} />
          </svg>
          Case Cost
        </span>

        {/* After RIP */}
        {hasRipAny && (
          <span className="flex items-center gap-1.5 text-xs text-zinc-500">
            <svg width="20" height="10" viewBox="0 0 20 10" aria-hidden>
              <line x1="0" y1="5" x2="20" y2="5" stroke={ORANGE} strokeWidth="2" strokeDasharray="5 2.5" strokeLinecap="round" />
              <circle cx="10" cy="5" r="3" fill={ORANGE} />
            </svg>
            After RIP
          </span>
        )}

        {/* Closeout */}
        {hasCloseoutAny && (
          <span className="flex items-center gap-1.5 text-xs text-zinc-500">
            <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden>
              <polygon
                points="6,1 11,6 6,11 1,6"
                fill={ROSE}
              />
            </svg>
            Closeout
          </span>
        )}
      </div>
    </div>
  );
}
