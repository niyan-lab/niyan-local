import { useEffect, useState } from "react";
import { listModels, probeGateway, sortModelsForDomain } from "./api/chat";
import { ConnectionConfig, POLICY_DOMAINS } from "./connection";

type Props = {
  draft: ConnectionConfig;
  setDraft: (c: ConnectionConfig) => void;
  onClose: () => void;
  onSave: () => void;
};

export function SettingsModal({ draft, setDraft, onClose, onSave }: Props) {
  const [status, setStatus] = useState<"idle" | "checking" | "up" | "down">("idle");
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [models, setModels] = useState<string[]>([]);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [loadingModels, setLoadingModels] = useState(false);

  useEffect(() => {
    const url = draft.gatewayUrl.trim();
    if (!url) {
      setStatus("idle");
      setStatusMsg(null);
      setModels([]);
      return;
    }

    let cancelled = false;
    const t = window.setTimeout(async () => {
      setStatus("checking");
      setStatusMsg("Checking Base URL…");
      const probe = await probeGateway(draft);
      if (cancelled) return;
      if (!probe.ok) {
        setStatus("down");
        setStatusMsg(probe.message);
        setModels([]);
        return;
      }
      setStatus("up");
      setStatusMsg(probe.message);

      if (!draft.apiKey.trim()) {
        setModelsError("Enter an API key to load models.");
        setModels([]);
        return;
      }

      setLoadingModels(true);
      setModelsError(null);
      try {
        const ids = await listModels(draft);
        if (!cancelled) setModels(ids);
      } catch (e) {
        if (!cancelled) {
          setModels([]);
          setModelsError(e instanceof Error ? e.message : "Could not load models");
        }
      } finally {
        if (!cancelled) setLoadingModels(false);
      }
    }, 450);

    return () => {
      cancelled = true;
      window.clearTimeout(t);
    };
  }, [draft.gatewayUrl, draft.apiKey]);

  const sortedModels = draft.domain ? sortModelsForDomain(draft.domain, models) : models;
  const canSave = Boolean(draft.gatewayUrl.trim() && draft.apiKey.trim() && draft.model.trim());

  return (
    <div className="modal-backdrop" role="dialog" aria-label="Settings">
      <div className="modal settings-modal">
        <div className="settings-head">
          <h2>Settings</h2>
          <button type="button" className="ghost" onClick={onClose}>
            Close
          </button>
        </div>

        <div className="settings-scroll">
          <section className="settings-section">
            <h3>1 · Base URL</h3>
            <p className="modal-lede">Point at your running API gateway. Domains appear when it is up.</p>
            <label>
              Base URL
              <input
                value={draft.gatewayUrl}
                onChange={(e) =>
                  setDraft({ ...draft, gatewayUrl: e.target.value, domain: "", model: "" })
                }
                placeholder="http://127.0.0.1:4000"
                autoFocus
              />
            </label>
            <label>
              API key
              <input
                type="password"
                autoComplete="off"
                value={draft.apiKey}
                onChange={(e) => setDraft({ ...draft, apiKey: e.target.value })}
                placeholder="sk-…"
              />
            </label>
            <p
              className={
                status === "up" ? "conn-status ok" : status === "down" ? "conn-status bad" : "conn-status"
              }
            >
              {status === "checking" && "Checking…"}
              {statusMsg}
            </p>
          </section>

          {status === "up" && (
            <section className="settings-section">
              <h3>2 · Domain</h3>
              <p className="modal-lede">Choose a policy domain (scroll). Then pick a model.</p>
              <div className="picker-scroll" role="listbox" aria-label="Domains">
                {POLICY_DOMAINS.map((d) => (
                  <button
                    key={d.id}
                    type="button"
                    role="option"
                    aria-selected={draft.domain === d.id}
                    className={draft.domain === d.id ? "picker-item active" : "picker-item"}
                    onClick={() =>
                      setDraft({
                        ...draft,
                        domain: d.id,
                        model: draft.domain === d.id && draft.model ? draft.model : d.id,
                      })
                    }
                  >
                    <strong>{d.label}</strong>
                    <span>{d.hint}</span>
                    <code>{d.id}</code>
                  </button>
                ))}
              </div>
            </section>
          )}

          {status === "up" && draft.domain && (
            <section className="settings-section">
              <h3>3 · Model</h3>
              <p className="modal-lede">
                Models available on this gateway for <code>{draft.domain}</code>.
              </p>
              {loadingModels && <p className="conn-status">Loading models…</p>}
              {modelsError && <p className="conn-status bad">{modelsError}</p>}
              <div className="picker-scroll models" role="listbox" aria-label="Models">
                <button
                  type="button"
                  role="option"
                  aria-selected={draft.model === draft.domain}
                  className={draft.model === draft.domain ? "picker-item active" : "picker-item"}
                  onClick={() => setDraft({ ...draft, model: draft.domain })}
                >
                  <strong>Use domain route</strong>
                  <span>Lets the gateway pick the model for this domain</span>
                  <code>{draft.domain}</code>
                </button>
                {sortedModels.map((id) => (
                  <button
                    key={id}
                    type="button"
                    role="option"
                    aria-selected={draft.model === id}
                    className={draft.model === id ? "picker-item active" : "picker-item"}
                    onClick={() => setDraft({ ...draft, model: id })}
                  >
                    <strong>{id}</strong>
                    <span>Concrete model id</span>
                    <code>{id}</code>
                  </button>
                ))}
                {!loadingModels && !modelsError && sortedModels.length === 0 && (
                  <p className="modal-lede">No models returned — check API key or enable models upstream.</p>
                )}
              </div>
            </section>
          )}
        </div>

        <div className="modal-actions sticky-actions">
          <div className="selection-summary">
            {draft.domain && (
              <span>
                Domain <code>{draft.domain}</code>
              </span>
            )}
            {draft.model && (
              <span>
                Model <code>{draft.model}</code>
              </span>
            )}
          </div>
          <button type="button" className="ghost" onClick={onClose}>
            Cancel
          </button>
          <button type="button" className="cta" disabled={!canSave} onClick={onSave}>
            Save
          </button>
        </div>
      </div>
    </div>
  );
}
