import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { Pulse } from "./Pulse";

const SERVICE_LABELS: Record<string, string> = {
  gateway: "Gateway",
  ollama: "Ollama",
  langfuse: "Langfuse",
  guard_llm: "LLM Guard",
  guard_nemo: "NeMo",
  qdrant: "Qdrant",
};

export function serviceLabel(name: string): string {
  return SERVICE_LABELS[name] ?? name.replace(/_/g, " ");
}

/** "down" means the gateway itself is unreachable — nothing can serve traffic. */
export type HealthLevel = "checking" | "operational" | "degraded" | "down";

export type StackHealth = {
  level: HealthLevel;
  checks: Record<string, boolean>;
  down: string[];
  total: number;
  checkedAt: number | null;
  refresh: () => void;
};

/**
 * Polls /api/health so the shell can show real status. Pauses while the tab is
 * hidden so a backgrounded console isn't hammering the API all day.
 */
export function useStackHealth(intervalMs = 15000): StackHealth {
  const [checks, setChecks] = useState<Record<string, boolean>>({});
  const [level, setLevel] = useState<HealthLevel>("checking");
  const [checkedAt, setCheckedAt] = useState<number | null>(null);
  const alive = useRef(true);

  const load = useCallback(async () => {
    try {
      const res = await api.health();
      if (!alive.current) return;
      const next = res.checks ?? {};
      const gatewayUp = next.gateway !== false;
      const anyDown = Object.values(next).some((ok) => !ok);
      setChecks(next);
      setLevel(!gatewayUp ? "down" : anyDown ? "degraded" : "operational");
      setCheckedAt(Date.now());
    } catch {
      if (!alive.current) return;
      setChecks({});
      setLevel("down");
      setCheckedAt(Date.now());
    }
  }, []);

  useEffect(() => {
    alive.current = true;
    load();
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") load();
    }, intervalMs);
    const onVisible = () => {
      if (document.visibilityState === "visible") load();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      alive.current = false;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [load, intervalMs]);

  const down = Object.entries(checks)
    .filter(([, ok]) => !ok)
    .map(([name]) => name);

  return { level, checks, down, total: Object.keys(checks).length, checkedAt, refresh: load };
}

function summary(health: StackHealth): string {
  switch (health.level) {
    case "checking":
      return "checking";
    case "operational":
      return "operational";
    case "down":
      return "offline";
    default:
      return `${health.down.length} degraded`;
  }
}

function tooltip(health: StackHealth): string {
  if (health.level === "checking") return "Checking stack health…";
  if (health.level === "down") return "Gateway unreachable — the stack cannot serve requests.";
  if (health.level === "operational") return `All ${health.total} services responding.`;
  return `Not responding: ${health.down.map(serviceLabel).join(", ")}`;
}

/**
 * Global status indicator in the topbar. Click-through lands on the hardware
 * tab, which carries the per-service detail.
 */
export function StackStatusChip({ health }: { health: StackHealth }) {
  const nav = useNavigate();
  return (
    <button
      type="button"
      className={`live-chip live-chip--${health.level}`}
      title={tooltip(health)}
      onClick={() => nav("/?tab=hardware")}
    >
      {health.level === "operational" ? <Pulse /> : null}
      <span className="live-dot" aria-hidden />
      <span className="live-text">{summary(health)}</span>
    </button>
  );
}
