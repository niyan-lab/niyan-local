import { useEffect, useState } from "react";
import { api, type ModelCard } from "./api/client";

export type PullJob = {
  id: string;
  name: string;
  card: ModelCard | null;
  status: string;
  percent: number | null;
  completed: number | null;
  total: number | null;
  error: string | null;
  startedAt: number;
};

type Listener = () => void;

const jobs = new Map<string, PullJob>();
const listeners = new Set<Listener>();

function emit() {
  listeners.forEach((listener) => listener());
}

export function listPulls(): PullJob[] {
  return [...jobs.values()].sort((a, b) => b.startedAt - a.startedAt);
}

export function getPull(id: string): PullJob | undefined {
  return jobs.get(id);
}

export function usePulls(): PullJob[] {
  const [, bump] = useState(0);
  useEffect(() => {
    const listener = () => bump((n) => n + 1);
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  }, []);
  return listPulls();
}

function upsert(id: string, patch: Partial<PullJob>): PullJob {
  const current = jobs.get(id);
  const next: PullJob = {
    id,
    name: current?.name ?? id,
    card: current?.card ?? null,
    status: current?.status ?? "starting",
    percent: current?.percent ?? null,
    completed: current?.completed ?? null,
    total: current?.total ?? null,
    error: current?.error ?? null,
    startedAt: current?.startedAt ?? Date.now(),
    ...patch,
  };
  jobs.set(id, next);
  emit();
  return next;
}

/**
 * Start an Ollama pull that outlives page navigation.
 *
 * Progress is tracked here rather than in On-prem local state so leaving the
 * tab does not abort the stream or hide the bar.
 */
export function startPull(
  id: string,
  opts?: { card?: ModelCard | null; name?: string },
): Promise<void> {
  const existing = jobs.get(id);
  if (existing && !existing.error) {
    return Promise.resolve();
  }

  upsert(id, {
    name: opts?.name || opts?.card?.name || id,
    card: opts?.card ?? existing?.card ?? null,
    status: "starting",
    percent: null,
    completed: null,
    total: null,
    error: null,
    startedAt: Date.now(),
  });

  return api
    .pullModelStream(id, (ev) => {
      if (ev.event === "progress") {
        const data = JSON.parse(ev.data) as {
          status?: string;
          percent?: number | null;
          completed?: number | null;
          total?: number | null;
        };
        upsert(id, {
          status: data.status || "downloading",
          percent: data.percent ?? null,
          completed: data.completed ?? null,
          total: data.total ?? null,
        });
      } else if (ev.event === "error") {
        const data = JSON.parse(ev.data) as { detail?: string };
        throw new Error(data.detail || "pull failed");
      }
    })
    .then(() => {
      upsert(id, { status: "success", percent: 100, error: null });
      window.setTimeout(() => {
        const job = jobs.get(id);
        if (job && job.status === "success") {
          jobs.delete(id);
          emit();
        }
      }, 2500);
    })
    .catch((err) => {
      upsert(id, {
        status: "error",
        error: err instanceof Error ? err.message : String(err),
      });
    });
}
