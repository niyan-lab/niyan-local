import { FormEvent, useEffect, useState } from "react";
import { api } from "../api/client";

export default function Guardrails() {
  const [enabled, setEnabled] = useState(true);
  const [provider, setProvider] = useState("llm_guard");
  const [onFailure, setOnFailure] = useState("allow");
  const [scanners, setScanners] = useState("prompt_injection,pii");
  const [outputScanners, setOutputScanners] = useState("pii,toxicity,secrets");
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .guardrails()
      .then((g: any) => {
        setEnabled(Boolean(g.enabled));
        setProvider(g.provider || "llm_guard");
        setOnFailure(g.on_failure || "allow");
        setScanners((g.llm_guard?.scanners || []).join(","));
        setOutputScanners((g.llm_guard?.output_scanners || ["pii", "toxicity", "secrets"]).join(","));
      })
      .catch((err) => setError(String(err)));
  }, []);

  async function onSave(e: FormEvent) {
    e.preventDefault();
    setMsg("");
    setError("");
    try {
      const res: any = await api.putGuardrails({
        enabled,
        provider,
        on_failure: onFailure,
        scanners: scanners
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        output_scanners: outputScanners
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
      });
      setMsg(
        res.note ||
          "Saved. Recreate stack to apply provider switch (`niyan guardrails provider …`).",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <p className="page-kicker">Safety</p>
          <h1>Guardrails</h1>
          <p className="muted" style={{ margin: "0.4rem 0 0" }}>
            Incoming prompts are scanned before the model, and the model reply is scanned before it
            reaches the client. Choose exactly one provider: LLM Guard or NeMo.
          </p>
        </div>
      </div>
      {error && <p className="error">{error}</p>}
      {msg && <p style={{ color: "var(--ok)" }}>{msg}</p>}
      <form className="panel" onSubmit={onSave}>
        <div className="inline-toggle">
          <label className="toggle">
            <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
            Enabled
          </label>
          <div className="grow">
            <label>Provider</label>
            <select value={provider} onChange={(e) => setProvider(e.target.value)} disabled={!enabled}>
              <option value="llm_guard">LLM Guard</option>
              <option value="nemo">NeMo Guardrails</option>
            </select>
          </div>
          <div className="grow">
            <label>On failure</label>
            <select value={onFailure} onChange={(e) => setOnFailure(e.target.value)} disabled={!enabled}>
              <option value="allow">allow (local DX)</option>
              <option value="block">block</option>
            </select>
          </div>
        </div>
        <div className="field">
          <label>Input scanners (comma-separated)</label>
          <input
            value={scanners}
            onChange={(e) => setScanners(e.target.value)}
            disabled={!enabled || provider !== "llm_guard"}
            placeholder="prompt_injection,pii"
          />
          <p className="muted" style={{ margin: "0.35rem 0 0", fontSize: "0.8rem" }}>
            Runs on the user prompt before LiteLLM. Typical: <code>prompt_injection</code>,{" "}
            <code>pii</code>.
          </p>
        </div>
        <div className="field">
          <label>Output scanners (comma-separated)</label>
          <input
            value={outputScanners}
            onChange={(e) => setOutputScanners(e.target.value)}
            disabled={!enabled || provider !== "llm_guard"}
            placeholder="pii,toxicity,secrets"
          />
          <p className="muted" style={{ margin: "0.35rem 0 0", fontSize: "0.8rem" }}>
            Runs on the model reply before it is returned. Typical: <code>pii</code>,{" "}
            <code>toxicity</code>, <code>secrets</code>. PII/secrets are redacted; toxicity blocks.
          </p>
        </div>
        <button type="submit">Save</button>
      </form>
    </div>
  );
}
