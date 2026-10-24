export type ConnectionConfig = {
  gatewayUrl: string;
  apiKey: string;
  domain: string;
  model: string;
};

const STORAGE_KEY = "fiducia-api-settings";

export function defaultConnection(): ConnectionConfig {
  return {
    gatewayUrl: import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:4000",
    apiKey: import.meta.env.VITE_API_KEY || "",
    domain: import.meta.env.VITE_DOMAIN || "finance",
    model: import.meta.env.VITE_MODEL || "finance",
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

/** Policy domain ids commonly configured on a Niyan gateway. */
export const POLICY_DOMAINS = [
  { id: "finance", label: "Finance", hint: "Client revenue · usually local model" },
  { id: "research", label: "Research", hint: "Usually proprietary model" },
  { id: "marketing", label: "Marketing", hint: "Campaign & copy" },
  { id: "sales", label: "Sales", hint: "Pipeline support" },
  { id: "summary", label: "Summary", hint: "Condensed briefs" },
  { id: "support", label: "Support", hint: "Ticket assist" },
  { id: "legal", label: "Legal", hint: "Contract review" },
] as const;
