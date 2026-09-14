import { FormEvent, useMemo, useState } from "react";
import { runAnalysis } from "./api/chat";
import { ConnectionConfig, loadConnection, saveConnection } from "./connection";
import { CLIENTS, ClientRecord, INVOICES, REVENUE_BY_MONTH, TEAM } from "./data";
import { SettingsModal } from "./SettingsModal";

const HERO =
  "https://images.unsplash.com/photo-1497366216548-37526070297c?auto=format&fit=crop&w=2000&q=80";

export default function App() {
  const [view, setView] = useState<"landing" | "app">("landing");
  const [cfg, setCfg] = useState<ConnectionConfig>(() => loadConnection());
  const [draft, setDraft] = useState<ConnectionConfig>(() => loadConnection());
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [selectedId, setSelectedId] = useState(CLIENTS[0].id);
  const [query, setQuery] = useState("");
  const [region, setRegion] = useState("All regions");
  const [note, setNote] = useState("");
  const [result, setResult] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const selected = CLIENTS.find((c) => c.id === selectedId) ?? CLIENTS[0];

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return CLIENTS.filter((c) => {
      const regionOk = region === "All regions" || c.region === region;
      const queryOk =
        !q ||
        c.name.toLowerCase().includes(q) ||
        c.industry.toLowerCase().includes(q) ||
        c.owner.toLowerCase().includes(q);
      return regionOk && queryOk;
    });
  }, [query, region]);

  const totals = useMemo(() => {
    const arr = CLIENTS.reduce((s, c) => s + c.arr, 0);
    const openInv = INVOICES.filter((i) => i.status !== "Paid").reduce((s, i) => s + i.amount, 0);
    const atRisk = CLIENTS.filter((c) => c.health === "At risk").length;
    return { arr, openInv, atRisk, clients: CLIENTS.length };
  }, []);

  const clientInvoices = INVOICES.filter((i) => i.clientId === selected.id);

  function persistSettings() {
    saveConnection(draft);
    setCfg(draft);
    setSettingsOpen(false);
  }

  async function onAnalyze(e: FormEvent) {
    e.preventDefault();
    if (!note.trim() || busy) return;
    setBusy(true);
    setResult(null);
    try {
      const prompt = [
        "Confidential client record (internal only — do not invent external facts):",
        `Client: ${selected.name} (${selected.id})`,
        `Industry: ${selected.industry} · Region: ${selected.region}`,
        `ARR: $${selected.arr.toLocaleString()} · Plan: ${selected.plan}`,
        `Owner: ${selected.owner} · Health: ${selected.health}`,
        `Contacts: ${selected.contacts.map((x) => `${x.name} <${x.email}>`).join("; ")}`,
        "",
        note.trim(),
      ].join("\n");
      const out = await runAnalysis(cfg, prompt);
      setResult(out.content || "No output returned.");
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
          <span className="brand-mark">Fiducia</span>
          <span className="privacy-pill">Private · on-prem data</span>
        </header>
        <main className="landing-hero">
          <p className="brand-hero">Fiducia</p>
          <h1>Client revenue stays inside your walls.</h1>
          <p className="lede">
            Customer contracts, invoices, and account health — sourced from your private
            database, never sent to outside model providers.
          </p>
          <button type="button" className="cta" onClick={() => setView("app")}>
            Open client ledger
          </button>
        </main>
      </div>
    );
  }

  return (
    <div className="shell">
      <aside className="rail">
        <button type="button" className="brand-link" onClick={() => setView("landing")}>
          Fiducia
        </button>
        <div className="privacy-banner">
          <strong>Confidential</strong>
          <span>Client PII & revenue stay local. Analysis runs on your private model only.</span>
        </div>
        <nav className="rail-nav">
          <span className="nav-active">Clients</span>
          <span>Revenue</span>
          <span>Invoices</span>
          <span>Renewals</span>
        </nav>
        <div className="rail-team">
          <p className="rail-label">Account team</p>
          {TEAM.map((m) => (
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
            <h1>Client revenue ledger</h1>
            <p className="muted">Synced from internal CRM · last pull 3 min ago</p>
          </div>
          <div className="filters">
            <label>
              Search clients
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Name, industry, owner…"
              />
            </label>
            <label>
              Region
              <select value={region} onChange={(e) => setRegion(e.target.value)}>
                <option>All regions</option>
                <option>North America</option>
                <option>Europe</option>
                <option>APAC</option>
              </select>
            </label>
          </div>
        </header>

        <section className="kpi-row">
          <div className="kpi">
            <span className="kpi-label">Booked ARR</span>
            <strong>${(totals.arr / 1e6).toFixed(2)}M</strong>
            <span className="kpi-hint">{totals.clients} active accounts</span>
          </div>
          <div className="kpi">
            <span className="kpi-label">Open receivables</span>
            <strong>${(totals.openInv / 1e3).toFixed(0)}K</strong>
            <span className="kpi-hint">Unpaid invoices</span>
          </div>
          <div className="kpi">
            <span className="kpi-label">At-risk accounts</span>
            <strong>{totals.atRisk}</strong>
            <span className="kpi-hint">Needs CSM attention</span>
          </div>
          <div className="kpi">
            <span className="kpi-label">Data residency</span>
            <strong className="local">Local DB</strong>
            <span className="kpi-hint">No proprietary cloud models</span>
          </div>
        </section>

        <div className="grid-ledger">
          <section className="panel client-list">
            <div className="panel-head">
              <h2>Accounts</h2>
              <span className="chip">{filtered.length} shown</span>
            </div>
            <ul className="accounts">
              {filtered.map((c) => (
                <li key={c.id}>
                  <button
                    type="button"
                    className={c.id === selected.id ? "account active" : "account"}
                    onClick={() => setSelectedId(c.id)}
                  >
                    <img src={c.logo} alt="" />
                    <div className="account-body">
                      <strong>{c.name}</strong>
                      <span className="sub">
                        {c.id} · {c.industry}
                      </span>
                    </div>
                    <div className="account-side">
                      <span className={`health ${healthClass(c.health)}`}>{c.health}</span>
                      <span className="arr">${formatArr(c.arr)}</span>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          </section>

          <section className="panel detail">
            <div className="detail-hero">
              <img src={selected.cover} alt="" className="detail-cover" />
              <div className="detail-hero-text">
                <div className="detail-brand">
                  <img src={selected.logo} alt="" />
                  <div>
                    <h2>{selected.name}</h2>
                    <p className="muted">
                      {selected.id} · {selected.region} · Contract since {selected.since}
                    </p>
                  </div>
                </div>
                <span className={`health big ${healthClass(selected.health)}`}>{selected.health}</span>
              </div>
            </div>

            <div className="detail-grid">
              <div>
                <span className="field-label">Annual revenue</span>
                <strong>${selected.arr.toLocaleString()}</strong>
              </div>
              <div>
                <span className="field-label">Plan</span>
                <strong>{selected.plan}</strong>
              </div>
              <div>
                <span className="field-label">Seats</span>
                <strong>{selected.seats}</strong>
              </div>
              <div>
                <span className="field-label">Renewal</span>
                <strong>{selected.renewal}</strong>
              </div>
              <div>
                <span className="field-label">Account owner</span>
                <strong>{selected.owner}</strong>
              </div>
              <div>
                <span className="field-label">Billing email</span>
                <strong className="secret">{selected.billingEmail}</strong>
              </div>
            </div>

            <h3 className="section-title">Primary contacts</h3>
            <div className="contacts">
              {selected.contacts.map((p) => (
                <div key={p.email} className="contact">
                  <img src={p.photo} alt="" />
                  <div>
                    <strong>{p.name}</strong>
                    <span className="sub">
                      {p.title} · <span className="secret">{p.email}</span>
                    </span>
                  </div>
                </div>
              ))}
            </div>

            <h3 className="section-title">Invoices (from ledger DB)</h3>
            <table>
              <thead>
                <tr>
                  <th>Invoice</th>
                  <th>Period</th>
                  <th>Amount</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {clientInvoices.map((inv) => (
                  <tr key={inv.id}>
                    <td>
                      <strong>{inv.id}</strong>
                    </td>
                    <td>{inv.period}</td>
                    <td>${inv.amount.toLocaleString()}</td>
                    <td>
                      <span className={`inv ${inv.status.toLowerCase().replace(" ", "-")}`}>
                        {inv.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            <h3 className="section-title">Internal note</h3>
            <p className="note-hint">
              Uses only this account’s local fields. Safe for sensitive customer data — private
              model path.
            </p>
            <form onSubmit={onAnalyze} className="analysis-form">
              <textarea
                rows={3}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder={`e.g. Draft a renewal risk summary for ${selected.name} using only the fields above…`}
                disabled={busy}
              />
              <button type="submit" className="cta" disabled={busy || !note.trim()}>
                {busy ? "Generating…" : "Generate internal note"}
              </button>
            </form>
            {result && <pre className="analysis-out">{result}</pre>}
          </section>
        </div>

        <section className="panel">
          <div className="panel-head">
            <h2>Recognized revenue (trailing 6 months)</h2>
            <span className="chip">From finance DB</span>
          </div>
          <div className="rev-bars">
            {REVENUE_BY_MONTH.map((m) => (
              <div key={m.month} className="rev-col">
                <div className="rev-bar-wrap">
                  <div
                    className="rev-bar"
                    style={{ height: `${(m.amount / maxRevenue()) * 100}%` }}
                    title={`$${m.amount.toLocaleString()}`}
                  />
                </div>
                <span>{m.month}</span>
                <strong>${(m.amount / 1000).toFixed(0)}k</strong>
              </div>
            ))}
          </div>
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

function healthClass(h: ClientRecord["health"]) {
  if (h === "Healthy") return "ok";
  if (h === "Watch") return "watch";
  return "risk";
}

function formatArr(n: number) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  return `${Math.round(n / 1000)}K`;
}

function maxRevenue() {
  return Math.max(...REVENUE_BY_MONTH.map((m) => m.amount));
}
