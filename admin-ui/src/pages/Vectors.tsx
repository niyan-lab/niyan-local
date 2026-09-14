import { FormEvent, useCallback, useEffect, useState } from "react";
import { api } from "../api/client";

type Collection = { name: string; size?: number; points?: number };

export default function Vectors() {
  const [enabled, setEnabled] = useState(false);
  const [provider, setProvider] = useState("qdrant");
  const [embEnabled, setEmbEnabled] = useState(true);
  const [embModel, setEmbModel] = useState("nomic-embed-text");
  const [health, setHealth] = useState<Record<string, unknown> | null>(null);
  const [collections, setCollections] = useState<Collection[]>([]);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    setError("");
    try {
      const [v, e] = await Promise.all([api.vectorConfig(), api.embeddingsConfig()]);
      setEnabled(Boolean(v.enabled));
      setProvider(String(v.provider || "qdrant"));
      setEmbEnabled(Boolean(e.enabled));
      setEmbModel(String(e.model || "nomic-embed-text"));
      if (v.enabled) {
        try {
          setHealth(await api.vectorHealth());
          const cols = await api.vectorCollections();
          setCollections(cols.collections || []);
        } catch {
          setHealth(null);
          setCollections([]);
        }
      } else {
        setHealth(null);
        setCollections([]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function onSaveVector(e: FormEvent) {
    e.preventDefault();
    setMsg("");
    setError("");
    try {
      const res = await api.putVectorConfig({ enabled, provider });
      setMsg(res.note || "Saved. Recreate stack to apply (`niyan vector provider …`).");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function onSaveEmbeddings(e: FormEvent) {
    e.preventDefault();
    setMsg("");
    setError("");
    try {
      const res = await api.putEmbeddingsConfig({ enabled: embEnabled, model: embModel });
      setMsg(res.note || "Embeddings config saved.");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <p className="page-kicker">Retrieval</p>
          <h1>Vectors & embeddings</h1>
          <p className="muted" style={{ margin: "0.4rem 0 0" }}>
            Qdrant or pgvector for retrieval; pull embeddings with niyan (maps to Ollama), serve via the gateway.
          </p>
        </div>
      </div>
      {error && <p className="error">{error}</p>}
      {msg && <p style={{ color: "var(--ok)" }}>{msg}</p>}

      <form className="panel" onSubmit={onSaveEmbeddings}>
        <h2 style={{ marginTop: 0 }}>Embeddings</h2>
        <div className="inline-toggle">
          <label className="toggle">
            <input
              type="checkbox"
              checked={embEnabled}
              onChange={(e) => setEmbEnabled(e.target.checked)}
            />
            Enabled
          </label>
          <div className="grow">
            <label>Model (niyan → Ollama)</label>
            <input
              value={embModel}
              onChange={(e) => setEmbModel(e.target.value)}
              disabled={!embEnabled}
            />
          </div>
        </div>
        <button type="submit">Save embeddings</button>
      </form>

      <form className="panel" style={{ marginTop: "1rem" }} onSubmit={onSaveVector}>
        <h2 style={{ marginTop: 0 }}>Vector store</h2>
        <div className="inline-toggle">
          <label className="toggle">
            <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
            Enabled
          </label>
          <div className="grow">
            <label>Provider</label>
            <select
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
              disabled={!enabled}
            >
              <option value="qdrant">Qdrant</option>
              <option value="pgvector">pgvector (Postgres)</option>
            </select>
          </div>
        </div>
        <button type="submit">Save vector config</button>
      </form>

      {enabled && (
        <div className="panel" style={{ marginTop: "1rem" }}>
          <h2 style={{ marginTop: 0 }}>Status</h2>
          {health ? (
            <p className="muted">
              Provider: <strong>{String(health.provider || provider)}</strong> —{" "}
              {health.ok ? <span style={{ color: "var(--ok)" }}>healthy</span> : "unreachable"}{" "}
              {health.detail ? `(${String(health.detail)})` : ""}
            </p>
          ) : (
            <p className="muted">Health unavailable — ensure the stack was recreated after enabling.</p>
          )}
          <h3 style={{ fontSize: "0.95rem" }}>Collections</h3>
          <div className="panel-scroll">
            {collections.length === 0 ? (
              <p className="muted">
                No collections yet. Create via API <code>POST /api/vector/collections</code>.
              </p>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Dims</th>
                    <th>Points</th>
                  </tr>
                </thead>
                <tbody>
                  {collections.map((c) => (
                    <tr key={c.name}>
                      <td>{c.name}</td>
                      <td>{c.size ?? "—"}</td>
                      <td>{c.points ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
          <button type="button" className="secondary" style={{ marginTop: "0.75rem" }} onClick={() => refresh()}>
            Refresh
          </button>
        </div>
      )}
    </div>
  );
}
