import { FormEvent, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, type ProviderModel, type ProviderSection } from "../api/client";

function formatContext(tokens: number): string {
  if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(0)}M ctx`;
  if (tokens >= 1000) return `${Math.round(tokens / 1000)}K ctx`;
  return `${tokens} ctx`;
}

function price(value: number): string {
  if (!value) return "—";
  return `$${value.toFixed(2)}`;
}

export default function Proprietary() {
  const [searchParams] = useSearchParams();
  const focus = (searchParams.get("focus") || "").toLowerCase();
  const [providers, setProviders] = useState<ProviderSection[]>([]);
  const [keys, setKeys] = useState<Record<string, string>>({});
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async (live = false) => {
    const res = await api.proprietary(live);
    setProviders(res.providers);
  }, []);

  useEffect(() => {
    refresh()
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, [refresh]);

  useEffect(() => {
    if (!focus || !providers.length) return;
    document.getElementById(`provider-${focus}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [focus, providers]);

  async function saveKey(e: FormEvent, provider: ProviderSection) {
    e.preventDefault();
    setBusy(provider.name);
    setError("");
    setMsg("");
    try {
      const key = (keys[provider.name] || "").trim();
      const body: Record<string, { enabled: boolean; api_key?: string }> = {
        [provider.name]: { enabled: provider.enabled },
      };
      if (key) body[provider.name].api_key = key;
      await api.putProviders(body);
      setKeys((k) => ({ ...k, [provider.name]: "" }));
      setMsg(`${provider.title} saved — LiteLLM refreshed`);
      await refresh(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  }

  async function toggleModel(model: ProviderModel, enabled: boolean) {
    setBusy(model.id);
    setError("");
    setMsg("");
    try {
      await api.updateModel(model.id, {
        enabled,
        // The model may only exist in the provider's catalog, not niyan.yaml yet.
        provider: model.in_config ? undefined : model.provider,
        family: model.in_config ? undefined : model.family,
      });
      setMsg(`${model.id} ${enabled ? "enabled" : "disabled"} on the gateway`);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  }

  async function liveRefresh() {
    setRefreshing(true);
    setError("");
    setMsg("");
    try {
      await refresh(true);
      setMsg("Checked each provider for the models your keys can reach");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRefreshing(false);
    }
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <p className="page-kicker">Cloud inference</p>
          <h1>Proprietary</h1>
          <p className="muted" style={{ margin: "0.4rem 0 0" }}>
            Configure a provider key, then enable the models you want routable. Requests still go
            through the same OpenAI-compatible gateway as your on-prem models.
          </p>
        </div>
        <div className="head-stats">
          <button type="button" className="secondary" onClick={liveRefresh} disabled={refreshing}>
            {refreshing ? "Checking…" : "Refresh from providers"}
          </button>
        </div>
      </div>

      {error && <p className="error">{error}</p>}
      {msg && <p style={{ color: "var(--ok)" }}>{msg}</p>}
      {loading ? <p className="muted">Loading providers…</p> : null}

      <div style={{ display: "grid", gap: "1rem" }}>
        {providers.map((provider) => {
          const highlighted = focus === provider.name;
          const enabledCount = provider.models.filter((m) => m.enabled).length;
          return (
            <section
              key={provider.name}
              id={`provider-${provider.name}`}
              className={`panel${highlighted ? " panel-focus" : ""}`}
            >
              <div className="inline-toggle" style={{ marginBottom: "0.75rem" }}>
                <div className="grow">
                  <h2 style={{ margin: 0 }}>{provider.title}</h2>
                  <p className="muted" style={{ margin: "0.35rem 0 0" }}>
                    <span className={`badge ${provider.configured ? "up" : "down"}`}>
                      {provider.configured ? `key ···${provider.api_key_last4}` : "no key"}
                    </span>{" "}
                    {enabledCount} of {provider.models.length} models routable
                    {provider.live_refreshed ? " · verified against your key" : ""}
                  </p>
                </div>
                <label className="toggle">
                  <input
                    type="checkbox"
                    checked={provider.enabled}
                    onChange={(e) =>
                      setProviders((list) =>
                        list.map((p) =>
                          p.name === provider.name ? { ...p, enabled: e.target.checked } : p,
                        ),
                      )
                    }
                  />
                  Enabled
                </label>
              </div>

              <form className="provider-key" onSubmit={(e) => saveKey(e, provider)}>
                <div className="field grow">
                  <label htmlFor={`key-${provider.name}`}>
                    API key {provider.configured ? "(leave blank to keep current)" : ""}
                  </label>
                  <input
                    id={`key-${provider.name}`}
                    type="password"
                    value={keys[provider.name] || ""}
                    onChange={(e) => setKeys((k) => ({ ...k, [provider.name]: e.target.value }))}
                    placeholder={provider.configured ? "••••••••" : "Paste API key"}
                    autoComplete="off"
                  />
                </div>
                <button type="submit" disabled={busy === provider.name}>
                  {busy === provider.name ? "Saving…" : "Save"}
                </button>
                {provider.docs_url ? (
                  <a className="ghost-link" href={provider.docs_url} target="_blank" rel="noreferrer">
                    Get a key ↗
                  </a>
                ) : null}
              </form>

              {provider.detail ? <p className="muted">{provider.detail}</p> : null}

              {!provider.configured ? (
                <p className="muted">
                  Add a key above to enable these models. Pricing shown is the published list rate
                  used for Dashboard cost estimates.
                </p>
              ) : null}

              <div className="pmodel-list">
                {provider.models.map((model) => {
                  const card = model.card;
                  const open = expanded[model.id] ?? false;
                  const unreachable = model.available_live === false;
                  return (
                    <div className="pmodel" key={model.id}>
                      <div className="pmodel-main">
                        <div className="pmodel-title">
                          <strong>{model.name || model.id}</strong>
                          {model.default ? <span className="badge">default</span> : null}
                          {!card ? <span className="chip">no card</span> : null}
                          {unreachable ? (
                            <span className="badge down" title="Your key did not list this model">
                              not in your plan
                            </span>
                          ) : null}
                        </div>
                        <code className="mcard-id">{model.id}</code>
                        {card ? <p className="muted">{card.summary}</p> : null}
                        <div className="pmodel-meta">
                          {card ? <span className="chip">{formatContext(card.context_window)}</span> : null}
                          {card && card.input_per_1m ? (
                            <span className="chip">
                              {price(card.input_per_1m)} in / {price(card.output_per_1m)} out per 1M
                            </span>
                          ) : null}
                          {card ? <span className={`chip chip--${card.modality}`}>{card.modality}</span> : null}
                        </div>
                      </div>

                      <div className="pmodel-side">
                        <label className="toggle">
                          <input
                            type="checkbox"
                            checked={model.enabled}
                            disabled={busy === model.id || (!model.enabled && !provider.configured)}
                            title={
                              !provider.configured && !model.enabled
                                ? "Save an API key for this provider first"
                                : undefined
                            }
                            onChange={(e) => toggleModel(model, e.target.checked)}
                          />
                          {model.enabled ? "on" : "off"}
                        </label>
                        {card ? (
                          <button
                            type="button"
                            className="ghost"
                            onClick={() => setExpanded((x) => ({ ...x, [model.id]: !open }))}
                            aria-expanded={open}
                          >
                            {open ? "Less" : "Details"}
                          </button>
                        ) : null}
                      </div>

                      {open && card ? (
                        <div className="pmodel-detail">
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
                          <dl className="pmodel-specs">
                            <div>
                              <dt>Context</dt>
                              <dd>{card.context_window.toLocaleString()} tokens</dd>
                            </div>
                            {card.max_output_tokens ? (
                              <div>
                                <dt>Max output</dt>
                                <dd>{card.max_output_tokens.toLocaleString()} tokens</dd>
                              </div>
                            ) : null}
                            <div>
                              <dt>Input price</dt>
                              <dd>{price(card.input_per_1m)} / 1M tokens</dd>
                            </div>
                            <div>
                              <dt>Output price</dt>
                              <dd>{price(card.output_per_1m)} / 1M tokens</dd>
                            </div>
                          </dl>
                          {card.source_url ? (
                            <p className="muted mcard-source">
                              Prices are the published list rate.{" "}
                              <a href={card.source_url} target="_blank" rel="noreferrer">
                                Provider docs ↗
                              </a>
                            </p>
                          ) : null}
                        </div>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
