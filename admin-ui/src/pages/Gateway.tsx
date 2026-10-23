import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, GATEWAY_BASE_URL, type OnPremModel, type ProviderSection } from "../api/client";

type Snippet = {
  id: string;
  title: string;
  note: string;
  lang: "bash" | "python";
  code: string;
};

function shellQuote(value: string): string {
  return `'${value.replace(/'/g, `'\\''`)}'`;
}

function CopyBlock({ snippet }: { snippet: Snippet }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(snippet.code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      /* ignore — some browsers block clipboard without a user gesture */
    }
  }

  return (
    <article className="snippet">
      <header className="snippet-head">
        <div>
          <h3>{snippet.title}</h3>
          <p className="muted">{snippet.note}</p>
        </div>
        <button type="button" className="secondary" onClick={copy}>
          {copied ? "Copied" : "Copy"}
        </button>
      </header>
      <pre className="code-block">
        <code>{snippet.code}</code>
      </pre>
    </article>
  );
}

export default function Gateway() {
  const [port, setPort] = useState(4000);
  const [keys, setKeys] = useState("");
  const [onPrem, setOnPrem] = useState<OnPremModel[]>([]);
  const [providers, setProviders] = useState<ProviderSection[]>([]);
  const [domain, setDomain] = useState("finance");
  const [embedModel, setEmbedModel] = useState("nomic-embed-text");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    Promise.all([
      api.gateway(),
      api.onPrem().catch(() => ({ models: [] as OnPremModel[] })),
      api.proprietary().catch(() => ({ providers: [] as ProviderSection[] })),
      api.enterprisePolicy().catch(() => null),
      api.embeddingsConfig().catch(() => null),
    ])
      .then(([gateway, local, proprietary, policy, embeddings]) => {
        setPort(gateway.port);
        setKeys((gateway.api_keys || []).join("\n"));
        setOnPrem(local.models || []);
        setProviders(proprietary.providers || []);
        const firstDomain = policy?.policy.domains.find((d) => d.enabled)?.id;
        if (firstDomain) setDomain(firstDomain);
        const emb = (embeddings as { model?: string } | null)?.model;
        if (emb) setEmbedModel(emb);
      })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  const apiKey = keys.split("\n").map((k) => k.trim()).filter(Boolean)[0] || "<your-api-key>";
  // Behind an ingress the gateway is reached at <ingress host>/v1, not on a
  // published port; GATEWAY_BASE_URL carries that. The port field below still
  // configures the container's listen port, which is not what callers dial.
  const origin = GATEWAY_BASE_URL || `http://127.0.0.1:${port}`;

  const chatModel = useMemo(() => {
    const local = onPrem.find(
      (m) => m.enabled && m.installed && (m.card?.modality ?? m.family) !== "embedding",
    );
    if (local) return local.id;
    const cloud = providers.flatMap((p) => p.models).find((m) => m.enabled);
    return cloud?.id || "llama3.2:3b";
  }, [onPrem, providers]);

  const snippets = useMemo<Snippet[]>(() => {
    const auth = `-H "Authorization: Bearer ${apiKey}"`;
    const json = `-H "Content-Type: application/json"`;
    const out: Snippet[] = [
      {
        id: "models",
        title: "List models",
        note: "Everything currently routed through this gateway — local and cloud.",
        lang: "bash",
        code: `curl -sS ${origin}/v1/models \\\n  ${auth}`,
      },
      {
        id: "chat",
        title: "Chat completion",
        note: `Uses ${chatModel}, which is enabled on this install.`,
        lang: "bash",
        code: `curl -sS ${origin}/v1/chat/completions \\\n  ${auth} \\\n  ${json} \\\n  -d ${shellQuote(
          JSON.stringify(
            {
              model: chatModel,
              messages: [{ role: "user", content: "Summarise Niyan in one sentence." }],
            },
            null,
            2,
          ),
        )}`,
      },
      {
        id: "domain",
        title: "Chat via a policy domain",
        note: `Send the domain name as model. Policy currently maps "${domain}" on the Policy page.`,
        lang: "bash",
        code: `curl -sS ${origin}/v1/chat/completions \\\n  ${auth} \\\n  ${json} \\\n  -d ${shellQuote(
          JSON.stringify(
            {
              model: domain,
              messages: [{ role: "user", content: "What should I watch for in this quarter's numbers?" }],
            },
            null,
            2,
          ),
        )}`,
      },
      {
        id: "embed",
        title: "Embeddings",
        note: `Default embedding model is ${embedModel}. Create vector collections with matching dimensions.`,
        lang: "bash",
        code: `curl -sS ${origin}/v1/embeddings \\\n  ${auth} \\\n  ${json} \\\n  -d ${shellQuote(
          JSON.stringify({ model: embedModel, input: "Niyan local RAG stack" }, null, 2),
        )}`,
      },
      {
        id: "sdk",
        title: "Python SDK",
        note: "Any OpenAI-compatible client works. Point base_url at this gateway.",
        lang: "python",
        code: `from openai import OpenAI

client = OpenAI(
    base_url="${origin}/v1",
    api_key="${apiKey}",
)

chat = client.chat.completions.create(
    model="${chatModel}",
    messages=[{"role": "user", "content": "Summarise Niyan in one sentence."}],
)
print(chat.choices[0].message.content)`,
      },
    ];
    return out;
  }, [apiKey, chatModel, domain, embedModel, origin]);

  async function onSave(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg("");
    setError("");
    try {
      await api.putGateway({
        port,
        api_keys: keys.split("\n").map((k) => k.trim()).filter(Boolean),
      });
      setMsg("Gateway port and keys saved. Recreate the stack if the port changed.");
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
          <p className="page-kicker">How to call this stack</p>
          <h1>Gateway</h1>
          <p className="muted" style={{ margin: "0.4rem 0 0" }}>
            OpenAI-compatible endpoint at <code>{origin}/v1</code>. Snippets below use a model and
            key from this install — copy and run them as-is.
          </p>
        </div>
        <div className="head-stats">
          <span>
            <strong>{origin}</strong>
          </span>
          <span className="muted">key {apiKey.slice(0, 8)}…</span>
        </div>
      </div>

      {error && <p className="error">{error}</p>}
      {msg && <p style={{ color: "var(--ok)" }}>{msg}</p>}

      <div className="snippet-list">
        {snippets.map((snippet) => (
          <CopyBlock key={snippet.id} snippet={snippet} />
        ))}
      </div>

      <p className="muted" style={{ marginTop: "1rem" }}>
        Enable or pull models on <Link to="/inference/on-prem">On-prem</Link> and{" "}
        <Link to="/inference/proprietary">Proprietary</Link>. Domain names are mapped on{" "}
        <Link to="/enterprise-policy">Policy</Link>.
      </p>

      <div className="panel" style={{ marginTop: "1.25rem" }}>
        <div className="inline-toggle">
          <div className="grow">
            <h2 style={{ margin: 0 }}>Port and API keys</h2>
            <p className="muted" style={{ margin: "0.35rem 0 0" }}>
              Changing the listen port needs a stack recreate. Keys authenticate every{" "}
              <code>/v1</code> request.
            </p>
          </div>
          <button type="button" className="secondary" onClick={() => setShowAdvanced((v) => !v)}>
            {showAdvanced ? "Hide" : "Edit"}
          </button>
        </div>
        {showAdvanced ? (
          <form onSubmit={onSave} style={{ marginTop: "0.9rem" }}>
            <div className="field">
              <label htmlFor="gw-port">Proxy port</label>
              <input
                id="gw-port"
                type="number"
                value={port}
                onChange={(e) => setPort(Number(e.target.value))}
              />
            </div>
            <div className="field">
              <label htmlFor="gw-keys">API keys (one per line)</label>
              <textarea
                id="gw-keys"
                rows={4}
                value={keys}
                onChange={(e) => setKeys(e.target.value)}
              />
            </div>
            <button type="submit" disabled={busy}>
              {busy ? "Saving…" : "Save"}
            </button>
          </form>
        ) : null}
      </div>
    </div>
  );
}
