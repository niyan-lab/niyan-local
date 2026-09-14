# Demo apps

Two standalone product UIs for local demos.

| App | Port | Description |
|-----|------|-------------|
| [`finance/`](finance/) — **Fiducia** | 5201 | Confidential client revenue / CRM ledger |
| [`research/`](research/) — **Praxis** | 5202 | Research program workspace |

## Run

```bash
# requires Node.js (brew install node)
cd demo_apps/finance && npm install && npm run dev
cd demo_apps/research && npm install && npm run dev
```

Optional API wiring for notes/briefs is under **Settings**:

1. Enter **Base URL** (auto health-check)
2. Scroll and pick a **domain**
3. Pick an available **model** from the gateway
4. Save — then run notes in the app
