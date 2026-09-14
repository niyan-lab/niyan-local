import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type ModelCard, type OnPremModel } from "../api/client";
import { EmptyState } from "../components/ui";
import { startPull, usePulls, type PullJob } from "../pulls";

type HostCapacity = { ramGb: number | null; vramGb: number | null };

const MODALITIES = [
  { id: "all", label: "All" },
  { id: "chat", label: "Chat" },
  { id: "code", label: "Code" },
  { id: "reasoning", label: "Reasoning" },
  { id: "vision", label: "Vision" },
  { id: "embedding", label: "Embedding" },
] as const;

type Modality = (typeof MODALITIES)[number]["id"];

function gb(bytes: number | null | undefined): number | null {
  if (bytes == null) return null;
  return bytes / 1024 ** 3;
}

function formatBytes(bytes: number | null): string {
  const value = gb(bytes);
  if (value == null) return "—";
  return value >= 1 ? `${value.toFixed(1)} GB` : `${(value * 1024).toFixed(0)} MB`;
}

function formatContext(tokens: number): string {
  if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(0)}M ctx`;
  if (tokens >= 1000) return `${Math.round(tokens / 1024)}K ctx`;
  return `${tokens} ctx`;
}

/**
 * Compare a card's stated requirements against the host the stack runs on.
 * `null` means we could not read host metrics, which is different from "won't fit".
 */
function fitFor(card: ModelCard | null, host: HostCapacity) {
  if (!card) return null;
  const req = card.requirements;
  if (host.ramGb == null) return null;
  if (req.min_vram_gb > 0 && host.vramGb != null && host.vramGb + 0.5 >= req.min_vram_gb) {
    return { tone: "good", label: "Fits GPU" } as const;
  }
  if (host.ramGb + 0.5 >= req.recommended_ram_gb) {
    return { tone: "good", label: "Fits host" } as const;
  }
  if (host.ramGb + 0.5 >= req.min_ram_gb) {
    return { tone: "warn", label: "Tight fit" } as const;
  }
  return { tone: "bad", label: `Needs ${req.min_ram_gb} GB` } as const;
}

function placeholderModel(job: PullJob): OnPremModel {
  return {
    id: job.id,
    family: job.card?.family ?? "",
    enabled: false,
    installed: false,
    loaded: false,
    default: false,
    managed: true,
    size_bytes: null,
    parameter_size: job.card?.parameters ?? "",
    quantization: "",
    modified_at: "",
    card: job.card,
  };
}

export default function OnPrem() {
  const pulls = usePulls();
  const [models, setModels] = useState<OnPremModel[]>([]);
  const [catalog, setCatalog] = useState<ModelCard[]>([]);
  const [reachable, setReachable] = useState(true);
  const [host, setHost] = useState<HostCapacity>({ ramGb: null, vramGb: null });
  const [modality, setModality] = useState<Modality>("all");
  const [query, setQuery] = useState("");
  const [showCatalog, setShowCatalog] = useState(false);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [busyLabel, setBusyLabel] = useState("");
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const res = await api.onPrem();
    setModels(res.models);
    setReachable(res.ollama_reachable);
    if (res.adopted.length) {
      setMsg(`Adopted from Ollama: ${res.adopted.join(", ")}`);
    }
  }, []);

  useEffect(() => {
    (async () => {
      try {
        await refresh();
        const [cards, resources] = await Promise.all([
          api.onPremCatalog(),
          api.dashboardResources().catch(() => null),
        ]);
        setCatalog(cards.cards);
        setHost({
          ramGb: gb(resources?.memory?.total_bytes ?? null),
          vramGb: gb(resources?.gpu?.devices?.[0]?.memory_total_bytes ?? null),
        });
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setLoading(false);
      }
    })();
  }, [refresh]);

  useEffect(() => {
    if (pulls.some((job) => job.status === "success")) {
      refresh().catch(() => undefined);
    }
    const failed = pulls.find((job) => job.error);
    if (failed?.error) setError(failed.error);
  }, [pulls, refresh]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    const matches = (m: OnPremModel) => {
      const card = m.card;
      if (modality !== "all") {
        const mod = card?.modality ?? (m.family === "embedding" ? "embedding" : "chat");
        if (mod !== modality) return false;
      }
      if (!q) return true;
      const haystack = [m.id, m.family, card?.name, card?.publisher, card?.summary]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(q);
    };
    const filtered = models.filter(matches);
    const pullingIds = new Set(pulls.map((job) => job.id));
    const pinned = pulls.map((job) => models.find((m) => m.id === job.id) || placeholderModel(job));
    return [...pinned, ...filtered.filter((m) => !pullingIds.has(m.id))];
  }, [models, modality, query, pulls]);

  const notInstalled = useMemo(() => {
    const hidden = new Set([
      ...models.filter((m) => m.installed).map((m) => m.id.split(":")[0]),
      ...pulls.map((job) => job.id.split(":")[0]),
    ]);
    return catalog.filter((c) => !hidden.has(c.id.split(":")[0]));
  }, [catalog, models, pulls]);

  const totals = useMemo(() => {
    const installed = models.filter((m) => m.installed);
    const disk = installed.reduce((sum, m) => sum + (m.size_bytes ?? 0), 0);
    return {
      installed: installed.length,
      loaded: models.filter((m) => m.loaded).length,
      disk,
    };
  }, [models]);

  async function run(id: string, label: string, fn: () => Promise<unknown>, success: string) {
    setBusy(id);
    setBusyLabel(label);
    setError("");
    setMsg("");
    try {
      await fn();
      setMsg(success);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
      setBusyLabel("");
    }
  }

  function pull(id: string, card?: ModelCard | null) {
    setError("");
    setMsg(`Pulling ${id}…`);
    void startPull(id, { card: card ?? catalog.find((c) => c.id === id) ?? null });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function Card({ model }: { model: OnPremModel }) {
    const card = model.card;
    const job = pulls.find((item) => item.id === model.id);
    const pulling = Boolean(job && job.status !== "error");
    const isBusy = busy === model.id || (pulling && job?.status !== "success");
    const pct = job?.percent;
    const open = expanded[model.id] ?? false;
    const fit = fitFor(card, host);
    const modalityLabel = card?.modality ?? (model.family === "embedding" ? "embedding" : "chat");

    return (
      <article className={`mcard${model.installed ? " is-installed" : ""}`}>
        <header className="mcard-head">
          <div className="mcard-title">
            <h3>{card?.name ?? model.id}</h3>
            <code className="mcard-id">{model.id}</code>
          </div>
          <div className="mcard-flags">
            {job && job.status !== "success" ? (
            <span className={`badge ${job.error ? "down" : "up"}`}>
              {job.error ? "pull failed" : pct != null ? `${Math.round(pct)}%` : "pulling"}
            </span>
          ) : null}
          {model.default ? <span className="badge">default</span> : null}
            {model.loaded ? <span className="badge up">in memory</span> : null}
            <span className={`badge ${model.installed ? "up" : "down"}`}>
              {model.installed ? "on disk" : "not pulled"}
            </span>
          </div>
        </header>

        <div className="mcard-meta">
          <span className={`chip chip--${modalityLabel}`}>{modalityLabel}</span>
          {card ? <span className="chip">{card.publisher}</span> : null}
          <span className="chip">{model.parameter_size || card?.parameters || model.family}</span>
          {card ? <span className="chip">{formatContext(card.context_window)}</span> : null}
          {model.installed ? <span className="chip">{formatBytes(model.size_bytes)}</span> : null}
          {model.quantization ? <span className="chip">{model.quantization}</span> : null}
          {fit ? <span className={`chip chip--fit-${fit.tone}`}>{fit.label}</span> : null}
        </div>

        <p className="mcard-summary">
          {card?.summary ?? "Pulled directly through Ollama — no curated card for this tag yet."}
        </p>

        {job && job.status !== "success" ? (
          <div className="mcard-progress">
            <div className="progress-track">
              <div
                className={`progress-fill${pct == null && !job.error ? " is-indeterminate" : ""}`}
                style={{ width: pct != null ? `${Math.min(100, Math.max(0, pct))}%` : undefined }}
              />
            </div>
            <span className={job.error ? "error" : "muted"}>
              {job.error
                ? job.error
                : `${job.status || "starting"}${
                    pct != null ? ` · ${pct.toFixed(pct >= 10 ? 0 : 1)}%` : ""
                  }${
                    job.total
                      ? ` · ${formatBytes(job.completed)} / ${formatBytes(job.total)}`
                      : ""
                  }`}
            </span>
          </div>
        ) : null}

        {open && card ? (
          <div className="mcard-detail">
            <div className="mcard-cols">
              <section>
                <h4>Good at</h4>
                <ul className="mcard-list mcard-list--good">
                  {card.strengths.map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                </ul>
              </section>
              <section>
                <h4>Watch out for</h4>
                <ul className="mcard-list mcard-list--bad">
                  {card.limitations.map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                </ul>
              </section>
            </div>

            <section className="mcard-req">
              <h4>Minimum system requirements</h4>
              <dl>
                <div>
                  <dt>Disk</dt>
                  <dd>{card.requirements.disk_gb} GB</dd>
                </div>
                <div>
                  <dt>RAM</dt>
                  <dd>
                    {card.requirements.min_ram_gb} GB min · {card.requirements.recommended_ram_gb} GB
                    recommended
                  </dd>
                </div>
                <div>
                  <dt>GPU</dt>
                  <dd>
                    {card.requirements.min_vram_gb > 0
                      ? `${card.requirements.min_vram_gb} GB VRAM`
                      : "Not required"}
                    {card.requirements.runs_on_cpu ? " · CPU capable" : " · GPU only"}
                  </dd>
                </div>
                <div>
                  <dt>Quantization</dt>
                  <dd>{card.requirements.quantization}</dd>
                </div>
                <div>
                  <dt>Licence</dt>
                  <dd>{card.license}</dd>
                </div>
                {card.embedding_dimensions ? (
                  <div>
                    <dt>Dimensions</dt>
                    <dd>{card.embedding_dimensions}</dd>
                  </div>
                ) : null}
              </dl>
              {card.requirements.note ? <p className="muted">{card.requirements.note}</p> : null}
            </section>

            <section className="mcard-bench">
              <h4>Published benchmarks</h4>
              {card.benchmarks.length ? (
                <>
                  <div className="bench-row">
                    {card.benchmarks.map((b) => (
                      <div className="bench" key={b.suite}>
                        <span className="bench-suite">{b.suite}</span>
                        <span className="bench-score">
                          {b.score}
                          {b.unit}
                        </span>
                        {b.note ? <span className="bench-note">{b.note}</span> : null}
                      </div>
                    ))}
                  </div>
                  <p className="muted mcard-source">
                    Reported by the publisher, not re-run by Niyan.{" "}
                    {card.source_url ? (
                      <a href={card.source_url} target="_blank" rel="noreferrer">
                        Model card ↗
                      </a>
                    ) : null}
                  </p>
                </>
              ) : (
                <p className="muted">
                  No published figures recorded for this tag.{" "}
                  {card.source_url ? (
                    <a href={card.source_url} target="_blank" rel="noreferrer">
                      Model card ↗
                    </a>
                  ) : null}
                </p>
              )}
            </section>
          </div>
        ) : null}

        <footer className="mcard-foot">
          <label className="toggle">
            <input
              type="checkbox"
              checked={model.enabled}
              disabled={isBusy}
              onChange={(e) =>
                run(
                  model.id,
                  "Saving…",
                  () => api.updateModel(model.id, { enabled: e.target.checked }),
                  `${model.id} ${e.target.checked ? "enabled" : "disabled"} on the gateway`,
                )
              }
            />
            {model.enabled ? "Routing on" : "Routing off"}
          </label>

          <div className="mcard-actions">
            {!model.installed && job?.status !== "success" ? (
              <button type="button" disabled={isBusy} onClick={() => pull(model.id, card)}>
                {pulling && !job?.error
                  ? pct != null
                    ? `Pulling ${Math.round(pct)}%`
                    : "Pulling…"
                  : job?.error
                    ? "Retry"
                    : "Pull"}
              </button>
            ) : null}
            {model.installed && !model.loaded ? (
              <button
                type="button"
                className="secondary"
                disabled={isBusy}
                onClick={() =>
                  run(model.id, "Loading…", () => api.loadModel(model.id), `${model.id} loaded into memory`)
                }
              >
                {isBusy && busyLabel === "Loading…" ? "Loading…" : "Load"}
              </button>
            ) : null}
            {model.loaded ? (
              <button
                type="button"
                className="secondary"
                disabled={isBusy}
                onClick={() =>
                  run(model.id, "Ejecting…", () => api.ejectModel(model.id), `${model.id} ejected from memory`)
                }
              >
                {isBusy && busyLabel === "Ejecting…" ? "Ejecting…" : "Eject"}
              </button>
            ) : null}
            {model.installed ? (
              <button
                type="button"
                className="secondary danger"
                disabled={isBusy}
                onClick={() => {
                  if (!window.confirm(`Delete ${model.id} weights from disk? You can re-pull later.`)) return;
                  run(model.id, "Deleting…", () => api.deleteModel(model.id), `${model.id} deleted from disk`);
                }}
              >
                {isBusy && busyLabel === "Deleting…" ? "Deleting…" : "Delete"}
              </button>
            ) : null}
            {card ? (
              <button
                type="button"
                className="ghost"
                onClick={() => setExpanded((e) => ({ ...e, [model.id]: !open }))}
                aria-expanded={open}
              >
                {open ? "Less" : "Details"}
              </button>
            ) : null}
          </div>
        </footer>
      </article>
    );
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <p className="page-kicker">Self-hosted inference</p>
          <h1>On-prem</h1>
          <p className="muted" style={{ margin: "0.4rem 0 0" }}>
            Open-weight models running on your own hardware through Ollama. Anything pulled directly
            with <code>ollama pull</code> is adopted here automatically.
          </p>
        </div>
        <div className="head-stats">
          <span>
            <strong>{totals.installed}</strong> on disk
          </span>
          <span>
            <strong>{totals.loaded}</strong> in memory
          </span>
          <span>
            <strong>{formatBytes(totals.disk)}</strong> used
          </span>
          {host.ramGb != null ? (
            <span className="muted">
              host {host.ramGb.toFixed(0)} GB RAM
              {host.vramGb != null ? ` · ${host.vramGb.toFixed(0)} GB VRAM` : " · no GPU"}
            </span>
          ) : null}
        </div>
      </div>

      {!reachable ? (
        <p className="error">
          Ollama is unreachable — showing configured models only. Pull, load, and delete will fail
          until it is back.
        </p>
      ) : null}
      {error && <p className="error">{error}</p>}
      {msg && <p style={{ color: "var(--ok)" }}>{msg}</p>}

      <div className="filter-bar">
        <div className="chip-row">
          {MODALITIES.map((m) => (
            <button
              key={m.id}
              type="button"
              className={`filter-chip${modality === m.id ? " is-active" : ""}`}
              onClick={() => setModality(m.id)}
            >
              {m.label}
            </button>
          ))}
        </div>
        <input
          type="search"
          placeholder="Filter by name, publisher, or capability…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="filter-search"
        />
      </div>

      {loading ? (
        <p className="muted">Loading models…</p>
      ) : visible.length ? (
        <div className="mcard-grid">
          {visible.map((m) => (
            <Card key={m.id} model={m} />
          ))}
        </div>
      ) : (
        <EmptyState
          title="No models match"
          hint="Clear the filters, or add a model from the catalog below."
        />
      )}

      <div className="panel" style={{ marginTop: "1.25rem" }}>
        <div className="inline-toggle">
          <div className="grow">
            <h2 style={{ margin: 0 }}>Add a model</h2>
            <p className="muted" style={{ margin: "0.35rem 0 0" }}>
              {notInstalled.length} curated models with cards, plus anything in the public Ollama
              library.
            </p>
          </div>
          <button type="button" className="secondary" onClick={() => setShowCatalog((v) => !v)}>
            {showCatalog ? "Hide catalog" : "Browse catalog"}
          </button>
        </div>
        {showCatalog ? <Catalog cards={notInstalled} onPull={pull} /> : null}
      </div>
    </div>
  );
}

function Catalog({
  cards,
  onPull,
}: {
  cards: ModelCard[];
  onPull: (id: string, card?: ModelCard | null) => void;
}) {
  const pulls = usePulls();
  const [query, setQuery] = useState("");
  const [library, setLibrary] = useState<
    Array<{ id: string; name: string; description: string; curated: boolean }>
  >([]);
  const [libraryNote, setLibraryNote] = useState("");
  const [searching, setSearching] = useState(false);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const pulling = new Set(pulls.map((job) => job.id.split(":")[0]));
    const available = cards.filter((c) => !pulling.has(c.id.split(":")[0]));
    if (!q) return available;
    return available.filter((c) =>
      `${c.id} ${c.name} ${c.publisher} ${c.summary} ${c.modality}`.toLowerCase().includes(q),
    );
  }, [cards, query, pulls]);

  async function searchLibrary() {
    if (!query.trim()) return;
    setSearching(true);
    try {
      const res = await api.library(query.trim());
      setLibrary(res.results.filter((r) => !r.curated));
      setLibraryNote(res.detail || (res.source === "ollama.com" ? "" : "Offline — curated matches only."));
    } catch (err) {
      setLibraryNote(err instanceof Error ? err.message : String(err));
    } finally {
      setSearching(false);
    }
  }

  return (
    <div className="catalog">
      <div className="filter-bar" style={{ marginTop: "0.75rem" }}>
        <input
          type="search"
          placeholder="Search curated models…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="filter-search"
          onKeyDown={(e) => {
            if (e.key === "Enter") searchLibrary();
          }}
        />
        <button type="button" className="secondary" onClick={searchLibrary} disabled={searching || !query.trim()}>
          {searching ? "Searching…" : "Search Ollama library"}
        </button>
      </div>

      <div className="catalog-grid">
        {filtered.map((card) => (
            <div className="catalog-item" key={card.id}>
              <div className="catalog-item-head">
                <strong>{card.name}</strong>
                <span className={`chip chip--${card.modality}`}>{card.modality}</span>
              </div>
              <code className="mcard-id">{card.id}</code>
              <p className="muted">{card.summary}</p>
              <div className="catalog-item-meta">
                <span>{card.requirements.disk_gb} GB download</span>
                <span>{card.requirements.min_ram_gb} GB RAM min</span>
                <span>{formatContext(card.context_window)}</span>
              </div>
              <button type="button" onClick={() => onPull(card.id, card)}>
                Pull
              </button>
            </div>
        ))}
      </div>

      {libraryNote ? <p className="muted">{libraryNote}</p> : null}
      {library.length ? (
        <>
          <h3 style={{ marginBottom: "0.5rem" }}>From the Ollama library</h3>
          <p className="muted" style={{ marginTop: 0 }}>
            No curated card for these — Niyan will pull the tag as-is.
          </p>
          <div className="catalog-grid">
            {library
              .filter((item) => !pulls.some((job) => job.id === item.id))
              .map((item) => (
              <div className="catalog-item" key={item.id}>
                <div className="catalog-item-head">
                  <strong>{item.name}</strong>
                </div>
                <code className="mcard-id">{item.id}</code>
                {item.description ? <p className="muted">{item.description}</p> : null}
                <button type="button" onClick={() => onPull(item.id)}>
                  Pull
                </button>
              </div>
            ))}
          </div>
        </>
      ) : null}
    </div>
  );
}
