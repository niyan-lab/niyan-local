import { FormEvent, useEffect, useState } from "react";
import { api } from "../api/client";

type DomainRow = {
  id: string;
  enabled: boolean;
  deployment: "local" | "proprietary";
  local_model: string;
  proprietary_model: string;
};

type Catalog = {
  local: Array<{ id: string; provider: string; enabled: boolean }>;
  proprietary: Array<{ id: string; provider: string; enabled: boolean; ready?: boolean }>;
};

export default function EnterprisePolicy() {
  const [enabled, setEnabled] = useState(true);
  const [mode, setMode] = useState("manual");
  const [domains, setDomains] = useState<DomainRow[]>([]);
  const [catalog, setCatalog] = useState<Catalog>({ local: [], proprietary: [] });
  const [defaults, setDefaults] = useState({
    local_model: "llama3.2:3b",
    proprietary_model: "gemini-2.5-flash",
  });
  const [note, setNote] = useState("");
  const [newId, setNewId] = useState("");
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  async function refresh() {
    const res = await api.enterprisePolicy();
    setEnabled(res.policy.enabled);
    setMode(res.policy.mode || "manual");
    setDomains(res.policy.domains || []);
    setCatalog(res.catalog);
    setDefaults(res.defaults);
    setNote(res.note || "");
  }

  useEffect(() => {
    refresh().catch((err) => setError(String(err)));
  }, []);

  async function save(nextDomains: DomainRow[], nextEnabled = enabled, nextMode = mode) {
    setBusy(true);
    setError("");
    setMsg("");
    try {
      await api.putEnterprisePolicy({
        enabled: nextEnabled,
        mode: nextMode,
        domains: nextDomains,
      });
      setMsg("Policy saved — gateway remaps domains on the next request.");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  function updateRow(index: number, patch: Partial<DomainRow>) {
    setDomains((rows) => rows.map((r, i) => (i === index ? { ...r, ...patch } : r)));
  }

  async function onSaveAll(e: FormEvent) {
    e.preventDefault();
    await save(domains);
  }

  async function addDomain(e: FormEvent) {
    e.preventDefault();
    const id = newId.trim().toLowerCase();
    if (!id) return;
    if (domains.some((d) => d.id === id)) {
      setError(`Domain "${id}" already exists`);
      return;
    }
    const next = [
      ...domains,
      {
        id,
        enabled: true,
        deployment: "local" as const,
        local_model: defaults.local_model,
        proprietary_model: defaults.proprietary_model,
      },
    ];
    setNewId("");
    await save(next);
  }

  async function removeDomain(id: string) {
    await save(domains.filter((d) => d.id !== id));
  }

  const localOptions = catalog.local.length
    ? catalog.local
    : [{ id: defaults.local_model, provider: "ollama", enabled: true }];
  const propOptions = catalog.proprietary.length
    ? catalog.proprietary
    : [{ id: defaults.proprietary_model, provider: "gemini", enabled: true }];

  return (
    <div>
      <div className="page-head">
        <div>
          <p className="page-kicker">Routing</p>
          <h1>Enterprise AI Policy</h1>
          <p className="muted" style={{ margin: "0.4rem 0 0" }}>
            Map business domains to self-hosted or proprietary models. Clients send{" "}
            <code>model: &quot;finance&quot;</code> (etc.) instead of a concrete model id.
          </p>
        </div>
      </div>

      {error && <p className="error">{error}</p>}
      {msg && <p style={{ color: "var(--ok)" }}>{msg}</p>}
      {note && <p className="muted">{note}</p>}

      <form className="panel" onSubmit={onSaveAll} style={{ marginBottom: "1rem" }}>
        <div className="inline-toggle" style={{ marginBottom: "0.75rem" }}>
          <div className="grow">
            <h2 style={{ margin: 0 }}>Policy</h2>
            <p className="muted" style={{ margin: "0.35rem 0 0" }}>
              Manual bar per domain now. Auto (complexity / domain classifier) comes later.
            </p>
          </div>
          <label className="toggle">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => setEnabled(e.target.checked)}
            />
            Enabled
          </label>
        </div>
        <div className="field">
          <label>Mode</label>
          <div className="seg" role="group" aria-label="Policy mode">
            <button
              type="button"
              className={mode === "manual" ? "seg-active" : ""}
              onClick={() => setMode("manual")}
            >
              Manual
            </button>
            <button type="button" className="seg-disabled" disabled title="Coming soon">
              Auto (coming soon)
            </button>
          </div>
        </div>
        <button type="submit" disabled={busy}>
          {busy ? "Saving…" : "Save policy"}
        </button>
      </form>

      <div className="panel" style={{ marginBottom: "1rem" }}>
        <h2>Domains</h2>
        <p className="muted" style={{ marginTop: 0 }}>
          Flip the bar to choose self-hosted vs proprietary. Proprietary default is Gemini (
          {defaults.proprietary_model}).
        </p>
        <div className="panel-scroll">
          <table>
            <thead>
              <tr>
                <th>Domain</th>
                <th>Deployment</th>
                <th>Local model</th>
                <th>Proprietary model</th>
                <th>On</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {domains.map((d, i) => (
                <tr key={d.id}>
                  <td>
                    <strong>{d.id}</strong>
                  </td>
                  <td>
                    <div className="seg" role="group" aria-label={`${d.id} deployment`}>
                      <button
                        type="button"
                        className={d.deployment === "local" ? "seg-active" : ""}
                        onClick={() => updateRow(i, { deployment: "local" })}
                      >
                        Self-hosted
                      </button>
                      <button
                        type="button"
                        className={d.deployment === "proprietary" ? "seg-active" : ""}
                        onClick={() => updateRow(i, { deployment: "proprietary" })}
                      >
                        Proprietary
                      </button>
                    </div>
                  </td>
                  <td>
                    <select
                      value={d.local_model}
                      onChange={(e) => updateRow(i, { local_model: e.target.value })}
                    >
                      {!localOptions.some((o) => o.id === d.local_model) ? (
                        <option value={d.local_model}>{d.local_model}</option>
                      ) : null}
                      {localOptions.map((o) => (
                        <option key={o.id} value={o.id}>
                          {o.id}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <select
                      value={d.proprietary_model}
                      onChange={(e) => updateRow(i, { proprietary_model: e.target.value })}
                    >
                      {!propOptions.some((o) => o.id === d.proprietary_model) ? (
                        <option value={d.proprietary_model}>{d.proprietary_model}</option>
                      ) : null}
                      {propOptions.map((o) => (
                        <option key={o.id} value={o.id}>
                          {o.id}
                          {o.provider === "gemini" ? " (Gemini)" : ""}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <input
                      type="checkbox"
                      checked={d.enabled}
                      onChange={(e) => updateRow(i, { enabled: e.target.checked })}
                      aria-label={`${d.id} enabled`}
                    />
                  </td>
                  <td>
                    <button
                      type="button"
                      className="secondary danger"
                      onClick={() => removeDomain(d.id)}
                      disabled={busy}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <button
          type="button"
          style={{ marginTop: "0.75rem" }}
          disabled={busy}
          onClick={() => save(domains)}
        >
          {busy ? "Saving…" : "Save domain changes"}
        </button>
      </div>

      <form className="panel" onSubmit={addDomain}>
        <h2>Add domain</h2>
        <div className="field">
          <label>Domain id (clients send as model)</label>
          <input
            value={newId}
            onChange={(e) => setNewId(e.target.value)}
            placeholder="e.g. hr"
            autoComplete="off"
          />
        </div>
        <p className="muted" style={{ marginTop: 0 }}>
          New rows default to self-hosted → {defaults.local_model}, proprietary →{" "}
          {defaults.proprietary_model}.
        </p>
        <button type="submit" disabled={busy || !newId.trim()}>
          Add domain
        </button>
      </form>
    </div>
  );
}
