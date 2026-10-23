// Runtime config (window.__NIYAN_CONFIG__) may be injected via /config.js.
// On Compose, public/config.js is empty and build-time VITE_* env wins.
//
// Resolution order per URL:
//   1. runtime config      (optional /config.js)
//   2. build-time Vite env (VM / docker-compose)
//   3. "" — callers supply their own loopback default
declare global {
  interface Window {
    __NIYAN_CONFIG__?: { apiBaseUrl?: string; gatewayBaseUrl?: string };
  }
}

// apiBaseUrl may legitimately be "" (same-origin/relative), so the check is
// `typeof === "string"`, not truthiness.
const RUNTIME_API_URL = window.__NIYAN_CONFIG__?.apiBaseUrl;
export const API_BASE_URL =
  typeof RUNTIME_API_URL === "string"
    ? RUNTIME_API_URL
    : import.meta.env.VITE_API_URL || "";

// gatewayBaseUrl is different: "" means "not configured" and falls through,
// because a relative gateway URL would produce a curl snippet the user cannot
// paste into a terminal.
const RUNTIME_GATEWAY_URL = window.__NIYAN_CONFIG__?.gatewayBaseUrl;
export const GATEWAY_BASE_URL =
  typeof RUNTIME_GATEWAY_URL === "string" && RUNTIME_GATEWAY_URL !== ""
    ? RUNTIME_GATEWAY_URL
    : import.meta.env.VITE_GATEWAY_URL || "";

const API_URL = API_BASE_URL;

export type Token = string | null;

export type Benchmark = { suite: string; score: number; unit: string; note: string };

export type SystemRequirements = {
  quantization: string;
  disk_gb: number;
  min_ram_gb: number;
  recommended_ram_gb: number;
  min_vram_gb: number;
  runs_on_cpu: boolean;
  note: string;
};

export type ModelCard = {
  id: string;
  name: string;
  family: string;
  publisher: string;
  parameters: string;
  context_window: number;
  license: string;
  modality: string;
  summary: string;
  strengths: string[];
  limitations: string[];
  benchmarks: Benchmark[];
  requirements: SystemRequirements;
  source_url: string;
  embedding_dimensions: number | null;
};

export type OnPremModel = {
  id: string;
  family: string;
  enabled: boolean;
  installed: boolean;
  loaded: boolean;
  default: boolean;
  managed: boolean;
  size_bytes: number | null;
  parameter_size: string;
  quantization: string;
  modified_at: string;
  card: ModelCard | null;
};

export type OnPremResponse = {
  models: OnPremModel[];
  adopted: string[];
  ollama_reachable: boolean;
};

export type ProprietaryModelCard = {
  id: string;
  name: string;
  provider: string;
  family: string;
  context_window: number;
  max_output_tokens: number | null;
  modality: string;
  summary: string;
  strengths: string[];
  limitations: string[];
  input_per_1m: number;
  output_per_1m: number;
  source_url: string;
};

export type ProviderModel = {
  id: string;
  name: string;
  provider: string;
  family: string;
  enabled: boolean;
  default: boolean;
  configured: boolean;
  in_config: boolean;
  available_live: boolean | null;
  card: ProprietaryModelCard | null;
};

export type ProviderSection = {
  name: string;
  title: string;
  docs_url: string;
  enabled: boolean;
  configured: boolean;
  api_key_last4: string;
  models: ProviderModel[];
  live_refreshed: boolean;
  detail: string;
};

export type ProprietaryResponse = { providers: ProviderSection[] };

let token: Token = localStorage.getItem("niyan_token");

export function setToken(t: Token) {
  token = t;
  if (t) localStorage.setItem("niyan_token", t);
  else localStorage.removeItem("niyan_token");
}

export function getToken() {
  return token;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string> | undefined),
  };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (!res.ok) {
    const text = await res.text();
    const isLogin = path.includes("/api/auth/login");
    if (res.status === 401 && !isLogin) {
      setToken(null);
      if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
        window.location.assign("/login");
      }
    }
    throw new Error(text || res.statusText);
  }
  return res.json();
}

export const api = {
  login: (username: string, password: string) =>
    request<{ access_token: string }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  health: () => request<{ status: string; checks?: Record<string, boolean> }>("/api/health"),
  dashboard: (opts?: { range?: string; from?: string; to?: string; application?: string }) => {
    const q = new URLSearchParams();
    if (opts?.from) q.set("from", opts.from);
    if (opts?.to) q.set("to", opts.to);
    if (opts?.range && !opts?.from) q.set("range", opts.range);
    if (opts?.application && opts.application !== "all") q.set("application", opts.application);
    const qs = q.toString();
    return request<Record<string, unknown>>(`/api/dashboard${qs ? `?${qs}` : ""}`);
  },
  dashboardResources: () =>
    request<{
      generated_at?: string;
      cpu?: { percent?: number | null; count?: number | null; available?: boolean };
      memory?: {
        percent?: number | null;
        used_bytes?: number | null;
        total_bytes?: number | null;
        available?: boolean;
      };
      gpu?: {
        available?: boolean;
        detail?: string;
        devices?: Array<{
          index?: number;
          name?: string;
          utilization_percent?: number;
          memory_used_bytes?: number;
          memory_total_bytes?: number;
          memory_percent?: number;
        }>;
      };
    }>("/api/dashboard/resources"),
  services: () => request<{ services: Array<{ name: string; status: string; healthy: boolean; detail: string }> }>("/api/services"),
  models: () =>
    request<{
      models: Array<{
        id: string;
        family: string;
        provider?: string;
        deployment?: string;
        enabled: boolean;
        installed: boolean;
        default: boolean;
        provider_ready?: boolean;
        can_pull?: boolean;
      }>;
    }>("/api/models"),
  pullModel: (name: string) => request("/api/models/pull", { method: "POST", body: JSON.stringify({ name }) }),
  pullModelStream: async (
    name: string,
    onEvent: (ev: { event: string; data: string }) => void,
  ) => {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (token) headers.Authorization = `Bearer ${token}`;
    const res = await fetch(`${API_URL}/api/models/pull/stream`, {
      method: "POST",
      headers,
      body: JSON.stringify({ name }),
    });
    if (!res.ok || !res.body) {
      throw new Error((await res.text()) || res.statusText);
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    const consume = (raw: string) => {
      let event = "message";
      let data = "";
      for (const line of raw.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (data) onEvent({ event, data });
    };
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const chunks = buf.split("\n\n");
      buf = chunks.pop() || "";
      for (const chunk of chunks) consume(chunk);
    }
    if (buf.trim()) consume(buf);
  },
  deleteModel: (id: string) =>
    request(`/api/models/${encodeURIComponent(id)}`, { method: "DELETE" }),
  loadModel: (id: string) =>
    request(`/api/models/${encodeURIComponent(id)}/load`, { method: "POST" }),
  ejectModel: (id: string) =>
    request(`/api/models/${encodeURIComponent(id)}/eject`, { method: "POST" }),
  updateModel: (
    id: string,
    body: { enabled?: boolean; default?: boolean; provider?: string; family?: string },
  ) => request(`/api/models/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify(body) }),
  onPrem: () => request<OnPremResponse>("/api/inference/on-prem"),
  onPremCatalog: () => request<{ cards: ModelCard[] }>("/api/inference/on-prem/catalog"),
  library: (q: string) =>
    request<{
      results: Array<{
        id: string;
        name: string;
        description: string;
        tags: string[];
        curated: boolean;
      }>;
      source: string;
      detail: string;
    }>(`/api/inference/library?q=${encodeURIComponent(q)}`),
  proprietary: (refresh = false) =>
    request<ProprietaryResponse>(`/api/inference/proprietary${refresh ? "?refresh=true" : ""}`),
  providers: () =>
    request<{
      openai: { enabled: boolean; configured: boolean; api_key_last4: string };
      gemini: { enabled: boolean; configured: boolean; api_key_last4: string };
      anthropic: { enabled: boolean; configured: boolean; api_key_last4: string };
    }>("/api/providers"),
  putProviders: (body: Record<string, unknown>) =>
    request("/api/providers", { method: "PUT", body: JSON.stringify(body) }),
  gateway: () =>
    request<{ port: number; api_keys: string[]; models: unknown[]; api_keys_hint?: string }>("/api/gateway/config"),
  // Keys are read-only (rotate with `niyan secrets rotate gateway-key`); only the port is saved.
  putGateway: (body: { port: number }) =>
    request("/api/gateway/config", { method: "PUT", body: JSON.stringify(body) }),
  guardrails: () => request<Record<string, unknown>>("/api/guardrails/config"),
  putGuardrails: (body: Record<string, unknown>) =>
    request("/api/guardrails/config", { method: "PUT", body: JSON.stringify(body) }),
  observability: () => request<Record<string, unknown>>("/api/observability/status"),
  putObservability: (body: Record<string, unknown>) =>
    request<Record<string, unknown>>("/api/observability", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  enterprisePolicy: () =>
    request<{
      policy: {
        enabled: boolean;
        mode: string;
        domains: Array<{
          id: string;
          enabled: boolean;
          deployment: "local" | "proprietary";
          local_model: string;
          proprietary_model: string;
        }>;
      };
      catalog: {
        local: Array<{ id: string; provider: string; enabled: boolean }>;
        proprietary: Array<{ id: string; provider: string; enabled: boolean; ready?: boolean }>;
      };
      defaults: { local_model: string; proprietary_model: string };
      note?: string;
    }>("/api/enterprise-policy"),
  putEnterprisePolicy: (body: Record<string, unknown>) =>
    request<Record<string, unknown>>("/api/enterprise-policy", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  loadtestPresets: () =>
    request<{
      presets: Array<{ id: string; label: string; path?: string; fields: string[]; note?: string }>;
      limits: {
        max_users: number;
        max_duration_sec: number;
        min_duration_sec: number;
        one_active_run: boolean;
      };
      note?: string;
    }>("/api/loadtests/presets"),
  loadtests: () =>
    request<{
      runs: Array<Record<string, unknown>>;
      active_run_id?: string | null;
    }>("/api/loadtests"),
  createLoadtest: (body: Record<string, unknown>) =>
    request<Record<string, unknown>>("/api/loadtests", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  getLoadtest: (id: string) =>
    request<Record<string, unknown>>(`/api/loadtests/${encodeURIComponent(id)}`),
  stopLoadtest: (id: string) =>
    request<Record<string, unknown>>(`/api/loadtests/${encodeURIComponent(id)}/stop`, {
      method: "POST",
    }),
  downloadLoadtest: async (id: string, format: "json" | "csv") => {
    const headers: Record<string, string> = {};
    if (token) headers.Authorization = `Bearer ${token}`;
    const res = await fetch(
      `${API_URL}/api/loadtests/${encodeURIComponent(id)}/download?format=${format}`,
      { headers },
    );
    if (!res.ok) {
      const text = await res.text();
      throw new Error(text || res.statusText);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `niyan-loadtest-${id}.${format}`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },
  viewLoadtestReport: async (id: string) => {
    const headers: Record<string, string> = {};
    if (token) headers.Authorization = `Bearer ${token}`;
    const res = await fetch(
      `${API_URL}/api/loadtests/${encodeURIComponent(id)}/report`,
      { headers },
    );
    if (!res.ok) {
      const text = await res.text();
      throw new Error(text || res.statusText);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const win = window.open(url, "_blank", "noopener,noreferrer");
    if (!win) {
      // Popup blocked — fall back to same-tab navigation via temp link
      const a = document.createElement("a");
      a.href = url;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      document.body.appendChild(a);
      a.click();
      a.remove();
    }
    // Revoke later so the new tab can load the blob
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
  },
  config: () => request<Record<string, unknown>>("/api/config"),
  putConfig: (body: Record<string, unknown>) =>
    request("/api/config", { method: "PUT", body: JSON.stringify(body) }),
  embeddingsConfig: () => request<Record<string, unknown>>("/api/embeddings/config"),
  putEmbeddingsConfig: (body: Record<string, unknown>) =>
    request<{ note?: string }>("/api/embeddings/config", { method: "PUT", body: JSON.stringify(body) }),
  vectorConfig: () => request<Record<string, unknown>>("/api/vector/config"),
  putVectorConfig: (body: Record<string, unknown>) =>
    request<{ note?: string }>("/api/vector/config", { method: "PUT", body: JSON.stringify(body) }),
  vectorHealth: () => request<Record<string, unknown>>("/api/vector/health"),
  vectorCollections: () =>
    request<{ collections: Array<{ name: string; size?: number; points?: number }> }>("/api/vector/collections"),
};
