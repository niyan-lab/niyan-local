import { FormEvent, useEffect, useState } from "react";
import { api } from "../api/client";

type Status = {
  enabled?: boolean;
  reachable?: boolean;
  keys_configured?: boolean;
  public_key_last4?: string;
  secret_key_set?: boolean;
  host?: string;
  ui_url?: string;
};

export default function Observability() {
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [publicKey, setPublicKey] = useState("");
  const [secretKey, setSecretKey] = useState("");
  const [enabled, setEnabled] = useState(true);

  async function refresh() {
    const res = (await api.observability()) as Status;
    setStatus(res);
    setEnabled(res.enabled ?? true);
  }

  useEffect(() => {
    refresh().catch((err) => setError(String(err)));
  }, []);

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setMsg("");
    try {
      const body: Record<string, unknown> = { enabled };
      if (publicKey.trim()) body.public_key = publicKey.trim();
      if (secretKey.trim()) body.secret_key = secretKey.trim();
      const res = (await api.putObservability(body)) as Status;
      setStatus(res);
      setPublicKey("");
      setSecretKey("");
      setMsg("Langfuse keys saved — new traces use them right away.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <p className="page-kicker">Tracing</p>
          <h1>Observability</h1>
          <p className="muted" style={{ margin: "0.4rem 0 0" }}>
            Langfuse for full request traces and cost. Paste your project keys here — they are stored
            in the control-plane database.
          </p>
        </div>
      </div>
      {error && <p className="error">{error}</p>}
      {msg && <p style={{ color: "var(--ok)" }}>{msg}</p>}

      <div style={{ display: "grid", gap: "1rem" }}>
        <div className="panel">
          {status ? (
            <>
              <p style={{ marginTop: 0 }}>
                Reachable:{" "}
                <span className={`badge ${status.reachable ? "up" : "down"}`}>
                  {status.reachable ? "yes" : "no"}
                </span>{" "}
                &nbsp; Keys:{" "}
                <span className={`badge ${status.keys_configured ? "up" : "down"}`}>
                  {status.keys_configured
                    ? `configured ···${status.public_key_last4 || ""}`
                    : "missing"}
                </span>
              </p>
              <a
                className="btn"
                href={String(status.ui_url || "http://localhost:3100")}
                target="_blank"
                rel="noreferrer"
              >
                Open Langfuse
              </a>
            </>
          ) : (
            <p className="muted">Loading…</p>
          )}
        </div>

        <form className="panel" onSubmit={save}>
          <div className="inline-toggle" style={{ marginBottom: "0.75rem" }}>
            <div className="grow">
              <h2 style={{ margin: 0 }}>Langfuse keys</h2>
              <p className="muted" style={{ margin: "0.35rem 0 0" }}>
                In Langfuse: open the UI, create a project, then copy its Public and Secret API keys.
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
            <label>
              Public key{" "}
              {status?.keys_configured ? "(leave blank to keep current)" : ""}
            </label>
            <input
              type="password"
              value={publicKey}
              onChange={(e) => setPublicKey(e.target.value)}
              placeholder={status?.public_key_last4 ? "••••••••" : "pk-lf-…"}
              autoComplete="off"
            />
          </div>
          <div className="field">
            <label>
              Secret key {status?.secret_key_set ? "(leave blank to keep current)" : ""}
            </label>
            <input
              type="password"
              value={secretKey}
              onChange={(e) => setSecretKey(e.target.value)}
              placeholder={status?.secret_key_set ? "••••••••" : "sk-lf-…"}
              autoComplete="off"
            />
          </div>
          <button type="submit" disabled={busy}>
            {busy ? "Saving…" : "Save keys"}
          </button>
        </form>
      </div>
    </div>
  );
}
