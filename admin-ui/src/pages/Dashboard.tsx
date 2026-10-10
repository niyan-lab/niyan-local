import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, GATEWAY_BASE_URL } from "../api/client";
import { PageTurn } from "../components/PageTurn";
import { AreaChart, RankedBars, Sparkline, type Point, type Tone } from "../components/charts";
import {
  Delta,
  EmptyState,
  MetricCard,
  MetricSkeleton,
  ServiceStrip,
  Skeleton,
  type MetricBasis,
} from "../components/ui";
import { serviceLabel } from "../components/StackStatus";

const GATEWAY_ORIGIN = GATEWAY_BASE_URL || "http://127.0.0.1:4000";

type RangeKey = "24h" | "7d" | "30d" | "90d" | "custom";
type DashTab = "overview" | "models" | "cost" | "applications" | "hardware";

type AppRow = {
  id: string;
  requests?: number;
  total_tokens?: number;
  cost_usd?: number | null;
  today_requests?: number;
  today_total_tokens?: number;
  today_cost_usd?: number | null;
  period_requests?: number;
  period_total_tokens?: number;
  period_cost_usd?: number | null;
  daily?: Array<{ date?: string; total_tokens?: number; cost_usd?: number; traces?: number; requests?: number }>;
};

type Resources = {
  generated_at?: string;
  cpu?: { percent?: number | null; count?: number | null; available?: boolean };
  memory?: {
    percent?: number | null;
    used_bytes?: number | null;
    total_bytes?: number | null;
    available?: boolean;
  };
  gpu?: {
    available?: boolean;
    detail?: string;
    devices?: Array<{
      index?: number;
      name?: string;
      utilization_percent?: number;
      memory_used_bytes?: number;
      memory_total_bytes?: number;
      memory_percent?: number;
    }>;
  };
};

type ModelRow = {
  id: string;
  family: string;
  provider?: string;
  deployment?: string;
  enabled: boolean;
  installed: boolean;
  default: boolean;
  today_requests: number;
  requests: number;
  avg_latency_ms: number | null;
  today_avg_latency_ms: number | null;
  today_total_tokens?: number;
  total_tokens?: number;
  today_cost_usd?: number | null;
  cost_usd?: number | null;
  period_requests?: number;
  period_total_tokens?: number;
  period_cost_usd?: number | null;
};

type Dash = {
  generated_at?: string;
  range?: { key?: string; from?: string; to?: string };
  stack?: {
    status?: string;
    healthy_services?: number;
    tracked_services?: number;
    checks?: Record<string, boolean>;
    services?: Array<{ name: string; status: string; healthy: boolean }>;
  };
  traffic?: {
    available?: boolean;
    source?: string;
    error?: string;
    period?: {
      chat_requests?: number;
      total_tokens?: number;
      cost_usd?: number | null;
      label?: string;
    };
    timeseries?: Array<{
      date?: string;
      total_tokens?: number;
      cost_usd?: number;
      traces?: number;
    }>;
    today?: {
      chat_requests?: number;
      embed_requests?: number;
      avg_chat_latency_ms?: number | null;
      avg_embed_latency_ms?: number | null;
      guardrails_blocked?: number;
      total_tokens?: number;
      cost_usd?: number | null;
      date?: string;
    };
    lifetime?: {
      chat_requests?: number;
      embed_requests?: number;
      avg_chat_latency_ms?: number | null;
      avg_embed_latency_ms?: number | null;
      guardrails_blocked?: number;
      total_tokens?: number;
      cost_usd?: number | null;
    };
  };
  models?: ModelRow[];
  comparison?: {
    local?: {
      requests?: number;
      tokens?: number;
      cost_usd?: number | null;
      label?: string;
      api_cost_note?: string;
    };
    proprietary?: {
      requests?: number;
      tokens?: number;
      cost_usd?: number | null;
      label?: string;
      openai?: { requests?: number; tokens?: number; cost_usd?: number | null };
      gemini?: { requests?: number; tokens?: number; cost_usd?: number | null };
      anthropic?: { requests?: number; tokens?: number; cost_usd?: number | null };
    };
    note?: string;
  };
  embeddings?: {
    enabled?: boolean;
    model?: string;
    today_requests?: number;
    requests?: number;
    avg_latency_ms?: number | null;
    today_avg_latency_ms?: number | null;
  };
  vector?: {
    enabled?: boolean;
    provider?: string;
    healthy?: boolean;
    collections?: number;
    total_points?: number;
    collections_detail?: Array<{ name: string; size?: number; points?: number }>;
    detail?: string;
  };
  guardrails?: {
    enabled?: boolean;
    provider?: string;
    today_blocked?: number;
    lifetime_blocked?: number;
  };
  observability?: {
    enabled?: boolean;
    reachable?: boolean;
    keys_configured?: boolean;
    ui_url?: string;
    note?: string;
  };
  resources?: Resources;
  application?: {
    selected?: string;
    items?: AppRow[];
    note?: string;
  };
  enterprise_functions?: {
    items?: AppRow[];
    note?: string;
  };
};

const RANGE_PRESETS: Array<{ key: RangeKey; label: string }> = [
  { key: "24h", label: "24h" },
  { key: "7d", label: "7d" },
  { key: "30d", label: "30d" },
  { key: "90d", label: "90d" },
];

const TABS: Array<{ id: DashTab; label: string; desc: string }> = [
  { id: "overview", label: "Overview", desc: "KPIs & pulse" },
  { id: "models", label: "Models & tokens", desc: "Per-model detail" },
  { id: "cost", label: "Cost & traffic", desc: "Spend & volume" },
  { id: "applications", label: "Applications", desc: "Per project" },
  { id: "hardware", label: "Hardware", desc: "CPU · memory · GPU" },
];

function fmtMs(v: number | null | undefined) {
  if (v == null || Number.isNaN(v)) return "—";
  if (v >= 1000) return `${(v / 1000).toFixed(1)}s`;
  return `${Math.round(v)} ms`;
}

function fmtNum(v: number | null | undefined) {
  if (v == null) return "0";
  return v.toLocaleString();
}

/** Axis-friendly number: 12.4k, 3.1M. Keeps y-labels from wrapping. */
function compactNum(v: number) {
  if (!Number.isFinite(v)) return "0";
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(v >= 10_000 ? 0 : 1)}k`;
  return String(Math.round(v));
}

function fmtUsd(v: number | null | undefined) {
  if (v == null || Number.isNaN(v)) return "—";
  if (v > 0 && v < 0.01) return `$${v.toFixed(4)}`;
  return `$${v.toFixed(2)}`;
}

function fmtBytes(v: number | null | undefined) {
  if (v == null || Number.isNaN(v)) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let n = v;
  let i = 0;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i += 1;
  }
  return `${n.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

function fillClass(pct: number | null | undefined) {
  if (pct == null) return "";
  if (pct >= 90) return "danger";
  if (pct >= 75) return "warn";
  return "";
}

function tokensPerReq(tokens?: number | null, requests?: number | null) {
  if (!tokens || !requests) return null;
  return tokens / requests;
}

function costPer1k(cost?: number | null, tokens?: number | null) {
  if (cost == null || !tokens) return null;
  return (cost / tokens) * 1000;
}

type SeriesRow = { date?: string; total_tokens?: number; cost_usd?: number; traces?: number };
type SeriesKey = "total_tokens" | "cost_usd" | "traces";

function seriesPoints(series: SeriesRow[], key: SeriesKey): Point[] {
  return series.map((s) => ({ label: s.date || "", value: Number(s[key] || 0) }));
}

/**
 * Split the range in half and compare the two halves, so "7d" reports the last
 * ~3.5 days against the ~3.5 before it. Returns null when there is too little
 * data, or when the earlier half is empty (percent change from zero).
 */
function trendPct(series: SeriesRow[], key: SeriesKey): number | null {
  if (series.length < 4) return null;
  const mid = Math.floor(series.length / 2);
  const sum = (rows: SeriesRow[]) => rows.reduce((a, r) => a + Number(r[key] || 0), 0);
  const prev = sum(series.slice(0, mid));
  const curr = sum(series.slice(mid));
  if (prev <= 0) return null;
  return ((curr - prev) / prev) * 100;
}

function halfLabel(series: SeriesRow[]) {
  const half = Math.floor(series.length / 2);
  return half > 0 ? `vs prior ${half}d` : "";
}

function shortDate(iso?: string) {
  if (!iso) return "";
  try {
    return new Date(iso).toISOString().slice(0, 10);
  } catch {
    return iso.slice(0, 10);
  }
}

const BASIS_TODAY: MetricBasis = { kind: "today", label: "today" };
const BASIS_LIFETIME: MetricBasis = { kind: "lifetime", label: "all time" };

/**
 * A model that can't serve traffic is only useful if you can go fix it, so the
 * status cell links to the page that owns the fix: config for disabled models,
 * Providers for a cloud model whose key is missing.
 */
function ModelFix({ row }: { row: ModelTableRow }) {
  if (row.enabled && row.installed) return null;

  const inferencePage = row.isLocal ? "/inference/on-prem" : "/inference/proprietary";
  const { to, label, title } = !row.enabled
    ? { to: inferencePage, label: "enable", title: "Disabled in niyan.yaml" }
    : row.isLocal
      ? { to: "/inference/on-prem", label: "pull", title: "Weights are not on this host yet" }
      : { to: "/inference/proprietary", label: "add key", title: "Provider has no usable API key" };

  return (
    <Link className="cell-fix" to={to} title={title}>
      {label}
    </Link>
  );
}

function relativeAge(ms: number): string {
  const secs = Math.max(0, Math.round(ms / 1000));
  if (secs < 5) return "just now";
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  return `${Math.floor(mins / 60)}h ago`;
}

/**
 * Data refreshes on a timer, so the age of what's on screen has to be visible.
 * Owns its own interval to keep the per-second tick from re-rendering charts.
 */
function FreshnessStamp({ at, busy }: { at: number | null; busy: boolean }) {
  const [, tick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, []);

  if (!at) return null;
  return (
    <span
      className={`freshness ${busy ? "is-busy" : ""}`.trim()}
      title={`Last loaded ${new Date(at).toLocaleString()} · auto-refresh every 30s`}
    >
      <span className="freshness-dot" aria-hidden />
      updated {relativeAge(Date.now() - at)}
    </span>
  );
}

function KpiChip({ label, value }: { label: string; value: string }) {
  return (
    <div className="kpi-chip">
      <div className="kpi-chip-label">{label}</div>
      <div className="kpi-chip-value">{value}</div>
    </div>
  );
}

function ResourceMeter({
  label,
  percent,
  detail,
}: {
  label: string;
  percent: number | null | undefined;
  detail?: string;
}) {
  const pct = percent == null || Number.isNaN(percent) ? null : Math.max(0, Math.min(100, percent));
  return (
    <div className="resource-meter">
      <div className="resource-meter-head">
        <span className="resource-meter-label">{label}</span>
        <span className="resource-meter-value">
          {pct == null ? "—" : `${pct.toFixed(0)}%`}
          {detail ? ` · ${detail}` : ""}
        </span>
      </div>
      <div className="progress-track">
        <div
          className={`progress-fill ${fillClass(pct)}`}
          style={{ width: `${pct ?? 0}%` }}
        />
      </div>
    </div>
  );
}

function ShareList({
  rows,
  tone = "accent",
  emptyLabel,
  onSelect,
  selectedId,
}: {
  rows: Array<{ id: string; label: string; sub?: string; value: number; meta: string }>;
  tone?: Tone;
  emptyLabel?: string;
  onSelect?: (id: string) => void;
  selectedId?: string;
}) {
  return (
    <RankedBars
      rows={rows}
      tone={tone}
      emptyLabel={emptyLabel ?? "No usage in this range."}
      onSelect={onSelect}
      selectedId={selectedId}
    />
  );
}

/**
 * How a project id appears on the dashboard. Known buckets keep a stable
 * spelling; everything else is shown as the client sent it (the gateway
 * lowercases the header, so `Enterprise-Functions` is listed as
 * `enterprise-functions` unless we map it).
 */
function canonicalAppId(id: string): string {
  const key = (id || "").trim().toLowerCase().replace(/_/g, "-");
  if (!key) return "unattributed";
  if (key === "project-xyz") return "enterprise-functions";
  return key === "all" ? "all" : id.trim();
}

function appLabel(id: string): string {
  const key = canonicalAppId(id).toLowerCase();
  if (key === "unattributed") return "Unattributed";
  if (key === "enterprise-functions") return "Enterprise-Functions";
  return id;
}

/** Overview dots follow endpoint probes — the same signal Hardware uses for "up". */
function serviceStrip(stack?: Dash["stack"]): {
  services: Array<{ name: string; status: string; healthy: boolean }>;
  healthy: number;
  tracked: number;
} {
  const checks = stack?.checks || {};
  const checkEntries = Object.entries(checks);
  if (checkEntries.length) {
    const services = checkEntries.map(([name, ok]) => ({
      name: serviceLabel(name),
      status: ok ? "up" : "down",
      healthy: Boolean(ok),
    }));
    return {
      services,
      healthy: services.filter((s) => s.healthy).length,
      tracked: services.length,
    };
  }
  const services = (stack?.services || []).filter((s) => s.status !== "not_created");
  return {
    services,
    healthy: services.filter((s) => s.healthy).length,
    tracked: services.length,
  };
}

type ModelSortKey = "id" | "reqs" | "tokens" | "cost" | "tpr" | "c1k" | "latency";
type SortDir = "asc" | "desc";
type ModelScope = "all" | "local" | "cloud";

type ModelTableRow = {
  id: string;
  sub: string;
  provider: string;
  enabled: boolean;
  installed: boolean;
  isDefault: boolean;
  isLocal: boolean;
  kind: "chat" | "embed";
  reqs: number;
  tokens: number;
  cost: number | null;
  tpr: number | null;
  c1k: number | null;
  latency: number | null;
};

/** Nulls sort last in both directions — "no data" is never a ranking. */
function compareRows(a: ModelTableRow, b: ModelTableRow, key: ModelSortKey, dir: SortDir): number {
  const sign = dir === "asc" ? 1 : -1;
  if (key === "id") return a.id.localeCompare(b.id) * sign;
  const av = a[key];
  const bv = b[key];
  if (av == null && bv == null) return 0;
  if (av == null) return 1;
  if (bv == null) return -1;
  return (av - bv) * sign;
}

function SortHeader({
  label,
  sortKey,
  active,
  dir,
  onSort,
  align = "left",
}: {
  label: string;
  sortKey: ModelSortKey;
  active: boolean;
  dir: SortDir;
  onSort: (key: ModelSortKey) => void;
  align?: "left" | "right";
}) {
  return (
    <th className={align === "right" ? "th-right" : undefined} aria-sort={active ? (dir === "asc" ? "ascending" : "descending") : "none"}>
      <button
        type="button"
        className={`th-sort ${active ? "is-active" : ""}`}
        onClick={() => onSort(sortKey)}
        title={`Sort by ${label}`}
      >
        {label}
        <span className="th-caret" aria-hidden>
          {active ? (dir === "asc" ? "↑" : "↓") : "↕"}
        </span>
      </button>
    </th>
  );
}

export default function Dashboard() {
  const [data, setData] = useState<Dash | null>(null);
  const [resources, setResources] = useState<Resources | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastLoaded, setLastLoaded] = useState<number | null>(null);
  const [heroKey, setHeroKey] = useState<SeriesKey>("total_tokens");
  const [modelSort, setModelSort] = useState<{ key: ModelSortKey; dir: SortDir }>({
    key: "tokens",
    dir: "desc",
  });
  const [modelScope, setModelScope] = useState<ModelScope>("all");
  const [modelQuery, setModelQuery] = useState("");
  // Tab, range and application filter live in the query string so a view can be
  // bookmarked or pasted to someone else. Defaults are left out to keep the URL
  // readable, and updates replace rather than stack history entries.
  const [searchParams, setSearchParams] = useSearchParams();

  const setParams = useCallback(
    (patch: Record<string, string | null>) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          for (const [key, value] of Object.entries(patch)) {
            if (value) next.set(key, value);
            else next.delete(key);
          }
          return next;
        },
        { replace: true }
      );
    },
    [setSearchParams]
  );

  const tabParam = searchParams.get("tab");
  const tab: DashTab = TABS.some((t) => t.id === tabParam) ? (tabParam as DashTab) : "overview";
  const rangeParam = searchParams.get("range");
  const rangeKey: RangeKey =
    rangeParam === "custom" || RANGE_PRESETS.some((p) => p.key === rangeParam)
      ? (rangeParam as RangeKey)
      : "7d";
  const appParam = searchParams.get("app") || "all";
  const appFilter = canonicalAppId(appParam);
  const customFrom = searchParams.get("from") || "";
  const customTo = searchParams.get("to") || "";

  const setTab = useCallback(
    (id: DashTab) => setParams({ tab: id === "overview" ? null : id }),
    [setParams]
  );
  const setRangeKey = useCallback(
    (key: RangeKey) => setParams({ range: key === "7d" ? null : key }),
    [setParams]
  );
  const setAppFilter = useCallback(
    (id: string) => setParams({ app: id === "all" ? null : id }),
    [setParams]
  );
  const setCustomFrom = useCallback((v: string) => setParams({ from: v || null }), [setParams]);
  const setCustomTo = useCallback((v: string) => setParams({ to: v || null }), [setParams]);

  const prevTabIdx = useRef(0);
  const tabIdx = TABS.findIndex((t) => t.id === tab);
  const tabDirection: 1 | -1 = tabIdx >= prevTabIdx.current ? 1 : -1;
  useEffect(() => {
    prevTabIdx.current = tabIdx;
  }, [tabIdx]);

  const refresh = useCallback(async () => {
    setError("");
    setRefreshing(true);
    try {
      const opts =
        rangeKey === "custom" && customFrom
          ? { from: customFrom, to: customTo || undefined, application: appFilter }
          : { range: rangeKey === "custom" ? "7d" : rangeKey, application: appFilter };
      const d = await api.dashboard(opts);
      setData(d as Dash);
      if ((d as Dash).resources) setResources((d as Dash).resources || null);
      setLastLoaded(Date.now());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [rangeKey, customFrom, customTo, appFilter]);

  const refreshResources = useCallback(async () => {
    try {
      const r = await api.dashboardResources();
      setResources(r);
    } catch {
      /* keep last snapshot */
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    refresh();
    const id = setInterval(refresh, 30000);
    return () => clearInterval(id);
  }, [refresh]);

  useEffect(() => {
    refreshResources();
    const id = setInterval(refreshResources, 3000);
    return () => clearInterval(id);
  }, [refreshResources]);

  const period = data?.traffic?.period;
  const today = data?.traffic?.today;
  const life = data?.traffic?.lifetime;
  const emb = data?.embeddings;
  const cmp = data?.comparison;
  const series = data?.traffic?.timeseries || [];
  const models = data?.models || [];
  const blockedToday = data?.guardrails?.today_blocked ?? today?.guardrails_blocked ?? 0;
  const blockedLife = data?.guardrails?.lifetime_blocked ?? life?.guardrails_blocked ?? 0;
  const lfOk = data?.traffic?.source === "langfuse";
  const rangeLabel =
    data?.range?.key === "custom"
      ? `${shortDate(data?.range?.from)} → ${shortDate(data?.range?.to)}`
      : data?.range?.key || rangeKey;
  const gpuDevices = resources?.gpu?.devices || [];
  const basisRange: MetricBasis = { kind: "range", label: rangeLabel };
  // Latency falls back to the all-time average until the day has any traffic,
  // so the tag has to follow whichever value we actually rendered.
  const chatLatency = today?.avg_chat_latency_ms ?? life?.avg_chat_latency_ms;
  const chatLatencyBasis =
    today?.avg_chat_latency_ms != null ? BASIS_TODAY : BASIS_LIFETIME;
  const rawAppItems = data?.application?.items;
  const appItems = useMemo(() => {
    const merged = new Map<string, AppRow>();
    for (const raw of rawAppItems || []) {
      const id = canonicalAppId(raw.id);
      const prev = merged.get(id);
      if (!prev) {
        merged.set(id, { ...raw, id });
        continue;
      }
      merged.set(id, {
        ...prev,
        requests: (prev.requests ?? 0) + (raw.requests ?? 0),
        total_tokens: (prev.total_tokens ?? 0) + (raw.total_tokens ?? 0),
        cost_usd: (prev.cost_usd ?? 0) + (raw.cost_usd ?? 0),
        today_requests: (prev.today_requests ?? 0) + (raw.today_requests ?? 0),
        today_total_tokens: (prev.today_total_tokens ?? 0) + (raw.today_total_tokens ?? 0),
        today_cost_usd: (prev.today_cost_usd ?? 0) + (raw.today_cost_usd ?? 0),
        period_requests: (prev.period_requests ?? 0) + (raw.period_requests ?? 0),
        period_total_tokens: (prev.period_total_tokens ?? 0) + (raw.period_total_tokens ?? 0),
        period_cost_usd: (prev.period_cost_usd ?? 0) + (raw.period_cost_usd ?? 0),
        daily: [...(prev.daily || []), ...(raw.daily || [])],
      });
    }
    return [...merged.values()];
  }, [rawAppItems]);
  const selectedApp = canonicalAppId(data?.application?.selected || appFilter);
  const functionItems = data?.enterprise_functions?.items || [];

  const functionShares = useMemo(() => {
    const rows = functionItems.map((a) => ({
      id: a.id,
      tokens: a.period_total_tokens ?? a.total_tokens ?? 0,
      reqs: a.period_requests ?? a.requests ?? 0,
      cost: a.period_cost_usd ?? a.cost_usd,
    }));
    const total = rows.reduce((sum, r) => sum + r.tokens, 0);
    const ranked = rows
      .filter((r) => r.tokens > 0)
      .sort((a, b) => b.tokens - a.tokens)
      .map((r) => ({ ...r, pct: total > 0 ? (r.tokens / total) * 100 : 0 }));
    const top = ranked.slice(0, 5);
    return {
      total,
      ranked,
      top,
      topPct: top.reduce((sum, r) => sum + r.pct, 0),
      rest: Math.max(0, ranked.length - top.length),
    };
  }, [functionItems]);

  const avgTokPerReq = tokensPerReq(period?.total_tokens, period?.chat_requests);
  const avgCostPer1k = costPer1k(period?.cost_usd, period?.total_tokens);
  const totalSeriesTokens = series.reduce((a, s) => a + (s.total_tokens || 0), 0);
  const totalSeriesTraces = series.reduce((a, s) => a + (s.traces || 0), 0);
  const totalSeriesCost = series.reduce((a, s) => a + (s.cost_usd || 0), 0);

  const modelShares = useMemo(() => {
    return [...models]
      .map((m) => {
        const tokens = m.period_total_tokens ?? m.today_total_tokens ?? 0;
        const reqs = m.period_requests ?? m.today_requests ?? 0;
        const cost = m.period_cost_usd ?? m.today_cost_usd;
        return {
          id: m.id,
          label: m.id,
          sub: `${m.provider || "ollama"}${m.default ? " · default" : ""}`,
          value: tokens,
          meta: `${fmtNum(tokens)} tok · ${fmtNum(reqs)} req${
            m.provider === "ollama" ? "" : ` · ${fmtUsd(cost)}`
          }`,
        };
      })
      .filter((r) => r.value > 0)
      .sort((a, b) => b.value - a.value);
  }, [models]);

  const heroMetrics: Array<{
    key: SeriesKey;
    label: string;
    value: string;
    total: string;
    tone: Tone;
    invert?: boolean;
    format: (v: number) => string;
    tip: (p: Point) => string;
  }> = [
    {
      key: "total_tokens",
      label: "Tokens",
      value: fmtNum(period?.total_tokens),
      total: `${fmtNum(totalSeriesTokens)} total`,
      tone: "accent",
      format: compactNum,
      tip: (p) => `${fmtNum(p.value)} tokens`,
    },
    {
      key: "cost_usd",
      label: "Proprietary cost",
      value: fmtUsd(period?.cost_usd),
      total: `${fmtUsd(totalSeriesCost)} total`,
      tone: "sand",
      invert: true,
      format: (v) => fmtUsd(v),
      tip: (p) => fmtUsd(p.value),
    },
    {
      key: "traces",
      label: "Traces",
      value: fmtNum(totalSeriesTraces),
      total: `${fmtNum(totalSeriesTraces)} total`,
      tone: "teal",
      format: compactNum,
      tip: (p) => `${fmtNum(p.value)} traces`,
    },
  ];
  const activeHero = heroMetrics.find((m) => m.key === heroKey) ?? heroMetrics[0];

  const peakDailyTokens = Math.max(1, ...series.map((s) => Number(s.total_tokens || 0)));

  const localTokens = cmp?.local?.tokens ?? 0;
  const propTokens = cmp?.proprietary?.tokens ?? 0;
  const mixTotal = localTokens + propTokens;
  const localSharePct = mixTotal > 0 ? (localTokens / mixTotal) * 100 : null;

  const latencyLeaders = useMemo(() => {
    return [...models]
      .map((m) => ({
        ...m,
        lat: m.today_avg_latency_ms ?? m.avg_latency_ms,
      }))
      .filter((m) => m.lat != null)
      .sort((a, b) => (b.lat || 0) - (a.lat || 0));
  }, [models]);

  const modelTableRows = useMemo<ModelTableRow[]>(() => {
    const rows: ModelTableRow[] = models.map((m) => {
      const reqs = m.period_requests ?? m.today_requests ?? 0;
      const tokens = m.period_total_tokens ?? m.today_total_tokens ?? 0;
      const cost = m.period_cost_usd ?? m.today_cost_usd ?? null;
      const isLocal = (m.provider || "ollama") === "ollama";
      return {
        id: m.id,
        sub: m.family + (m.default ? " · default" : ""),
        provider: m.provider || "ollama",
        enabled: m.enabled,
        installed: m.installed,
        isDefault: m.default,
        isLocal,
        kind: "chat",
        reqs,
        tokens,
        cost: isLocal ? null : cost,
        tpr: tokensPerReq(tokens, reqs),
        c1k: isLocal ? null : costPer1k(cost, tokens),
        latency: m.today_avg_latency_ms ?? m.avg_latency_ms ?? null,
      };
    });

    if (emb?.enabled) {
      rows.push({
        id: emb.model || "embedding",
        sub: "embedding",
        provider: "ollama",
        enabled: true,
        installed: true,
        isDefault: false,
        isLocal: true,
        kind: "embed",
        reqs: emb.today_requests ?? 0,
        tokens: 0,
        cost: null,
        tpr: null,
        c1k: null,
        latency: emb.today_avg_latency_ms ?? emb.avg_latency_ms ?? null,
      });
    }
    return rows;
  }, [models, emb]);

  const visibleModelRows = useMemo(() => {
    const q = modelQuery.trim().toLowerCase();
    return modelTableRows
      .filter((r) => (modelScope === "all" ? true : modelScope === "local" ? r.isLocal : !r.isLocal))
      .filter((r) => !q || r.id.toLowerCase().includes(q) || r.provider.toLowerCase().includes(q))
      .sort((a, b) => compareRows(a, b, modelSort.key, modelSort.dir));
  }, [modelTableRows, modelScope, modelQuery, modelSort]);

  const maxRowTokens = Math.max(1, ...visibleModelRows.map((r) => r.tokens));

  const modelGroups = useMemo(() => {
    if (modelScope !== "all") {
      return [
        {
          id: modelScope,
          label: modelScope === "local" ? "Self-hosted · Ollama" : "Cloud providers",
          rows: visibleModelRows,
        },
      ];
    }
    const local = visibleModelRows.filter((r) => r.isLocal);
    const cloud = visibleModelRows.filter((r) => !r.isLocal);
    return [
      { id: "local", label: "Self-hosted · Ollama", rows: local },
      { id: "cloud", label: "Cloud providers", rows: cloud },
    ].filter((g) => g.rows.length > 0);
  }, [visibleModelRows, modelScope]);

  function toggleSort(key: ModelSortKey) {
    setModelSort((s) =>
      s.key === key
        ? { key, dir: s.dir === "desc" ? "asc" : "desc" }
        : { key, dir: key === "id" ? "asc" : "desc" },
    );
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <p className="page-kicker">Control plane</p>
          <h1>Client observability</h1>
          <p className="muted" style={{ margin: "0.4rem 0 0" }}>
            Usage, models, tokens, cost, and live hardware — the detail behind every request.
          </p>
        </div>
        <div className="page-head-actions">
          <FreshnessStamp at={lastLoaded} busy={refreshing} />
          <button
            type="button"
            className="secondary"
            onClick={() => refresh()}
            disabled={refreshing}
          >
            {refreshing ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </div>

      <nav className="dash-tabs" aria-label="Dashboard sections">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            className={`dash-tab ${tab === t.id ? "active" : ""}`}
            onClick={() => setTab(t.id)}
          >
            <span className="dash-tab-label">{t.label}</span>
            <span className="dash-tab-desc">{t.desc}</span>
          </button>
        ))}
      </nav>

      <div className="filterbar">
        <div className="filterbar-group">
          <span className="filterbar-label">Range</span>
          <div className="seg">
            {RANGE_PRESETS.map((p) => (
              <button
                key={p.key}
                type="button"
                className={rangeKey === p.key ? "seg-active" : ""}
                onClick={() => setRangeKey(p.key)}
              >
                {p.label}
              </button>
            ))}
            <button
              type="button"
              className={rangeKey === "custom" ? "seg-active" : ""}
              onClick={() => setRangeKey("custom")}
            >
              Custom
            </button>
          </div>
          {rangeKey === "custom" ? (
            <div className="filterbar-dates">
              <input
                type="date"
                value={customFrom}
                onChange={(e) => setCustomFrom(e.target.value)}
                aria-label="From date"
              />
              <span className="filterbar-arrow" aria-hidden>
                →
              </span>
              <input
                type="date"
                value={customTo}
                onChange={(e) => setCustomTo(e.target.value)}
                aria-label="To date"
              />
              <button type="button" className="secondary" onClick={() => refresh()} disabled={!customFrom}>
                Apply
              </button>
            </div>
          ) : null}
        </div>

        <div className="filterbar-group">
          <span className="filterbar-label">Application</span>
          <div className="seg">
            <button
              type="button"
              className={appFilter === "all" ? "seg-active" : ""}
              onClick={() => setAppFilter("all")}
            >
              All
            </button>
            {appItems.map((a) => (
              <button
                key={a.id}
                type="button"
                className={appFilter === a.id ? "seg-active" : ""}
                onClick={() => setAppFilter(a.id)}
              >
                {appLabel(a.id)}
              </button>
            ))}
          </div>
          {!appItems.length ? (
            <span className="filterbar-note">
              No project traffic yet — send header <code>X-Niyan-Application</code>
            </span>
          ) : null}
        </div>

        <div className="filterbar-status">
          <span className={`badge ${lfOk ? "up" : "down"}`} title="Where token and cost figures come from">
            {lfOk ? "Langfuse" : data?.traffic?.source || "unavailable"}
          </span>
        </div>

        {!lfOk && data?.traffic?.error ? (
          <p className="error filterbar-error">
            {data.traffic.error}. Configure observability keys in Observability / Langfuse project.
          </p>
        ) : null}
      </div>

      {error && <p className="error">{error}</p>}
      {loading && !data ? (
        <section className="grid stats-grid" aria-busy="true" aria-label="Loading metrics">
          {Array.from({ length: 6 }).map((_, i) => (
            <MetricSkeleton key={i} size="lg" />
          ))}
        </section>
      ) : null}

      <PageTurn turnKey={tab} direction={tabDirection} className="view-stage--tabs">
      {data && tab === "overview" ? (
        <div className="dash-pane" key="overview">
          <ServiceStrip
            {...serviceStrip(data.stack)}
            onOpen={() => setTab("hardware")}
          />

          <section className="hero">
            <div className="hero-metrics">
              {heroMetrics.map((m) => (
                <MetricCard
                  key={m.key}
                  label={m.label}
                  value={m.value}
                  delta={trendPct(series, m.key)}
                  invertDelta={m.invert}
                  hint={halfLabel(series)}
                  points={seriesPoints(series, m.key)}
                  tone={m.tone}
                  active={heroKey === m.key}
                  onSelect={() => setHeroKey(m.key)}
                />
              ))}
            </div>

            <div className="hero-chart">
              <div className="hero-chart-head">
                <div>
                  <h2>{activeHero.label}</h2>
                  <p className="hero-chart-sub">
                    Daily totals for {rangeLabel} · {activeHero.total}
                  </p>
                </div>
                <span className="hero-chart-legend">
                  <span className={`legend-swatch tone-${activeHero.tone}`} aria-hidden />
                  {activeHero.label}
                </span>
              </div>
              {series.length ? (
                <AreaChart
                  points={seriesPoints(series, heroKey)}
                  tone={activeHero.tone}
                  height={224}
                  format={activeHero.format}
                  formatTip={activeHero.tip}
                  label={activeHero.label.toLowerCase()}
                />
              ) : (
                <EmptyState
                  title="No traffic in this range"
                  hint={
                    lfOk
                      ? "Send a request through the gateway on :4000 and it will appear here."
                      : "Langfuse is not reporting yet — configure keys under Observability."
                  }
                />
              )}
            </div>
          </section>

          <section className="grid stats-grid">
            <MetricCard size="lg"
              label="Chat requests"
              value={fmtNum(period?.chat_requests)}
              hint="Through the gateway"
              basis={basisRange}
            />
            <MetricCard size="lg"
              label="Avg chat latency"
              value={fmtMs(chatLatency)}
              hint="Gateway → model"
              basis={chatLatencyBasis}
            />
            <MetricCard size="lg"
              label="Tokens / request"
              value={avgTokPerReq == null ? "—" : Math.round(avgTokPerReq).toLocaleString()}
              hint="Mean across requests"
              basis={basisRange}
            />
            <MetricCard size="lg"
              label="Cost / 1k tokens"
              value={avgCostPer1k == null ? "—" : fmtUsd(avgCostPer1k)}
              hint="Proprietary blend"
              basis={basisRange}
            />
            <MetricCard size="lg"
              label="Embed requests"
              value={fmtNum(today?.embed_requests)}
              hint="Gateway ops counter"
              basis={BASIS_TODAY}
            />
            <MetricCard size="lg"
              label="Guardrails blocked"
              value={fmtNum(blockedToday)}
              hint={`${fmtNum(blockedLife)} blocked all time`}
              basis={BASIS_TODAY}
            />
          </section>

          <div className="dash-split">
            <div className="panel">
              <h2>Busiest models</h2>
              <p className="muted" style={{ marginTop: 0 }}>
                Top {Math.min(8, modelShares.length) || 8} by token volume for {rangeLabel}.
              </p>
              <ShareList rows={modelShares.slice(0, 8)} />
              <button type="button" className="panel-link" onClick={() => setTab("models")}>
                Every model, sortable
              </button>
            </div>

            {/* Summary only — the figures behind this split live on the Cost tab. */}
            <div className="panel">
              <div className="panel-head">
                <h2>Where tokens run</h2>
                {localSharePct != null ? (
                  <span className="mix-headline">
                    <strong>{localSharePct.toFixed(0)}%</strong> self-hosted
                  </span>
                ) : null}
              </div>
              <p className="muted" style={{ marginTop: 0 }}>
                Tokens served by your own hardware versus providers that bill per token.
              </p>
              {mixTotal > 0 ? (
                <>
                  <div
                    className="split-bar"
                    role="img"
                    aria-label={`${localSharePct?.toFixed(0)}% of tokens served self-hosted`}
                  >
                    <span className="split-seg is-local" style={{ width: `${localSharePct ?? 0}%` }} />
                    <span
                      className="split-seg is-cloud"
                      style={{ width: `${100 - (localSharePct ?? 0)}%` }}
                    />
                  </div>
                  <div className="split-legend">
                    <span className="split-key">
                      <i className="swatch is-local" aria-hidden />
                      Self-hosted · {fmtNum(localTokens)} tok
                    </span>
                    <span className="split-key">
                      <i className="swatch is-cloud" aria-hidden />
                      Cloud · {fmtNum(propTokens)} tok · {fmtUsd(cmp?.proprietary?.cost_usd)}
                    </span>
                  </div>
                </>
              ) : (
                <EmptyState
                  title="Nothing to compare yet"
                  hint="Once requests flow through the gateway, the self-hosted and cloud split appears here."
                />
              )}
              <button type="button" className="panel-link" onClick={() => setTab("cost")}>
                Full cost breakdown
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {data && tab === "models" ? (
        <div className="dash-pane" key="models">
          <section className="grid stats-grid">
            <MetricCard size="lg" label="Configured models" value={fmtNum(models.length)} hint="Chat models in config" />
            <MetricCard size="lg"
              label="Active models"
              value={fmtNum(models.filter((m) => (m.period_requests ?? m.today_requests) > 0).length)}
              hint="Served at least one request"
              basis={basisRange}
            />
            <MetricCard size="lg"
              label="Enabled"
              value={fmtNum(models.filter((m) => m.enabled).length)}
              hint={`${models.filter((m) => m.installed).length} installed / ready`}
            />
            <MetricCard size="lg"
              label="Default model"
              value={models.find((m) => m.default)?.id || "—"}
              hint={models.find((m) => m.default)?.provider || ""}
            />
          </section>

          <div className="panel">
            <div className="table-toolbar">
              <div>
                <h2>Per-model observability</h2>
                <p className="table-toolbar-sub">
                  Requests, tokens, cost, latency, and efficiency for {rangeLabel}.
                </p>
              </div>
              <div className="table-toolbar-controls">
                <input
                  className="table-search"
                  value={modelQuery}
                  onChange={(e) => setModelQuery(e.target.value)}
                  placeholder="Filter models…"
                  aria-label="Filter models"
                  spellCheck={false}
                />
                <div className="seg">
                  {(["all", "local", "cloud"] as ModelScope[]).map((s) => (
                    <button
                      key={s}
                      type="button"
                      className={modelScope === s ? "seg-active" : ""}
                      onClick={() => setModelScope(s)}
                    >
                      {s === "all" ? "All" : s === "local" ? "Self-hosted" : "Cloud"}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="panel-scroll" style={{ maxHeight: 520 }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <SortHeader
                      label="Model"
                      sortKey="id"
                      active={modelSort.key === "id"}
                      dir={modelSort.dir}
                      onSort={toggleSort}
                    />
                    <th>Status</th>
                    <SortHeader
                      label="Requests"
                      sortKey="reqs"
                      active={modelSort.key === "reqs"}
                      dir={modelSort.dir}
                      onSort={toggleSort}
                      align="right"
                    />
                    <SortHeader
                      label="Tokens"
                      sortKey="tokens"
                      active={modelSort.key === "tokens"}
                      dir={modelSort.dir}
                      onSort={toggleSort}
                      align="right"
                    />
                    <SortHeader
                      label="Tok/req"
                      sortKey="tpr"
                      active={modelSort.key === "tpr"}
                      dir={modelSort.dir}
                      onSort={toggleSort}
                      align="right"
                    />
                    <SortHeader
                      label="Cost"
                      sortKey="cost"
                      active={modelSort.key === "cost"}
                      dir={modelSort.dir}
                      onSort={toggleSort}
                      align="right"
                    />
                    <SortHeader
                      label="$/1k tok"
                      sortKey="c1k"
                      active={modelSort.key === "c1k"}
                      dir={modelSort.dir}
                      onSort={toggleSort}
                      align="right"
                    />
                    <SortHeader
                      label="Latency"
                      sortKey="latency"
                      active={modelSort.key === "latency"}
                      dir={modelSort.dir}
                      onSort={toggleSort}
                      align="right"
                    />
                  </tr>
                </thead>
                <tbody>
                  {modelGroups.map((group) => (
                    <Fragment key={group.id}>
                      <tr className="table-group">
                        <td colSpan={8}>
                          <span className="table-group-label">{group.label}</span>
                          <span className="table-group-count">
                            {group.rows.length} {group.rows.length === 1 ? "model" : "models"}
                          </span>
                        </td>
                      </tr>
                      {group.rows.map((r) => (
                        <tr key={`${r.kind}-${r.id}`} className={r.reqs === 0 ? "is-idle" : undefined}>
                          <td>
                            <div className="cell-model">
                              <span className="cell-model-id">
                                {r.id}
                                {r.isDefault ? <span className="tag-default">default</span> : null}
                              </span>
                              <span className="cell-model-sub">
                                {r.provider} · {r.sub}
                              </span>
                            </div>
                          </td>
                          <td>
                            <span className="status-pair">
                              <span
                                className={`dot-status ${r.enabled ? "is-on" : "is-off"}`}
                                title={r.enabled ? "Enabled" : "Disabled"}
                              />
                              <span
                                className={`dot-status ${r.installed ? "is-on" : "is-off"}`}
                                title={
                                  r.installed
                                    ? "Ready"
                                    : r.isLocal
                                      ? "Not pulled on this host"
                                      : "Provider key not configured"
                                }
                              />
                              <ModelFix row={r} />
                            </span>
                          </td>
                          <td className="td-num">{fmtNum(r.reqs)}</td>
                          <td className="td-num">
                            <span className="cell-metric">
                              <span>{r.kind === "embed" ? "—" : fmtNum(r.tokens)}</span>
                              {r.tokens > 0 ? (
                                <span className="cell-bar">
                                  <span style={{ width: `${(r.tokens / maxRowTokens) * 100}%` }} />
                                </span>
                              ) : null}
                            </span>
                          </td>
                          <td className="td-num">
                            {r.tpr == null ? "—" : Math.round(r.tpr).toLocaleString()}
                          </td>
                          <td className="td-num">{r.cost == null ? "—" : fmtUsd(r.cost)}</td>
                          <td className="td-num">{r.c1k == null ? "—" : fmtUsd(r.c1k)}</td>
                          <td className="td-num">{fmtMs(r.latency)}</td>
                        </tr>
                      ))}
                    </Fragment>
                  ))}
                  {!visibleModelRows.length ? (
                    <tr>
                      <td colSpan={8}>
                        <EmptyState
                          title={modelQuery ? `No model matches “${modelQuery}”` : "No models in this view"}
                          hint={
                            modelQuery
                              ? "Clear the filter to see every configured model."
                              : "Nothing is enabled for this scope yet."
                          }
                          action={
                            modelQuery ? (
                              <button
                                type="button"
                                className="secondary"
                                onClick={() => setModelQuery("")}
                              >
                                Clear search
                              </button>
                            ) : (
                              <Link className="btn secondary" to="/inference/on-prem">
                                Configure models
                              </Link>
                            )
                          }
                        />
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
            <div className="table-foot">
              <span className="status-legend">
                <span className="dot-status is-on" /> enabled · ready
                <span className="dot-status is-off" /> disabled · missing
              </span>
              {!lfOk ? (
                <span className="table-foot-note">
                  Usage and cost stay empty until Langfuse keys are configured and reachable.
                </span>
              ) : null}
            </div>
          </div>

          <div className="dash-split">
            <div className="panel">
              <h2>Token distribution</h2>
              <p className="muted" style={{ marginTop: 0 }}>
                Share of total tokens across every reporting model.
              </p>
              <ShareList rows={modelShares} emptyLabel="No model traffic in this range." />
            </div>
            <div className="panel">
              <h2>Slowest models</h2>
              <p className="muted" style={{ marginTop: 0 }}>
                Highest average chat latency, measured at the gateway.
              </p>
              <ShareList
                tone="plum"
                emptyLabel="No latency samples yet."
                rows={latencyLeaders.slice(0, 8).map((m) => ({
                  id: m.id,
                  label: m.id,
                  sub: m.provider || "ollama",
                  value: m.lat || 0,
                  meta: fmtMs(m.lat),
                }))}
              />
              <div className="kpi-strip">
                <KpiChip label="Embed model" value={emb?.enabled ? emb.model || "—" : "disabled"} />
                <KpiChip label="Embed reqs (today)" value={fmtNum(emb?.today_requests)} />
                <KpiChip
                  label="Embed latency"
                  value={fmtMs(emb?.today_avg_latency_ms ?? emb?.avg_latency_ms)}
                />
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {data && tab === "cost" ? (
        <div className="dash-pane" key="cost">
          <section className="grid stats-grid">
            <MetricCard size="lg"
              label="Total cost"
              value={fmtUsd(period?.cost_usd)}
              hint="Proprietary APIs only"
              basis={basisRange}
            />
            <MetricCard size="lg"
              label="OpenAI cost"
              value={fmtUsd(cmp?.proprietary?.openai?.cost_usd)}
              hint={`${fmtNum(cmp?.proprietary?.openai?.requests)} req · ${fmtNum(cmp?.proprietary?.openai?.tokens)} tok`}
              basis={basisRange}
            />
            <MetricCard size="lg"
              label="Gemini cost"
              value={fmtUsd(cmp?.proprietary?.gemini?.cost_usd)}
              hint={`${fmtNum(cmp?.proprietary?.gemini?.requests)} req · ${fmtNum(cmp?.proprietary?.gemini?.tokens)} tok`}
              basis={basisRange}
            />
            <MetricCard size="lg"
              label="Anthropic cost"
              value={fmtUsd(cmp?.proprietary?.anthropic?.cost_usd)}
              hint={`${fmtNum(cmp?.proprietary?.anthropic?.requests)} req · ${fmtNum(cmp?.proprietary?.anthropic?.tokens)} tok`}
              basis={basisRange}
            />
            <MetricCard size="lg"
              label="Local tokens"
              value={fmtNum(cmp?.local?.tokens)}
              hint={`${fmtNum(cmp?.local?.requests)} requests · cost TBD`}
              basis={basisRange}
            />
            <MetricCard size="lg"
              label="Traces"
              value={fmtNum(totalSeriesTraces)}
              hint="Sum of daily Langfuse traces"
              basis={basisRange}
            />
            <MetricCard size="lg"
              label="Chat requests"
              value={fmtNum(life?.chat_requests)}
              hint="Gateway counter since start"
              basis={BASIS_LIFETIME}
            />
          </section>

          <div className="panel">
            <div className="panel-head">
              <h2>Where the tokens run</h2>
              {localSharePct != null ? (
                <span className="mix-headline">
                  <strong>{localSharePct.toFixed(0)}%</strong> self-hosted
                </span>
              ) : null}
            </div>
            <p className="muted" style={{ marginTop: 0 }}>
              {cmp?.note || "Proprietary cost comes from Langfuse. Open-source cost is not yet modelled."}
            </p>

            {mixTotal > 0 ? (
              <>
                <div className="split-bar" role="img" aria-label={`${localSharePct?.toFixed(0)}% self-hosted tokens`}>
                  <span className="split-seg is-local" style={{ width: `${localSharePct ?? 0}%` }} />
                  <span className="split-seg is-cloud" style={{ width: `${100 - (localSharePct ?? 0)}%` }} />
                </div>
                <div className="split-legend">
                  <span className="split-key">
                    <i className="swatch is-local" aria-hidden />
                    Self-hosted · {fmtNum(localTokens)} tok
                  </span>
                  <span className="split-key">
                    <i className="swatch is-cloud" aria-hidden />
                    Cloud · {fmtNum(propTokens)} tok
                  </span>
                </div>
              </>
            ) : null}

            <div className="compare">
              <div className="compare-side">
                <span className="compare-title">{cmp?.local?.label || "Self-hosted · Ollama"}</span>
                <dl className="compare-figures">
                  <div>
                    <dt>Requests</dt>
                    <dd>{fmtNum(cmp?.local?.requests)}</dd>
                  </div>
                  <div>
                    <dt>Tokens</dt>
                    <dd>{fmtNum(cmp?.local?.tokens)}</dd>
                  </div>
                  <div>
                    <dt>API cost</dt>
                    <dd className="is-free">{fmtUsd(cmp?.local?.cost_usd)}</dd>
                  </div>
                </dl>
                <span className="compare-note">
                  {cmp?.local?.api_cost_note || "No per-token API charge — you pay for the hardware."}
                </span>
              </div>

              <div className="compare-side">
                <span className="compare-title">{cmp?.proprietary?.label || "Cloud providers"}</span>
                <dl className="compare-figures">
                  <div>
                    <dt>Requests</dt>
                    <dd>{fmtNum(cmp?.proprietary?.requests)}</dd>
                  </div>
                  <div>
                    <dt>Tokens</dt>
                    <dd>{fmtNum(cmp?.proprietary?.tokens)}</dd>
                  </div>
                  <div>
                    <dt>API cost</dt>
                    <dd>{fmtUsd(cmp?.proprietary?.cost_usd)}</dd>
                  </div>
                </dl>
                <span className="compare-note">
                  Billed per token by OpenAI, Gemini, and Anthropic.
                </span>
              </div>
            </div>
          </div>

          <div className="detail-grid">
            <div className="panel">
              <div className="panel-head">
                <h2>Cost over time</h2>
                <Delta pct={trendPct(series, "cost_usd")} invert />
              </div>
              {series.length ? (
                <AreaChart
                  points={seriesPoints(series, "cost_usd")}
                  tone="sand"
                  height={172}
                  format={(v) => fmtUsd(v)}
                  formatTip={(p) => fmtUsd(p.value)}
                  label="cost"
                />
              ) : (
                <EmptyState title="No spend recorded" />
              )}
            </div>
            <div className="panel">
              <div className="panel-head">
                <h2>Tokens over time</h2>
                <Delta pct={trendPct(series, "total_tokens")} />
              </div>
              {series.length ? (
                <AreaChart
                  points={seriesPoints(series, "total_tokens")}
                  tone="accent"
                  height={172}
                  format={compactNum}
                  formatTip={(p) => `${fmtNum(p.value)} tokens`}
                  label="tokens"
                />
              ) : (
                <EmptyState title="No tokens recorded" />
              )}
            </div>
            <div className="panel">
              <div className="panel-head">
                <h2>Traces over time</h2>
                <Delta pct={trendPct(series, "traces")} />
              </div>
              {series.length ? (
                <AreaChart
                  points={seriesPoints(series, "traces")}
                  tone="teal"
                  height={172}
                  format={compactNum}
                  formatTip={(p) => `${fmtNum(p.value)} traces`}
                  label="traces"
                />
              ) : (
                <EmptyState title="No traces recorded" />
              )}
            </div>
          </div>

          <div className="panel" style={{ marginTop: "1rem" }}>
            <h2>Daily breakdown</h2>
            <p className="muted" style={{ marginTop: 0 }}>
              Every day in {rangeLabel} with tokens, traces, and proprietary spend.
            </p>
            <div className="panel-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Date (UTC)</th>
                    <th className="th-right">Tokens</th>
                    <th className="th-right">Traces</th>
                    <th className="th-right">Cost</th>
                    <th className="th-right">$/1k tok</th>
                  </tr>
                </thead>
                <tbody>
                  {[...series].reverse().map((s) => {
                    const tok = Number(s.total_tokens || 0);
                    return (
                      <tr key={s.date}>
                        <td className="td-date">{s.date}</td>
                        <td className="td-num">
                          <span className="cell-metric">
                            <span>{fmtNum(tok)}</span>
                            {tok > 0 ? (
                              <span className="cell-bar">
                                <span style={{ width: `${(tok / peakDailyTokens) * 100}%` }} />
                              </span>
                            ) : null}
                          </span>
                        </td>
                        <td className="td-num">{fmtNum(s.traces)}</td>
                        <td className="td-num">{fmtUsd(s.cost_usd)}</td>
                        <td className="td-num">{fmtUsd(costPer1k(s.cost_usd, s.total_tokens))}</td>
                      </tr>
                    );
                  })}
                  {!series.length ? (
                    <tr>
                      <td colSpan={5}>
                        <EmptyState
                          title="No daily rows yet"
                          hint="Traffic appears here once Langfuse reports usage for this range."
                        />
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </div>

          <div className="dash-split">
            <div className="panel">
              <h2>Gateway lifetime counters</h2>
              <div className="kpi-strip">
                <KpiChip label="Chat requests" value={fmtNum(life?.chat_requests)} />
                <KpiChip label="Embed requests" value={fmtNum(life?.embed_requests)} />
                <KpiChip label="Avg chat latency" value={fmtMs(life?.avg_chat_latency_ms)} />
                <KpiChip label="Avg embed latency" value={fmtMs(life?.avg_embed_latency_ms)} />
                <KpiChip label="Guardrails blocked" value={fmtNum(life?.guardrails_blocked)} />
                <KpiChip label="Tokens (period)" value={fmtNum(life?.total_tokens)} />
              </div>
            </div>
            <div className="panel">
              <h2>Cost by model</h2>
              <ShareList
                tone="sand"
                emptyLabel="No proprietary spend in this range."
                rows={[...models]
                  .map((m) => {
                    const cost = m.period_cost_usd ?? m.today_cost_usd ?? 0;
                    return {
                      id: m.id,
                      label: m.id,
                      sub: m.provider || "",
                      value: typeof cost === "number" ? cost : 0,
                      meta: m.provider === "ollama" ? "local · N/A" : fmtUsd(cost),
                    };
                  })
                  .filter((r) => r.value > 0)
                  .sort((a, b) => b.value - a.value)}
              />
            </div>
          </div>
        </div>
      ) : null}

      {data && tab === "applications" ? (
        <div className="dash-pane" key="applications">
          <section className="grid stats-grid">
            <MetricCard size="lg"
              label="Projects seen"
              value={fmtNum(appItems.length)}
              hint={selectedApp === "all" ? "All applications" : `Filtered · ${appLabel(selectedApp)}`}
              basis={basisRange}
            />
            <MetricCard size="lg"
              label="Requests"
              value={fmtNum(period?.chat_requests)}
              hint={
                selectedApp === "all" ? "Across every project" : `Attributed to ${appLabel(selectedApp)}`
              }
              basis={basisRange}
            />
            <MetricCard size="lg"
              label="Tokens"
              value={fmtNum(period?.total_tokens)}
              hint={selectedApp === "all" ? "Langfuse + gateway" : "Gateway counters for this project"}
              basis={basisRange}
            />
            <MetricCard size="lg"
              label="Cost"
              value={fmtUsd(period?.cost_usd)}
              hint="Proprietary API cost"
              basis={basisRange}
            />
          </section>

          <div className="panel">
            <div className="table-toolbar">
              <div>
                <h2>Usage by application</h2>
                <p className="table-toolbar-sub">
                  {data.application?.note ||
                    "Each client should send X-Niyan-Application so niyan can attribute tokens and cost per project."}
                </p>
              </div>
              {appFilter !== "all" ? (
                <button type="button" className="secondary" onClick={() => setAppFilter("all")}>
                  Clear filter
                </button>
              ) : null}
            </div>

            <div className="panel-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Application</th>
                    <th>Tokens / day</th>
                    <th className="th-right">Requests</th>
                    <th className="th-right">Tokens</th>
                    <th className="th-right">Cost</th>
                    <th className="th-right">Share</th>
                  </tr>
                </thead>
                <tbody>
                  {appItems.map((a) => {
                    const reqs = a.period_requests ?? a.requests ?? 0;
                    const tokens = a.period_total_tokens ?? a.total_tokens ?? 0;
                    const cost = a.period_cost_usd ?? a.cost_usd;
                    const totalTok = Math.max(
                      1,
                      appItems.reduce((s, x) => s + (x.period_total_tokens ?? x.total_tokens ?? 0), 0),
                    );
                    const sharePct = (tokens / totalTok) * 100;
                    const selected = appFilter === a.id;
                    const spark: Point[] = (a.daily || []).map((d) => ({
                      label: d.date || "",
                      value: Number(d.total_tokens || 0),
                    }));
                    const select = () => setAppFilter(selected ? "all" : a.id);
                    return (
                      <tr
                        key={a.id}
                        className={`row-select ${selected ? "is-selected" : ""}`}
                        onClick={select}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            select();
                          }
                        }}
                        tabIndex={0}
                        role="button"
                        aria-pressed={selected}
                        title={selected ? "Clear this filter" : `Filter the dashboard to ${a.id}`}
                      >
                        <td>
                          <div className="cell-model">
                            <span className="cell-model-id">
                              {appLabel(a.id)}
                              {selected ? <span className="tag-default">filtered</span> : null}
                            </span>
                            <span className="cell-model-sub">
                              {fmtNum(a.today_requests)} today
                            </span>
                          </div>
                        </td>
                        <td className="td-spark">
                          {spark.length > 1 ? (
                            <Sparkline points={spark} tone="teal" height={26} />
                          ) : (
                            <span className="td-spark-empty">—</span>
                          )}
                        </td>
                        <td className="td-num">{fmtNum(reqs)}</td>
                        <td className="td-num">{fmtNum(tokens)}</td>
                        <td className="td-num">{fmtUsd(cost)}</td>
                        <td className="td-num">
                          <span className="cell-metric">
                            <span>{sharePct.toFixed(0)}%</span>
                            <span className="cell-bar">
                              <span
                                style={{ width: `${sharePct}%`, background: "var(--teal)" }}
                              />
                            </span>
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                  {!appItems.length ? (
                    <tr>
                      <td colSpan={6}>
                        <EmptyState
                          title="No attributed traffic yet"
                          hint="Send X-Niyan-Application with each request and projects will appear here automatically."
                        />
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
            {appItems.length ? (
              <div className="table-foot">
                <span className="table-foot-note">
                  Select a row to scope every panel on this dashboard to that project.
                </span>
              </div>
            ) : null}
          </div>

          <div className="dash-split">
            <div className="panel">
              <div className="panel-head">
                <h2>Token share</h2>
                {functionShares.top.length ? (
                  <span className="mix-headline">
                    top {functionShares.top.length} functions
                  </span>
                ) : null}
              </div>
              <p className="muted" style={{ marginTop: 0 }}>
                Enterprise functions for {rangeLabel} — the policy domain sent as{" "}
                <code>model</code> (finance, research, legal, …). Product vs Unattributed
                is in the table above.
              </p>
              <ShareList
                tone="teal"
                emptyLabel="No function traffic yet. Call the gateway with model set to a policy domain, e.g. finance."
                rows={functionShares.top.map((r) => ({
                  id: r.id,
                  label: r.id,
                  sub: `${fmtNum(r.reqs)} requests · ${fmtUsd(r.cost)}`,
                  value: r.tokens,
                  meta: `${r.pct.toFixed(1)}% · ${fmtNum(r.tokens)} tok`,
                }))}
              />
              {functionShares.rest ? (
                <p className="code-note">
                  {functionShares.rest} further function{functionShares.rest === 1 ? "" : "s"}{" "}
                  contributed the remaining {(100 - functionShares.topPct).toFixed(1)}%.
                </p>
              ) : null}
            </div>
            <div className="panel">
              <h2>How to attribute</h2>
              <p className="muted" style={{ marginTop: 0 }}>
                The header names the product. The <code>model</code> field names the
                enterprise function when it matches a policy domain.
              </p>
              <pre className="code-block">
                <code>
{`curl ${GATEWAY_ORIGIN}/v1/chat/completions \\
  -H "Authorization: Bearer sk-niyan-local" \\
  -H "X-Niyan-Application: Enterprise-Functions" \\
  -H "Content-Type: application/json" \\
  -d '{"model":"finance","messages":[{"role":"user","content":"hi"}]}'`}
                </code>
              </pre>
              <p className="code-note">
                Header <code>Enterprise-Functions</code> lands in the table as that product.
                <code>model: finance</code> (or research, legal, …) is what Token share
                counts. No header → Unattributed. A concrete model id like{" "}
                <code>llama3.2:3b</code> is not a function and will not appear here.
              </p>
            </div>
          </div>
        </div>
      ) : null}

      {data && tab === "hardware" ? (
        <div className="dash-pane" key="hardware">
          {/* Capacity of the host. Live utilization belongs to the meters below,
              so these cards deliberately state totals rather than percentages. */}
          <section className="grid stats-grid">
            <MetricCard size="lg"
              label="CPU cores"
              value={resources?.cpu?.count != null ? fmtNum(resources.cpu.count) : "—"}
              hint={resources?.cpu?.available === false ? "unavailable" : "Available to containers"}
            />
            <MetricCard size="lg"
              label="Total memory"
              value={fmtBytes(resources?.memory?.total_bytes)}
              hint="Host physical memory"
            />
            <MetricCard size="lg"
              label="GPUs"
              value={resources?.gpu?.available ? fmtNum(gpuDevices.length) : "0"}
              hint={
                resources?.gpu?.available
                  ? gpuDevices[0]?.name || "detected"
                  : resources?.gpu?.detail || "none detected"
              }
            />
          </section>

          <div className="dash-split" style={{ marginTop: "1rem" }}>
            <div className="panel">
              <div className="panel-head">
                <h2>Host utilization</h2>
                {resources?.generated_at ? (
                  <span className="live-stamp">
                    <span className="live-dot" aria-hidden />
                    {new Date(resources.generated_at).toLocaleTimeString()}
                  </span>
                ) : null}
              </div>
              <p className="muted" style={{ marginTop: 0 }}>
                Live host usage, sampled every 3 seconds. Per-GPU load is in the device table.
              </p>
              {resources ? (
                <>
                  <ResourceMeter
                    label="CPU"
                    percent={resources.cpu?.percent}
                    detail={
                      resources.cpu?.count
                        ? `${resources.cpu.count} cores`
                        : resources.cpu?.available === false
                          ? "unavailable"
                          : undefined
                    }
                  />
                  <ResourceMeter
                    label="Memory"
                    percent={resources.memory?.percent}
                    detail={
                      resources.memory?.used_bytes != null && resources.memory?.total_bytes != null
                        ? `${fmtBytes(resources.memory.used_bytes)} / ${fmtBytes(resources.memory.total_bytes)}`
                        : undefined
                    }
                  />
                </>
              ) : (
                <div className="hw-loading">
                  <Skeleton w="100%" h={30} />
                  <Skeleton w="100%" h={30} />
                </div>
              )}
            </div>

            <div className="panel">
              <h2>GPU devices</h2>
              <p className="muted" style={{ marginTop: 0 }}>
                Per-device utilization and VRAM from the host snapshot.
              </p>
              {resources?.gpu?.available && gpuDevices.length > 0 ? (
                <div className="panel-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Name</th>
                        <th>Util</th>
                        <th>VRAM</th>
                        <th>VRAM used</th>
                      </tr>
                    </thead>
                    <tbody>
                      {gpuDevices.map((g) => (
                        <tr key={g.index ?? g.name}>
                          <td>{g.index ?? "—"}</td>
                          <td>{g.name || "—"}</td>
                          <td>
                            {g.utilization_percent == null
                              ? "—"
                              : `${g.utilization_percent.toFixed(0)}%`}
                          </td>
                          <td>
                            {g.memory_percent == null ? "—" : `${g.memory_percent.toFixed(0)}%`}
                          </td>
                          <td>
                            {g.memory_used_bytes != null && g.memory_total_bytes != null
                              ? `${fmtBytes(g.memory_used_bytes)} / ${fmtBytes(g.memory_total_bytes)}`
                              : "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <EmptyState
                  title="No GPU on this host"
                  hint={
                    resources?.gpu?.detail ||
                    "Inference runs on CPU. On Linux with NVIDIA drivers, the linux-gpu profile reserves the device automatically."
                  }
                />
              )}
            </div>
          </div>

          <div className="panel" style={{ marginTop: "1rem" }}>
            <h2>Services</h2>
            <p className="muted" style={{ marginTop: 0 }}>
              Endpoint probes answer &ldquo;is it responding&rdquo;; containers answer &ldquo;is it
              running&rdquo;. On Docker Desktop, Ollama is a host process — it is up when the
              probe succeeds, even with no ollama container.
            </p>

            <p className="sub-label">Endpoint probes</p>
            <div className="chip-row">
              {Object.entries(data.stack?.checks || {}).map(([name, ok]) => (
                <span key={name} className={`badge ${ok ? "up" : "down"}`}>
                  {serviceLabel(name)}: {ok ? "up" : "down"}
                </span>
              ))}
            </div>

            <p className="sub-label">Containers</p>
            <div className="panel-scroll" style={{ maxHeight: 260 }}>
              <table>
                <thead>
                  <tr>
                    <th>Service</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {(data.stack?.services || [])
                    .filter((s) => s.status !== "not_created")
                    .map((s) => (
                      <tr key={s.name}>
                        <td>{s.name}</td>
                        <td>
                          <span className={`badge ${s.healthy ? "up" : "down"}`}>{s.status}</span>
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      ) : null}
      </PageTurn>

      {data ? (
        <p className="muted" style={{ marginTop: "1rem", fontSize: "0.8rem" }}>
          Usage auto-refreshes every 30s, hardware every 3s · token and cost source{" "}
          {data.traffic?.source || "—"}
        </p>
      ) : null}
    </div>
  );
}
