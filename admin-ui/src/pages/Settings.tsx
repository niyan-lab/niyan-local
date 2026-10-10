import { FormEvent, useEffect, useState } from "react";
import { api } from "../api/client";

export default function Settings() {
  const [raw, setRaw] = useState("");
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api.config()
      .then((cfg) => setRaw(JSON.stringify(cfg, null, 2)))
      .catch((err) => setError(String(err)));
  }, []);

  async function onSave(e: FormEvent) {
    e.preventDefault();
    setMsg("");
    setError("");
    try {
      const parsed = JSON.parse(raw);
      await api.putConfig(parsed);
      setMsg("Configuration saved");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <p className="page-kicker">Configuration</p>
          <h1>Settings</h1>
          <p className="muted" style={{ margin: "0.4rem 0 0" }}>
            Edit validated runtime config via the control plane (JSON view).
          </p>
        </div>
      </div>
      {error && <p className="error">{error}</p>}
      {msg && <p style={{ color: "var(--ok)" }}>{msg}</p>}
      <form className="panel" onSubmit={onSave}>
        <textarea rows={28} value={raw} onChange={(e) => setRaw(e.target.value)} style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", fontSize: "0.85rem" }} />
        <div className="row" style={{ marginTop: "0.75rem" }}>
          <button type="submit">Save config</button>
        </div>
      </form>
    </div>
  );
}
