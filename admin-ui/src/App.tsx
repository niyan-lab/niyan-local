import { NavLink, Navigate, Route, Routes, useLocation, useNavigate, Link } from "react-router-dom";
import { FormEvent, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { api, API_BASE_URL, getToken, setToken } from "./api/client";
import {
  THEME_STORAGE_KEY,
  applyTheme,
  readThemePreference,
  resolveTheme,
  type ResolvedTheme,
  type ThemePreference,
} from "./theme";
import { Atmosphere } from "./components/Atmosphere";
// Show the host the SPA actually calls. API_BASE_URL is "" for same-origin
// deployments, where the browser's own host is the answer.
const ENDPOINT_LABEL = (() => {
  try {
    return new URL(API_BASE_URL || window.location.origin).host;
  } catch {
    return window.location.host;
  }
})();

import { BrandMark } from "./components/BrandMark";
import { CommandPalette, type PaletteItem } from "./components/CommandPalette";
import { PageTurn } from "./components/PageTurn";
import { Schematic } from "./components/Schematic";
import { StackStatusChip, useStackHealth } from "./components/StackStatus";
import {
  IconDashboard,
  IconGateway,
  IconGuardrails,
  IconLoad,
  IconModels,
  IconObservability,
  IconPolicy,
  IconProviders,
  IconSearch,
  IconSettings,
  IconVectors,
} from "./components/icons";
import Dashboard from "./pages/Dashboard";
import OnPrem from "./pages/OnPrem";
import Proprietary from "./pages/Proprietary";
import Gateway from "./pages/Gateway";
import Guardrails from "./pages/Guardrails";
import Observability from "./pages/Observability";
import EnterprisePolicy from "./pages/EnterprisePolicy";
import LoadTesting from "./pages/LoadTesting";
import Vectors from "./pages/Vectors";
import Settings from "./pages/Settings";
import { usePulls } from "./pulls";

function useTheme() {
  const [preference, setPreference] = useState<ThemePreference>(() => readThemePreference());
  const [resolved, setResolved] = useState<ResolvedTheme>(() => resolveTheme(readThemePreference()));

  useEffect(() => {
    const next = resolveTheme(preference);
    setResolved(next);
    applyTheme(next);
    try {
      localStorage.setItem(THEME_STORAGE_KEY, preference);
    } catch {
      /* ignore */
    }

    if (preference !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      const systemTheme = resolveTheme("system");
      setResolved(systemTheme);
      applyTheme(systemTheme);
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [preference]);

  const toggle = useCallback(() => {
    setPreference(resolveTheme(readThemePreference()) === "dark" ? "light" : "dark");
  }, []);

  return { preference, resolved, toggle };
}

function ThemeToggle({
  resolved,
  onToggle,
  className = "",
}: {
  resolved: ResolvedTheme;
  onToggle: () => void;
  className?: string;
}) {
  const isDark = resolved === "dark";
  return (
    <button
      type="button"
      className={`theme-toggle ${className}`.trim()}
      onClick={onToggle}
      aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
      title={isDark ? "Switch to light mode" : "Switch to dark mode"}
    >
      <span className="theme-toggle-track" aria-hidden>
        <span className="theme-toggle-thumb">
          {isDark ? (
            <svg viewBox="0 0 24 24">
              <path d="M21 14.5A8.5 8.5 0 0 1 9.5 3 7 7 0 1 0 21 14.5z" />
            </svg>
          ) : (
            <svg viewBox="0 0 24 24">
              <circle cx="12" cy="12" r="4.2" />
              <path d="M12 2.4v2.1M12 19.5v2.1M4.6 4.6l1.5 1.5M17.9 17.9l1.5 1.5M2.4 12h2.1M19.5 12h2.1M4.6 19.4l1.5-1.5M17.9 6.1l1.5-1.5" />
            </svg>
          )}
        </span>
      </span>
    </button>
  );
}

const NAV_GROUPS = [
  {
    group: "Overview",
    items: [{ to: "/", label: "Dashboard", hint: "Traffic, cost, hardware", icon: IconDashboard, end: true }],
  },
  {
    group: "Inference",
    items: [
      { to: "/inference/on-prem", label: "On-prem", hint: "Self-hosted model cards and weights", icon: IconModels },
      {
        to: "/inference/proprietary",
        label: "Proprietary",
        hint: "Provider keys and cloud models",
        icon: IconProviders,
      },
      { to: "/gateway", label: "How to call", hint: "Copyable curl and SDK examples", icon: IconGateway },
    ],
  },
  {
    group: "Governance",
    items: [
      { to: "/enterprise-policy", label: "Policy", hint: "Domain to model routing", icon: IconPolicy },
      { to: "/guardrails", label: "Guardrails", hint: "Input and output filters", icon: IconGuardrails },
    ],
  },
  {
    group: "Data",
    items: [{ to: "/vectors", label: "Vectors", hint: "Collections and embeddings", icon: IconVectors }],
  },
  {
    group: "Operations",
    items: [
      { to: "/load-testing", label: "Load testing", hint: "Locust runs and reports", icon: IconLoad },
      { to: "/observability", label: "Observability", hint: "Langfuse traces", icon: IconObservability },
      { to: "/settings", label: "Settings", hint: "niyan.yaml configuration", icon: IconSettings },
    ],
  },
] as const;

const FLAT_NAV = NAV_GROUPS.flatMap((g) =>
  g.items.map((i) => ({ to: i.to, label: i.label, hint: i.hint, group: g.group }))
) as PaletteItem[];

/** Keeps `?focus=<provider>` working for links saved before the Inference split. */
function ProvidersRedirect() {
  const { search } = useLocation();
  return <Navigate to={`/inference/proprietary${search}`} replace />;
}

function navIndex(pathname: string): number {
  if (pathname === "/") return 0;
  const i = FLAT_NAV.findIndex((item) => item.to !== "/" && pathname.startsWith(item.to));
  return i < 0 ? 0 : i;
}

function currentSection(pathname: string) {
  const item = FLAT_NAV[navIndex(pathname)];
  const group = NAV_GROUPS.find((g) => g.items.some((i) => i.to === item.to));
  return { label: item.label, group: group?.group ?? "Overview" };
}

function Login({ theme, onToggleTheme }: { theme: ResolvedTheme; onToggleTheme: () => void }) {
  const nav = useNavigate();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("niyan");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const res = await api.login(username, password);
      setToken(res.access_token);
      nav("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <section className="login-hero">
        <Atmosphere className="atmosphere--hero" />
        <div className="login-hero-inner">
          <div className="login-mark">
            <BrandMark size={30} />
          </div>
          <h1 className="login-title">
            The control plane
            <br />
            for models you <em>own</em>.
          </h1>
          <p className="login-hero-copy">
            One config brings up inference, guardrails, embeddings, and retrieval — then keeps them
            observable. Ollama runs the models; niyan runs everything around them.
          </p>
          <Schematic />
        </div>
        <div className="login-hero-foot">
          <span className="meta-label">Local first</span>
          <span className="meta-dot" aria-hidden />
          <span className="meta-label">OpenAI compatible</span>
          <span className="meta-dot" aria-hidden />
          <span className="meta-label">Self hosted</span>
        </div>
      </section>

      <section className="login-panel">
        <ThemeToggle resolved={theme} onToggle={onToggleTheme} className="login-theme" />
        <form className="login-card" onSubmit={onSubmit}>
          <p className="eyebrow">Console access</p>
          <h2 className="login-card-title">Sign in</h2>
          <p className="login-card-sub">Administrator credentials for this stack.</p>

          <div className="field">
            <label htmlFor="niyan-user">Username</label>
            <input
              id="niyan-user"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              spellCheck={false}
            />
          </div>
          <div className="field">
            <label htmlFor="niyan-pass">Password</label>
            <input
              id="niyan-pass"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
            />
          </div>
          {error && <p className="error">{error}</p>}
          <button type="submit" className="btn-lg" disabled={busy}>
            {busy ? "Signing in…" : "Enter console"}
          </button>
          <p className="login-card-foot">
            Defaults ship as <code>admin</code> / <code>niyan</code>. Change them in{" "}
            <code>niyan.yaml</code>.
          </p>
        </form>
      </section>
    </div>
  );
}

function Sidebar({
  theme,
  onToggleTheme,
  onOpenPalette,
}: {
  theme: ResolvedTheme;
  onToggleTheme: () => void;
  onOpenPalette: () => void;
}) {
  const nav = useNavigate();
  const location = useLocation();
  const listRef = useRef<HTMLDivElement>(null);
  const [marker, setMarker] = useState<{ top: number; height: number; ready: boolean }>({
    top: 0,
    height: 0,
    ready: false,
  });

  useLayoutEffect(() => {
    const root = listRef.current;
    if (!root) return;
    const measure = () => {
      const active = root.querySelector<HTMLElement>("a.active");
      if (!active) return;
      setMarker({ top: active.offsetTop, height: active.offsetHeight, ready: true });
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(root);
    return () => ro.disconnect();
  }, [location.pathname]);

  return (
    <aside className="sidebar">
      <div className="brand">
        <BrandMark size={28} sub="Control plane" />
      </div>

      <button type="button" className="rail-search" onClick={onOpenPalette}>
        <IconSearch />
        <span>Jump to…</span>
        <kbd className="kbd">⌘K</kbd>
      </button>

      <div className="nav" ref={listRef}>
        <span
          className={`nav-marker ${marker.ready ? "is-ready" : ""}`}
          style={{ transform: `translateY(${marker.top}px)`, height: marker.height }}
          aria-hidden
        />
        {NAV_GROUPS.map((group) => (
          <div className="nav-group" key={group.group}>
            <p className="nav-group-label">{group.group}</p>
            {group.items.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink key={item.to} to={item.to} end={"end" in item ? item.end : false}>
                  <Icon className="nav-icon" />
                  <span className="nav-label">{item.label}</span>
                </NavLink>
              );
            })}
          </div>
        ))}
      </div>

      <div className="sidebar-foot">
        <div className="rail-account">
          <span className="rail-avatar" aria-hidden>
            ad
          </span>
          <span className="rail-account-meta">
            <span className="rail-account-name">admin</span>
            <span className="rail-account-role">Administrator</span>
          </span>
          <ThemeToggle resolved={theme} onToggle={onToggleTheme} />
        </div>
        <button
          type="button"
          className="secondary rail-signout"
          onClick={() => {
            setToken(null);
            nav("/login");
          }}
        >
          Sign out
        </button>
      </div>
    </aside>
  );
}

function Shell({ theme, onToggleTheme }: { theme: ResolvedTheme; onToggleTheme: () => void }) {
  const location = useLocation();
  const idx = navIndex(location.pathname);
  const prevIdx = useRef(idx);
  const direction: 1 | -1 = idx >= prevIdx.current ? 1 : -1;
  const [paletteOpen, setPaletteOpen] = useState(false);
  const health = useStackHealth();
  const pulls = usePulls();
  const activePull = pulls.find((job) => job.status !== "error") ?? pulls[0];

  useEffect(() => {
    prevIdx.current = idx;
  }, [idx]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (!getToken()) return <Navigate to="/login" replace />;

  const section = currentSection(location.pathname);

  return (
    <div className="layout">
      <Atmosphere className="atmosphere--shell" />
      <Sidebar theme={theme} onToggleTheme={onToggleTheme} onOpenPalette={() => setPaletteOpen(true)} />

      <div className="main">
        <header className="topbar">
          <nav className="crumb" aria-label="Breadcrumb">
            <span className="crumb-root">{section.group}</span>
            <span className="crumb-sep" aria-hidden>
              /
            </span>
            <span className="crumb-leaf">{section.label}</span>
          </nav>

          <div className="topbar-side">
            {activePull ? (
              <Link to="/inference/on-prem" className="pull-chip" title={activePull.error || activePull.status}>
                <span className="pull-chip-bar" aria-hidden>
                  <span
                    className={activePull.percent == null ? "progress-fill is-indeterminate" : undefined}
                    style={{
                      width: activePull.percent != null ? `${Math.min(100, activePull.percent)}%` : undefined,
                    }}
                  />
                </span>
                {activePull.error
                  ? `Pull failed · ${activePull.id}`
                  : `Pulling ${activePull.id}${
                      activePull.percent != null ? ` ${Math.round(activePull.percent)}%` : ""
                    }${pulls.length > 1 ? ` · +${pulls.length - 1}` : ""}`}
              </Link>
            ) : null}
            <StackStatusChip health={health} />
            <span className="env-chip">
              <span className="env-key">endpoint</span>
              <span className="env-value">{ENDPOINT_LABEL}</span>
            </span>
            <button type="button" className="topbar-search" onClick={() => setPaletteOpen(true)}>
              <IconSearch />
              <kbd className="kbd">⌘K</kbd>
            </button>
          </div>
        </header>

        <main className="content">
          <PageTurn turnKey={location.pathname} direction={direction} className="view-stage--routes">
            <Routes location={location}>
              <Route path="/" element={<Dashboard />} />
              <Route path="/inference/on-prem" element={<OnPrem />} />
              <Route path="/inference/proprietary" element={<Proprietary />} />
              {/* Pre-split bookmarks and in-app deep links. */}
              <Route path="/models" element={<Navigate to="/inference/on-prem" replace />} />
              <Route path="/providers" element={<ProvidersRedirect />} />
              <Route path="/gateway" element={<Gateway />} />
              <Route path="/enterprise-policy" element={<EnterprisePolicy />} />
              <Route path="/load-testing" element={<LoadTesting />} />
              <Route path="/guardrails" element={<Guardrails />} />
              <Route path="/vectors" element={<Vectors />} />
              <Route path="/observability" element={<Observability />} />
              <Route path="/settings" element={<Settings />} />
            </Routes>
          </PageTurn>
        </main>
      </div>

      <CommandPalette items={FLAT_NAV} open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </div>
  );
}

export default function App() {
  const [ready, setReady] = useState(false);
  const { resolved, toggle } = useTheme();
  useEffect(() => setReady(true), []);
  if (!ready) return null;
  return (
    <Routes>
      <Route path="/login" element={<Login theme={resolved} onToggleTheme={toggle} />} />
      <Route path="/*" element={<Shell theme={resolved} onToggleTheme={toggle} />} />
    </Routes>
  );
}
