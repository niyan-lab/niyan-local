import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { MetricCard } from "../components/ui";

type TargetType = "gateway_chat" | "gateway_embeddings" | "gateway_domain" | "custom";

type Run = {
  id: string;
  name?: string;
  status: string;
  target_type: string;
  created_at?: string;
  started_at?: string;
  finished_at?: string;
  error?: string;
  cost_warning?: string;
  job?: Record<string, unknown>;
  progress?: {
    elapsed_sec?: number;
    users?: number;
    requests?: number;
    failures?: number;
    fail_percent?: number;
    rps?: number;
    latency_ms?: { p50?: number; p95?: number; p99?: number; avg?: number };
    total_tokens?: number;
  };
  summary?: {
    requests?: number;
    failures?: number;
    fail_percent?: number;
    rps?: number;
    latency_ms?: { p50?: number; p95?: number; p99?: number; avg?: number };
    total_tokens?: number;
    duration_sec?: number;
  };
  artifacts?: Record<string, boolean>;
};

const DOMAIN_OPTIONS = [
  "finance",
  "marketing",
  "sales",
  "research",
  "summary",
  "support",
  "legal",
];

function fmtMs(v: number | null | undefined) {
  if (v == null || Number.isNaN(v)) return "—";
  if (v >= 1000) return `${(v / 1000).toFixed(1)}s`;
  return `${Math.round(v)} ms`;
}

/** Grid-sized metric card, shared with the dashboard. */
function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return <MetricCard size="lg" label={label} value={value} hint={hint} />;
}

export default function LoadTesting() {
  const [target, setTarget] = useState<TargetType>("gateway_chat");
  const [model, setModel] = useState("llama3.2:3b");
  const [domain, setDomain] = useState("finance");
  const [prompt, setPrompt] = useState("Say hi in five words.");
  const [embedInput, setEmbedInput] = useState("niyan load test embedding input");
  const [auth, setAuth] = useState("");
  const [users, setUsers] = useState(5);
  const [spawn, setSpawn] = useState(1);
  const [duration, setDuration] = useState(30);
  const [customUrl, setCustomUrl] = useState("");
  const [customMethod, setCustomMethod] = useState("POST");
  const [customHeaders, setCustomHeaders] = useState('{"Content-Type":"application/json"}');
  const [customBody, setCustomBody] = useState('{"ping":true}');
  const [allowInternal, setAllowInternal] = useState(true);
  const [models, setModels] = useState<Array<{ id: string; provider?: string }>>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [active, setActive] = useState<Run | null>(null);
  const [limits, setLimits] = useState({ max_users: 50, max_duration_sec: 600, min_duration_sec: 5 });
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const refreshList = useCallback(async () => {
    const res = await api.loadtests();
    setRuns((res.runs || []) as Run[]);
    setActiveId((res.active_run_id as string) || null);
  }, []);

  useEffect(() => {
    Promise.all([api.loadtestPresets(), api.models(), refreshList()])
      .then(([presets, modelsRes]) => {
        if (presets.limits) setLimits(presets.limits);
        setModels((modelsRes.models || []).map((m) => ({ id: m.id, provider: m.provider })));
      })
      .catch((err) => setError(String(err)));
  }, [refreshList]);

  useEffect(() => {
    if (!activeId) {
      setActive(null);
      return;
    }
    let cancelled = false;
    const tick = async () => {
      try {
        const r = (await api.getLoadtest(activeId)) as Run;
        if (!cancelled) {
          setActive(r);
          if (r.status !== "running" && r.status !== "queued") {
            setActiveId(null);
            await refreshList();
          }
        }
      } catch {
        /* keep last */
      }
    };
    tick();
    const id = setInterval(tick, 2000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [activeId, refreshList]);

  const costHint = useMemo(() => {
    const m = (target === "gateway_domain" ? domain : model).toLowerCase();
    if (target === "custom") return "";
    if (m.startsWith("gpt-") || m.startsWith("gemini") || m.startsWith("o1") || m.startsWith("o3")) {
      return "This may call a proprietary API and incur cost. Keep users/duration low.";
    }
    if (target === "gateway_domain") {
      return "Domain routing may hit proprietary models if Enterprise AI Policy is set to Proprietary.";
    }
    return "";
  }, [target, model, domain]);

  async function onStart(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setMsg("");
    try {
      let headers: Record<string, string> | undefined;
      let body: unknown = undefined;
      if (target === "custom") {
        try {
          headers = customHeaders.trim() ? JSON.parse(customHeaders) : {};
        } catch {
          throw new Error("Custom headers must be valid JSON object");
        }
        if (customBody.trim()) {
          try {
            body = JSON.parse(customBody);
          } catch {
            body = customBody;
          }
        }
      }
      const payload: Record<string, unknown> = {
        target_type: target,
        auth_bearer: auth,
        users,
        spawn_rate: spawn,
        duration_sec: duration,
      };
      if (target === "gateway_chat") {
        payload.model = model;
        payload.messages = [{ role: "user", content: prompt }];
      } else if (target === "gateway_domain") {
        payload.model = domain;
        payload.messages = [{ role: "user", content: prompt }];
      } else if (target === "gateway_embeddings") {
        payload.model = model || "nomic-embed-text";
        payload.input = embedInput;
      } else {
        if (!customUrl.trim()) throw new Error("Custom URL is required");
        payload.url = customUrl;
        payload.method = customMethod;
        payload.headers = headers;
        payload.body = body;
        payload.allow_internal_urls = allowInternal;
      }
      const run = (await api.createLoadtest(payload)) as Run;
      setMsg(`Started ${run.id}`);
      setActiveId(run.id);
      setActive(run);
      await refreshList();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onStop() {
    if (!activeId) return;
    setBusy(true);
    setError("");
    try {
      await api.stopLoadtest(activeId);
      setMsg("Stop requested");
      await refreshList();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  const live = active?.progress || active?.summary;
  const elapsedSec =
    active?.progress?.elapsed_sec ?? active?.summary?.duration_sec ?? 0;
  const localAndCloud = models.length
    ? models
    : [
        { id: "llama3.2:3b", provider: "ollama" },
        { id: "gemini-2.5-flash", provider: "gemini" },
        { id: "gpt-4o-mini", provider: "openai" },
      ];

  return (
    <div>
      <div className="page-head">
        <div>
          <p className="page-kicker">Capacity</p>
          <h1>Load Testing</h1>
          <p className="muted" style={{ margin: "0.4rem 0 0" }}>
            Run Locust against the niyan gateway (chat, embeddings, domains) or one custom HTTP
            endpoint. Caps: {limits.max_users} users · {limits.max_duration_sec}s · one active run.
          </p>
        </div>
      </div>

      {error && <p className="error">{error}</p>}
      {msg && <p style={{ color: "var(--ok)" }}>{msg}</p>}
      {costHint && (
        <p className="error" style={{ background: "rgba(245, 158, 11, 0.12)", color: "#fbbf24" }}>
          {costHint}
        </p>
      )}

      <form className="panel" onSubmit={onStart} style={{ marginBottom: "1rem" }}>
        <h2>Configure</h2>
        <div className="field">
          <label>Target</label>
          <select value={target} onChange={(e) => setTarget(e.target.value as TargetType)}>
            <option value="gateway_chat">Gateway chat completions</option>
            <option value="gateway_embeddings">Gateway embeddings</option>
            <option value="gateway_domain">Gateway domain (Enterprise AI Policy)</option>
            <option value="custom">Custom HTTP endpoint</option>
          </select>
        </div>

        {target === "gateway_chat" || target === "gateway_embeddings" ? (
          <div className="field">
            <label>Model</label>
            <select value={model} onChange={(e) => setModel(e.target.value)}>
              {localAndCloud.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.id}
                </option>
              ))}
              {target === "gateway_embeddings" ? (
                <option value="nomic-embed-text">nomic-embed-text</option>
              ) : null}
            </select>
          </div>
        ) : null}

        {target === "gateway_domain" ? (
          <div className="field">
            <label>Domain</label>
            <select value={domain} onChange={(e) => setDomain(e.target.value)}>
              {DOMAIN_OPTIONS.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </div>
        ) : null}

        {target === "gateway_chat" || target === "gateway_domain" ? (
          <div className="field">
            <label>User message</label>
            <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={2} />
          </div>
        ) : null}

        {target === "gateway_embeddings" ? (
          <div className="field">
            <label>Embedding input</label>
            <input value={embedInput} onChange={(e) => setEmbedInput(e.target.value)} />
          </div>
        ) : null}

        {target === "custom" ? (
          <>
            <div className="field">
              <label>URL</label>
              <input
                value={customUrl}
                onChange={(e) => setCustomUrl(e.target.value)}
                placeholder="http://gateway:4000/health or https://your-app/api/..."
              />
              <p className="muted" style={{ margin: "0.35rem 0 0", fontSize: "0.8rem" }}>
                From the Locust container use Docker DNS (e.g.{" "}
                <code>http://gateway:4000/...</code>), not localhost.
              </p>
            </div>
            <div className="field">
              <label>Method</label>
              <select value={customMethod} onChange={(e) => setCustomMethod(e.target.value)}>
                <option>GET</option>
                <option>POST</option>
                <option>PUT</option>
                <option>PATCH</option>
                <option>DELETE</option>
              </select>
            </div>
            <div className="field">
              <label>Headers (JSON)</label>
              <textarea value={customHeaders} onChange={(e) => setCustomHeaders(e.target.value)} rows={2} />
            </div>
            <div className="field">
              <label>Body (JSON or text)</label>
              <textarea value={customBody} onChange={(e) => setCustomBody(e.target.value)} rows={3} />
            </div>
            <label className="toggle" style={{ marginBottom: "0.75rem" }}>
              <input
                type="checkbox"
                checked={allowInternal}
                onChange={(e) => setAllowInternal(e.target.checked)}
              />
              Allow internal URLs (private/RFC1918 / Docker network)
            </label>
          </>
        ) : (
          <p className="muted" style={{ marginTop: 0, fontSize: "0.85rem" }}>
            Hits niyan gateway at <code>http://gateway:4000</code>
            {target === "gateway_chat" || target === "gateway_domain"
              ? " → POST /v1/chat/completions"
              : " → POST /v1/embeddings"}
            .
          </p>
        )}

        <div className="grid" style={{ gridTemplateColumns: "1fr 1fr 1fr", gap: "0.75rem" }}>
          <div className="field">
            <label>Concurrent users</label>
            <input
              type="number"
              min={1}
              max={limits.max_users}
              value={users}
              onChange={(e) => setUsers(Number(e.target.value))}
            />
          </div>
          <div className="field">
            <label>Spawn rate /s</label>
            <input
              type="number"
              min={0.1}
              step={0.1}
              value={spawn}
              onChange={(e) => setSpawn(Number(e.target.value))}
            />
          </div>
          <div className="field">
            <label>Duration (sec)</label>
            <input
              type="number"
              min={limits.min_duration_sec}
              max={limits.max_duration_sec}
              value={duration}
              onChange={(e) => setDuration(Number(e.target.value))}
            />
          </div>
        </div>

        <div className="field">
          <label>Bearer token</label>
          <input value={auth} onChange={(e) => setAuth(e.target.value)} autoComplete="off" />
        </div>

        <div className="row" style={{ gap: "0.5rem" }}>
          <button type="submit" disabled={busy || !!activeId}>
            {busy ? "Starting…" : "Start load test"}
          </button>
          <button
            type="button"
            className="secondary danger"
            disabled={busy || !activeId}
            onClick={() => onStop()}
          >
            Stop
          </button>
        </div>
      </form>

      {(active || activeId) && (
        <div className="panel" style={{ marginBottom: "1rem" }}>
          <h2>Live progress</h2>
          <p className="muted" style={{ marginTop: 0 }}>
            {active?.id || activeId} ·{" "}
            <span className={`badge ${active?.status === "running" ? "up" : "down"}`}>
              {active?.status || "…"}
            </span>
            {active?.cost_warning ? ` · ${active.cost_warning}` : ""}
          </p>
          <div className="grid stats-grid">
            <Stat label="Requests" value={String(live?.requests ?? 0)} />
            <Stat label="RPS" value={(live?.rps ?? 0).toFixed(1)} />
            <Stat
              label="Fail %"
              value={`${(live?.fail_percent ?? 0).toFixed(1)}%`}
              hint={`${live?.failures ?? 0} failures`}
            />
            <Stat label="p50" value={fmtMs(live?.latency_ms?.p50)} />
            <Stat label="p95" value={fmtMs(live?.latency_ms?.p95)} />
            <Stat label="p99" value={fmtMs(live?.latency_ms?.p99)} />
            <Stat label="Tokens" value={String(live?.total_tokens ?? 0)} hint="From chat usage when present" />
            <Stat
              label="Elapsed"
              value={`${Math.round(elapsedSec)}s`}
              hint={`${active?.progress?.users ?? (active?.job?.users as number | undefined) ?? "—"} users`}
            />
          </div>
          {active?.error ? <p className="error">{active.error}</p> : null}
          {active && active.status !== "running" && active.status !== "queued" ? (
            <div className="row" style={{ gap: "0.5rem", marginTop: "0.75rem", flexWrap: "wrap" }}>
              <button
                type="button"
                onClick={() => api.viewLoadtestReport(active.id).catch((e) => setError(String(e)))}
                disabled={!active.artifacts?.report_html}
              >
                View report
              </button>
              <button
                type="button"
                className="secondary"
                onClick={() => api.downloadLoadtest(active.id, "json").catch((e) => setError(String(e)))}
              >
                Download JSON
              </button>
              <button
                type="button"
                className="secondary"
                onClick={() => api.downloadLoadtest(active.id, "csv").catch((e) => setError(String(e)))}
              >
                Download CSV
              </button>
            </div>
          ) : null}
        </div>
      )}

      <div className="panel">
        <h2>History</h2>
        <div className="panel-scroll">
          <table>
            <thead>
              <tr>
                <th>Run</th>
                <th>Target</th>
                <th>Status</th>
                <th>Requests</th>
                <th>p95</th>
                <th>Reports</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => {
                const s = r.summary || r.progress;
                return (
                  <tr key={r.id}>
                    <td>
                      <strong>{r.name || r.id}</strong>
                      <div className="muted" style={{ fontSize: "0.75rem" }}>
                        {r.created_at}
                      </div>
                    </td>
                    <td>
                      <span className="badge">{r.target_type}</span>
                    </td>
                    <td>
                      <span className={`badge ${r.status === "finished" || r.status === "running" ? "up" : "down"}`}>
                        {r.status}
                      </span>
                    </td>
                    <td>{s?.requests ?? "—"}</td>
                    <td>{fmtMs(s?.latency_ms?.p95)}</td>
                    <td>
                      <div className="row" style={{ gap: "0.35rem", flexWrap: "wrap" }}>
                        <button
                          type="button"
                          className="secondary"
                          style={{ padding: "0.25rem 0.5rem", fontSize: "0.75rem" }}
                          disabled={!r.artifacts?.report_html}
                          onClick={() => api.viewLoadtestReport(r.id).catch((e) => setError(String(e)))}
                        >
                          View
                        </button>
                        <button
                          type="button"
                          className="secondary"
                          style={{ padding: "0.25rem 0.5rem", fontSize: "0.75rem" }}
                          onClick={() => api.downloadLoadtest(r.id, "json").catch((e) => setError(String(e)))}
                        >
                          JSON
                        </button>
                        <button
                          type="button"
                          className="secondary"
                          style={{ padding: "0.25rem 0.5rem", fontSize: "0.75rem" }}
                          onClick={() => api.downloadLoadtest(r.id, "csv").catch((e) => setError(String(e)))}
                        >
                          CSV
                        </button>
                        {r.status === "running" || r.status === "queued" ? (
                          <button
                            type="button"
                            className="secondary"
                            style={{ padding: "0.25rem 0.5rem", fontSize: "0.75rem" }}
                            onClick={() => setActiveId(r.id)}
                          >
                            Watch
                          </button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                );
              })}
              {runs.length === 0 ? (
                <tr>
                  <td colSpan={6} className="muted">
                    No runs yet — start a load test above.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
