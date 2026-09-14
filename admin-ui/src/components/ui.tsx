import { ReactNode } from "react";
import { Sparkline, type Point, type Tone } from "./charts";

/**
 * Period-over-period change. `invert` marks metrics where growth is bad
 * (cost, latency, blocked requests) so the colour still means "good/bad"
 * rather than "up/down".
 */
export function Delta({
  pct,
  invert = false,
  suffix,
}: {
  pct: number | null;
  invert?: boolean;
  suffix?: string;
}) {
  if (pct == null || !Number.isFinite(pct)) return null;
  const flat = Math.abs(pct) < 0.5;
  const good = flat ? null : invert ? pct < 0 : pct > 0;
  const tone = good == null ? "flat" : good ? "good" : "bad";
  return (
    <span className={`delta delta--${tone}`} title={suffix ? `Change ${suffix}` : undefined}>
      <span className="delta-arrow" aria-hidden>
        {flat ? "—" : pct > 0 ? "↑" : "↓"}
      </span>
      {flat ? "flat" : `${Math.abs(pct).toFixed(Math.abs(pct) >= 10 ? 0 : 1)}%`}
    </span>
  );
}

/**
 * The window a figure covers. Gateway counters are reported per day or since
 * start while Langfuse figures follow the range selector, so every card says
 * which one it is rather than leaving the reader to guess.
 */
export type MetricBasis = { kind: "range" | "today" | "lifetime"; label: string };

/**
 * Single metric card for the whole console. `md` is the compact hero row,
 * `lg` the roomier card used in the tab grids.
 */
export function MetricCard({
  label,
  value,
  hint,
  basis,
  delta,
  invertDelta,
  points,
  tone = "accent",
  size = "md",
  active,
  onSelect,
}: {
  label: string;
  value: string;
  hint?: ReactNode;
  basis?: MetricBasis;
  delta?: number | null;
  invertDelta?: boolean;
  points?: Point[];
  tone?: Tone;
  size?: "md" | "lg";
  active?: boolean;
  onSelect?: () => void;
}) {
  const body = (
    <>
      <span className="metric-top">
        <span className="metric-label">{label}</span>
        {basis ? (
          <span
            className={`metric-basis metric-basis--${basis.kind}`}
            title={`Covers: ${basis.label}`}
          >
            {basis.label}
          </span>
        ) : null}
      </span>
      <span className="metric-value">{value}</span>
      {delta !== undefined || hint ? (
        <span className="metric-foot">
          {delta !== undefined ? <Delta pct={delta ?? null} invert={invertDelta} /> : null}
          {hint ? <span className="metric-hint">{hint}</span> : null}
        </span>
      ) : null}
      {points && points.length > 1 ? (
        <span className="metric-spark">
          <Sparkline points={points} tone={tone} height={30} />
        </span>
      ) : null}
    </>
  );

  const className = [
    "metric",
    `metric--${size}`,
    onSelect ? "metric--selectable" : "",
    active ? "is-active" : "",
  ]
    .filter(Boolean)
    .join(" ");

  if (onSelect) {
    return (
      <button type="button" className={className} onClick={onSelect} aria-pressed={active}>
        {body}
      </button>
    );
  }

  return <div className={className}>{body}</div>;
}

export function EmptyState({
  title,
  hint,
  action,
}: {
  title: string;
  hint?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <span className="empty-mark" aria-hidden>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round">
          <path d="M3 17.5 8.5 11l4 4.2L21 6" />
          <path d="M3 21h18" />
        </svg>
      </span>
      <p className="empty-title">{title}</p>
      {hint ? <p className="empty-hint">{hint}</p> : null}
      {action}
    </div>
  );
}

export function Skeleton({ w = "100%", h = 12 }: { w?: string | number; h?: number }) {
  return <span className="skeleton" style={{ width: w, height: h }} aria-hidden />;
}

export function MetricSkeleton({ size = "md" }: { size?: "md" | "lg" }) {
  return (
    <div className={`metric metric--${size} metric--loading`}>
      <Skeleton w="52%" h={9} />
      <Skeleton w="72%" h={22} />
      <Skeleton w="40%" h={9} />
    </div>
  );
}

/** Compact per-service status strip driven by the stack health payload. */
export function ServiceStrip({
  services,
  healthy,
  tracked,
  onOpen,
}: {
  services: Array<{ name: string; status: string; healthy: boolean }>;
  healthy: number;
  tracked: number;
  onOpen?: () => void;
}) {
  const visible = services.filter((s) => s.status !== "not_created");
  if (!visible.length) return null;
  const down = visible.filter((s) => !s.healthy);
  return (
    <div className="svc-strip">
      <div className="svc-strip-head">
        <span className="svc-strip-count">
          <strong>{healthy}</strong>/{tracked}
        </span>
        <span className="svc-strip-label">services up</span>
      </div>
      <div className="svc-list">
        {visible.map((s) => (
          <span
            key={s.name}
            className={`svc ${s.healthy ? "is-up" : "is-down"}`}
            title={`${s.name} — ${s.status}`}
          >
            <span className="svc-dot" aria-hidden />
            {s.name}
          </span>
        ))}
      </div>
      {down.length ? (
        <span className="svc-strip-note">
          {down.length} degraded: {down.map((d) => d.name).join(", ")}
        </span>
      ) : null}
      {onOpen ? (
        <button type="button" className="svc-strip-open" onClick={onOpen}>
          Details
        </button>
      ) : null}
    </div>
  );
}
