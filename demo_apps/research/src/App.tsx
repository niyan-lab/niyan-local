import { FormEvent, useState } from "react";
import { runBrief } from "./api/chat";
import { ConnectionConfig, loadConnection, saveConnection } from "./connection";
import { SettingsModal } from "./SettingsModal";

const HERO =
  "https://images.unsplash.com/photo-1507842217343-583bb7270b66?auto=format&fit=crop&w=2000&q=80";

const COLLABORATORS = [
  {
    name: "Dr. Amira Sol",
    role: "Principal investigator",
    photo: "https://images.unsplash.com/photo-1594824476967-48c8b964273f?auto=format&fit=crop&w=200&h=200&q=80",
  },
  {
    name: "Noah Richter",
    role: "Methods lead",
    photo: "https://images.unsplash.com/photo-1519085360753-af0119f7cbe7?auto=format&fit=crop&w=200&h=200&q=80",
  },
  {
    name: "Sofia Park",
    role: "Literature curator",
    photo: "https://images.unsplash.com/photo-1544005313-94ddf0286df2?auto=format&fit=crop&w=200&h=200&q=80",
  },
  {
    name: "Leo Andersson",
    role: "Lab operations",
    photo: "https://images.unsplash.com/photo-1506794778202-cad84cf45f1d?auto=format&fit=crop&w=200&h=200&q=80",
  },
];

const PROJECTS = [
  {
    code: "PRX-214",
    title: "Retrieval evaluation protocols",
    status: "Active",
    progress: 72,
    cover: "https://images.unsplash.com/photo-1451187580459-43490279c0fa?auto=format&fit=crop&w=600&h=360&q=80",
  },
  {
    code: "PRX-198",
    title: "Long-context factuality study",
    status: "Review",
    progress: 91,
    cover: "https://images.unsplash.com/photo-1635070041078-e363dbe005cb?auto=format&fit=crop&w=600&h=360&q=80",
  },
  {
    code: "PRX-176",
    title: "Prompt robustness battery",
    status: "Active",
    progress: 44,
    cover: "https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=600&h=360&q=80",
  },
];

const PAPERS = [
  { title: "Encoder vs decoder trade-offs in classification", venue: "Preprint · 2026", tags: "NLP · Eval" },
  { title: "Measuring citation faithfulness under pressure", venue: "Internal memo", tags: "Methods" },
  { title: "Sampling strategies for ablation grids", venue: "Workshop draft", tags: "Experiment design" },
  { title: "Human preference noise in pairwise labels", venue: "Reading group", tags: "HLE" },
];

const MILESTONES = [
  { when: "Jul 30", title: "Freeze evaluation harness v3", owner: "Noah" },
  { when: "Aug 04", title: "Annotator calibration session", owner: "Sofia" },
  { when: "Aug 12", title: "Draft results for steering committee", owner: "Amira" },
  { when: "Aug 20", title: "External reviewer packet", owner: "Leo" },
];

const STATS = [
  { label: "Active studies", value: "12" },
  { label: "Sources indexed", value: "4,820" },
  { label: "Open reviews", value: "27" },
  { label: "Lab utilization", value: "81%" },
];

export default function App() {
  const [view, setView] = useState<"landing" | "app">("landing");
  const [cfg, setCfg] = useState<ConnectionConfig>(() => loadConnection());
  const [draft, setDraft] = useState<ConnectionConfig>(() => loadConnection());
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [brief, setBrief] = useState("");
  const [result, setResult] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [program, setProgram] = useState("Applied ML Lab");
  const [focus, setFocus] = useState("Evaluation & methods");

  function persistSettings() {
    saveConnection(draft);
    setCfg(draft);
    setSettingsOpen(false);
  }

  async function onBrief(e: FormEvent) {
    e.preventDefault();
    if (!brief.trim() || busy) return;
    setBusy(true);
    setResult(null);
    try {
      const prompt = `Program: ${program}. Focus: ${focus}.\n\n${brief.trim()}`;
      setResult((await runBrief(cfg, prompt)) || "No output returned.");
    } catch (err) {
      setResult(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  if (view === "landing") {
    return (
      <div className="landing">
        <div className="landing-media" style={{ backgroundImage: `url(${HERO})` }} />
        <div className="landing-scrim" />
        <header className="landing-top">
          <span className="brand-mark">Praxis</span>
          <button type="button" className="ghost-on-dark" onClick={() => setSettingsOpen(true)}>
            Settings
          </button>
        </header>
        <main className="landing-hero">
          <p className="brand-hero reveal">Praxis</p>
          <h1 className="reveal delay-1">A workspace for serious research programs.</h1>
          <p className="lede reveal delay-2">Projects, literature, and lab cadence in one place.</p>
          <button type="button" className="cta reveal delay-3" onClick={() => setView("app")}>
            Open workspace
          </button>
        </main>
        {settingsOpen && (
          <SettingsModal
            draft={draft}
            setDraft={setDraft}
            onClose={() => setSettingsOpen(false)}
            onSave={persistSettings}
          />
        )}
      </div>
    );
  }

  return (
    <div className="shell">
      <aside className="rail">
        <button type="button" className="brand-link" onClick={() => setView("landing")}>
          Praxis
        </button>
        <nav className="rail-nav">
          <span className="nav-active">Program</span>
          <span>Projects</span>
          <span>Library</span>
          <span>Calendar</span>
          <span>People</span>
        </nav>
        <div className="rail-team">
          <p className="rail-label">Core team</p>
          {COLLABORATORS.map((m) => (
            <div key={m.name} className="person">
              <img src={m.photo} alt="" />
              <div>
                <strong>{m.name}</strong>
                <span>{m.role}</span>
              </div>
            </div>
          ))}
        </div>
        <button
          type="button"
          className="ghost rail-settings"
          onClick={() => {
            setDraft(cfg);
            setSettingsOpen(true);
          }}
        >
          Settings
        </button>
      </aside>

      <div className="main">
        <header className="topbar">
          <div>
            <h1>Applied ML Lab</h1>
            <p className="muted">Summer cycle · 18 contributors</p>
          </div>
          <div className="filters">
            <label>
              Program
              <select value={program} onChange={(e) => setProgram(e.target.value)}>
                <option>Applied ML Lab</option>
                <option>Safety & alignment</option>
                <option>Systems research</option>
              </select>
            </label>
            <label>
              Focus
              <select value={focus} onChange={(e) => setFocus(e.target.value)}>
                <option>Evaluation & methods</option>
                <option>Literature synthesis</option>
                <option>Experiment design</option>
              </select>
            </label>
          </div>
        </header>

        <section className="kpi-row">
          {STATS.map((s) => (
            <div key={s.label} className="kpi">
              <span className="kpi-label">{s.label}</span>
              <strong>{s.value}</strong>
            </div>
          ))}
        </section>

        <section className="panel">
          <div className="panel-head">
            <h2>Active projects</h2>
            <span className="chip">3 in flight</span>
          </div>
          <div className="project-grid">
            {PROJECTS.map((p) => (
              <article key={p.code} className="project">
                <img src={p.cover} alt="" />
                <div className="project-body">
                  <span className="code">{p.code}</span>
                  <strong>{p.title}</strong>
                  <div className="project-meta">
                    <span className="status">{p.status}</span>
                    <span>{p.progress}%</span>
                  </div>
                  <div className="bar-track">
                    <div className="bar-fill" style={{ width: `${p.progress}%` }} />
                  </div>
                </div>
              </article>
            ))}
          </div>
        </section>

        <div className="grid-2">
          <section className="panel">
            <div className="panel-head">
              <h2>Reading queue</h2>
              <span className="chip">Shared shelf</span>
            </div>
            <ul className="paper-list">
              {PAPERS.map((p) => (
                <li key={p.title}>
                  <div>
                    <strong>{p.title}</strong>
                    <span className="sub">
                      {p.venue} · {p.tags}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          </section>

          <section className="panel">
            <div className="panel-head">
              <h2>Upcoming milestones</h2>
              <span className="chip">Next 30 days</span>
            </div>
            <ul className="milestone-list">
              {MILESTONES.map((m) => (
                <li key={m.title}>
                  <span className="when">{m.when}</span>
                  <div>
                    <strong>{m.title}</strong>
                    <span className="sub">Owner · {m.owner}</span>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        </div>

        <section className="panel brief">
          <div className="panel-head">
            <h2>Briefing note</h2>
            <span className="chip">Optional</span>
          </div>
          <form onSubmit={onBrief} className="brief-form">
            <textarea
              rows={3}
              value={brief}
              onChange={(e) => setBrief(e.target.value)}
              placeholder="e.g. Outline comparison points between encoder-only and decoder-only classifiers…"
              disabled={busy}
            />
            <button type="submit" className="cta" disabled={busy || !brief.trim()}>
              {busy ? "Drafting…" : "Draft brief"}
            </button>
          </form>
          {result && <pre className="brief-out">{result}</pre>}
        </section>
      </div>

      {settingsOpen && (
        <SettingsModal
          draft={draft}
          setDraft={setDraft}
          onClose={() => setSettingsOpen(false)}
          onSave={persistSettings}
        />
      )}
    </div>
  );
}
