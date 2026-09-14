export type ConnectionConfig = {
  gatewayUrl: string;
  apiKey: string;
  domain: string;
  model: string;
};

const STORAGE_KEY = "praxis-api-settings";

export function defaultConnection(): ConnectionConfig {
  return {
    gatewayUrl: import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:4000",
    apiKey: import.meta.env.VITE_API_KEY || "sk-niyan-local",
    domain: import.meta.env.VITE_DOMAIN || "research",
    model: import.meta.env.VITE_MODEL || "research",
  };
}

export function loadConnection(): ConnectionConfig {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return defaultConnection();
    const parsed = JSON.parse(raw) as Partial<ConnectionConfig>;
    const merged = { ...defaultConnection(), ...parsed };
    if (!merged.domain && merged.model) merged.domain = merged.model;
    return merged;
  } catch {
    return defaultConnection();
  }
}

export function saveConnection(cfg: ConnectionConfig) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(cfg));
}

export const POLICY_DOMAINS = [
  { id: "research", label: "Research", hint: "Usually proprietary model" },
  { id: "finance", label: "Finance", hint: "Usually local / private" },
  { id: "marketing", label: "Marketing", hint: "Campaign & copy" },
  { id: "sales", label: "Sales", hint: "Pipeline support" },
  { id: "summary", label: "Summary", hint: "Condensed briefs" },
  { id: "support", label: "Support", hint: "Ticket assist" },
  { id: "legal", label: "Legal", hint: "Contract review" },
] as const;
