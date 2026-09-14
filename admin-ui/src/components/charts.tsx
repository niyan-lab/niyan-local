import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";

export type Point = { label: string; value: number };
export type Tone = "accent" | "teal" | "sand" | "plum";

const TONE_VAR: Record<Tone, string> = {
  accent: "var(--accent)",
  teal: "var(--teal)",
  sand: "var(--sand)",
  plum: "var(--plum)",
};

/**
 * Monotone cubic interpolation (Fritsch–Carlson). Chosen over a cardinal
 * spline because it cannot overshoot: a series that touches zero never dips
 * below the baseline, which would read as negative traffic.
 */
function monotonePath(pts: Array<{ x: number; y: number }>): string {
  const n = pts.length;
  if (n === 0) return "";
  if (n === 1) return `M ${pts[0].x} ${pts[0].y}`;

  const dx: number[] = [];
  const slope: number[] = [];
  for (let i = 0; i < n - 1; i += 1) {
    dx[i] = pts[i + 1].x - pts[i].x;
    slope[i] = dx[i] === 0 ? 0 : (pts[i + 1].y - pts[i].y) / dx[i];
  }

  const m: number[] = [slope[0]];
  for (let i = 1; i < n - 1; i += 1) {
    if (slope[i - 1] * slope[i] <= 0) {
      m[i] = 0;
    } else {
      const w1 = 2 * dx[i] + dx[i - 1];
      const w2 = dx[i] + 2 * dx[i - 1];
      m[i] = (w1 + w2) / (w1 / slope[i - 1] + w2 / slope[i]);
    }
  }
  m[n - 1] = slope[n - 2];

  let d = `M ${pts[0].x} ${pts[0].y}`;
  for (let i = 0; i < n - 1; i += 1) {
    const x1 = pts[i].x + dx[i] / 3;
    const y1 = pts[i].y + (m[i] * dx[i]) / 3;
    const x2 = pts[i + 1].x - dx[i] / 3;
    const y2 = pts[i + 1].y - (m[i + 1] * dx[i]) / 3;
    d += ` C ${x1} ${y1}, ${x2} ${y2}, ${pts[i + 1].x} ${pts[i + 1].y}`;
  }
  return d;
}

/** Round an axis ceiling up to a readable 1 / 2 / 2.5 / 5 x 10^n step. */
function niceMax(v: number): number {
  if (!Number.isFinite(v) || v <= 0) return 1;
  const exp = Math.floor(Math.log10(v));
  const base = 10 ** exp;
  const n = v / base;
  const step = n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10;
  return step * base;
}

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width ?? 0;
      setWidth(w);
    });
    ro.observe(el);
    setWidth(el.getBoundingClientRect().width);
    return () => ro.disconnect();
  }, []);
  return [ref, width] as const;
}

/* -------------------------------------------------------------------------- */

export function Sparkline({
  points,
  tone = "accent",
  height = 30,
}: {
  points: Point[];
  tone?: Tone;
  height?: number;
}) {
  const uid = useId().replace(/:/g, "");
  const [ref, width] = useWidth<HTMLDivElement>();
  const color = TONE_VAR[tone];

  const usable = points.filter((p) => Number.isFinite(p.value));
  const ready = width > 0 && usable.length > 1;

  let line = "";
  let area = "";
  if (ready) {
    const max = Math.max(...usable.map((p) => p.value), 0) || 1;
    const pad = 2;
    const h = height - pad * 2;
    const coords = usable.map((p, i) => ({
      x: (i / (usable.length - 1)) * width,
      y: pad + h - (Math.max(0, p.value) / max) * h,
    }));
    line = monotonePath(coords);
    area = `${line} L ${width} ${height} L 0 ${height} Z`;
  }

  return (
    <div className="sparkline" ref={ref} style={{ height }}>
      {ready ? (
        <svg width={width} height={height} aria-hidden>
          <defs>
            <linearGradient id={`sp-${uid}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity="0.24" />
              <stop offset="100%" stopColor={color} stopOpacity="0" />
            </linearGradient>
          </defs>
          <path d={area} fill={`url(#sp-${uid})`} />
          <path
            d={line}
            fill="none"
            stroke={color}
            strokeWidth="1.4"
            strokeLinecap="round"
            strokeLinejoin="round"
            pathLength={1}
            className="spark-line"
          />
        </svg>
      ) : null}
    </div>
  );
}

/* -------------------------------------------------------------------------- */

export function AreaChart({
  points,
  tone = "accent",
  height = 200,
  format = (v: number) => String(v),
  formatTip,
  label = "value",
}: {
  points: Point[];
  tone?: Tone;
  height?: number;
  format?: (v: number) => string;
  formatTip?: (p: Point) => string;
  label?: string;
}) {
  const uid = useId().replace(/:/g, "");
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const color = TONE_VAR[tone];

  const pad = { top: 14, right: 10, bottom: 24, left: 52 };
  const innerW = Math.max(0, width - pad.left - pad.right);
  const innerH = Math.max(0, height - pad.top - pad.bottom);
  const ready = width > 0 && points.length > 0;

  const rawMax = Math.max(...points.map((p) => p.value), 0);
  const max = niceMax(rawMax);
  const single = points.length === 1;

  const coords = points.map((p, i) => ({
    x: pad.left + (single ? innerW / 2 : (i / (points.length - 1)) * innerW),
    y: pad.top + innerH - (Math.max(0, p.value) / max) * innerH,
  }));

  const line = coords.length > 1 ? monotonePath(coords) : "";
  const area =
    coords.length > 1
      ? `${line} L ${coords[coords.length - 1].x} ${pad.top + innerH} L ${coords[0].x} ${
          pad.top + innerH
        } Z`
      : "";

  const ticks = [0, 0.25, 0.5, 0.75, 1];

  function onMove(e: React.MouseEvent<HTMLDivElement>) {
    if (!ready || !points.length) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    if (single) {
      setHover(0);
      return;
    }
    const ratio = (x - pad.left) / (innerW || 1);
    const idx = Math.round(ratio * (points.length - 1));
    setHover(Math.max(0, Math.min(points.length - 1, idx)));
  }

  const active = hover != null ? points[hover] : null;
  const activeCoord = hover != null ? coords[hover] : null;
  const tipLeft = activeCoord ? Math.min(Math.max(activeCoord.x, 70), Math.max(70, width - 70)) : 0;

  return (
    <div
      className="chart"
      ref={ref}
      style={{ height }}
      onMouseMove={onMove}
      onMouseLeave={() => setHover(null)}
    >
      {ready ? (
        <>
          <svg width={width} height={height} role="img" aria-label={`${label} over time`}>
            <defs>
              <linearGradient id={`ar-${uid}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={color} stopOpacity="0.22" />
                <stop offset="100%" stopColor={color} stopOpacity="0.01" />
              </linearGradient>
            </defs>

            {ticks.map((t) => {
              const y = pad.top + innerH - t * innerH;
              return (
                <g key={t}>
                  <line
                    x1={pad.left}
                    x2={width - pad.right}
                    y1={y}
                    y2={y}
                    className={t === 0 ? "chart-axis" : "chart-grid"}
                  />
                  <text x={pad.left - 8} y={y + 3} className="chart-tick" textAnchor="end">
                    {format(max * t)}
                  </text>
                </g>
              );
            })}

            {coords.length > 1 ? (
              <>
                <path d={area} fill={`url(#ar-${uid})`} className="chart-area" />
                <path
                  d={line}
                  fill="none"
                  stroke={color}
                  strokeWidth="1.75"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  pathLength={1}
                  className="chart-line"
                />
              </>
            ) : (
              <circle cx={coords[0].x} cy={coords[0].y} r="3" fill={color} />
            )}

            {activeCoord ? (
              <g className="chart-cursor">
                <line
                  x1={activeCoord.x}
                  x2={activeCoord.x}
                  y1={pad.top}
                  y2={pad.top + innerH}
                  className="chart-crosshair"
                />
                <circle cx={activeCoord.x} cy={activeCoord.y} r="4.5" fill={color} />
                <circle cx={activeCoord.x} cy={activeCoord.y} r="8" fill={color} opacity="0.18" />
              </g>
            ) : null}

            {points.length > 1 ? (
              <>
                <text x={pad.left} y={height - 6} className="chart-tick" textAnchor="start">
                  {points[0].label}
                </text>
                <text x={width - pad.right} y={height - 6} className="chart-tick" textAnchor="end">
                  {points[points.length - 1].label}
                </text>
              </>
            ) : null}
          </svg>

          {active ? (
            <div className="chart-tip" style={{ left: tipLeft }}>
              <span className="chart-tip-date">{active.label}</span>
              <span className="chart-tip-value">
                {formatTip ? formatTip(active) : `${format(active.value)} ${label}`}
              </span>
            </div>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

/** Horizontal ranked bars — replaces the generic share list. */
export function RankedBars({
  rows,
  tone = "accent",
  emptyLabel = "No usage in this range.",
  onSelect,
  selectedId,
}: {
  rows: Array<{ id: string; label: string; sub?: string; value: number; meta: string }>;
  tone?: Tone;
  emptyLabel?: string;
  onSelect?: (id: string) => void;
  selectedId?: string;
}) {
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const id = window.setTimeout(() => setShown(true), 30);
    return () => window.clearTimeout(id);
  }, []);

  if (!rows.length) return <p className="chart-empty">{emptyLabel}</p>;
  const max = Math.max(...rows.map((r) => r.value), 1);

  return (
    <ol className="ranked">
      {rows.map((r, i) => {
        const selected = selectedId === r.id;
        const inner = (
          <>
            <span className="ranked-index">{String(i + 1).padStart(2, "0")}</span>
            <span className="ranked-body">
              <span className="ranked-head">
                <span className="ranked-name" title={r.label}>
                  {r.label}
                </span>
                <span className="ranked-meta">{r.meta}</span>
              </span>
              <span className="ranked-track">
                <span
                  className="ranked-fill"
                  style={{
                    width: shown ? `${(r.value / max) * 100}%` : "0%",
                    background: TONE_VAR[tone],
                    transitionDelay: `${i * 45}ms`,
                  }}
                />
              </span>
              {r.sub ? <span className="ranked-sub">{r.sub}</span> : null}
            </span>
          </>
        );
        return (
          <li className={`ranked-row ${selected ? "is-selected" : ""}`} key={r.id}>
            {onSelect ? (
              <button
                type="button"
                className="ranked-hit"
                onClick={() => onSelect(r.id)}
                aria-pressed={selected}
              >
                {inner}
              </button>
            ) : (
              inner
            )}
          </li>
        );
      })}
    </ol>
  );
}
