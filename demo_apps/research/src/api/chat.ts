import type { ConnectionConfig } from "../connection";

export type ChatMessage = { role: "system" | "user" | "assistant"; content: string };

function friendlyError(status: number, detail: unknown): string {
  const text =
    typeof detail === "string"
      ? detail
      : detail && typeof detail === "object"
        ? JSON.stringify(detail)
        : "";
  if (status === 401) return "Invalid API key.";
  if (status === 502) return "Cannot reach API endpoint.";
  return text.slice(0, 280) || `Request failed (${status})`;
}

async function parseError(res: Response): Promise<string> {
  try {
    const data = await res.json();
    return friendlyError(res.status, data.detail ?? data.error ?? data);
  } catch {
    return friendlyError(res.status, await res.text().catch(() => ""));
  }
}

function baseHeaders(cfg: Pick<ConnectionConfig, "gatewayUrl" | "apiKey">) {
  return {
    Authorization: `Bearer ${cfg.apiKey}`,
    "Content-Type": "application/json",
    "X-Api-Base": cfg.gatewayUrl.replace(/\/$/, ""),
    "X-Niyan-Application": "research",
  };
}

export async function runBrief(
  cfg: ConnectionConfig,
  prompt: string,
  signal?: AbortSignal
): Promise<string> {
  const messages: ChatMessage[] = [
    {
      role: "system",
      content:
        "You are a research analyst for Praxis. Structure findings clearly, note uncertainty, and never invent citations.",
    },
    { role: "user", content: prompt },
  ];

  const res = await fetch("/api-proxy/v1/chat/completions", {
    method: "POST",
    headers: baseHeaders(cfg),
    body: JSON.stringify({
      model: cfg.model,
      messages,
      stream: false,
      temperature: 0.4,
    }),
    signal,
  });

  if (!res.ok) throw new Error(await parseError(res));
  const data = await res.json();
  return String(data?.choices?.[0]?.message?.content ?? "");
}

export async function probeGateway(
  cfg: Pick<ConnectionConfig, "gatewayUrl" | "apiKey">
): Promise<{ ok: boolean; message: string }> {
  const base = cfg.gatewayUrl.replace(/\/$/, "");
  if (!base) return { ok: false, message: "Enter a Base URL." };

  try {
    const res = await fetch("/api-proxy/health", {
      method: "GET",
      headers: { "X-Api-Base": base },
    });
    if (!res.ok) return { ok: false, message: await parseError(res) };
    return { ok: true, message: "Gateway is running." };
  } catch (e) {
    return { ok: false, message: e instanceof Error ? e.message : "Unreachable" };
  }
}

export async function listModels(
  cfg: Pick<ConnectionConfig, "gatewayUrl" | "apiKey">
): Promise<string[]> {
  const res = await fetch("/api-proxy/v1/models", {
    method: "GET",
    headers: baseHeaders(cfg),
  });
  if (!res.ok) throw new Error(await parseError(res));
  const data = await res.json();
  const ids = (data?.data || [])
    .map((m: { id?: string }) => m.id)
    .filter((id: unknown): id is string => typeof id === "string" && id.length > 0);
  return Array.from(new Set(ids)).sort((a, b) => a.localeCompare(b));
}

export function sortModelsForDomain(domain: string, models: string[]): string[] {
  const localHint = /llama|gemma|mistral|qwen|phi|ollama/i;
  const cloudHint = /gpt|gemini|claude|openai/i;
  const preferLocal = ["finance", "legal", "support", "summary"].includes(domain);
  const preferCloud = domain === "research";

  return [...models].sort((a, b) => {
    const score = (id: string) => {
      if (preferLocal) return localHint.test(id) ? 0 : cloudHint.test(id) ? 2 : 1;
      if (preferCloud) return cloudHint.test(id) ? 0 : localHint.test(id) ? 2 : 1;
      return 1;
    };
    return score(a) - score(b) || a.localeCompare(b);
  });
}
