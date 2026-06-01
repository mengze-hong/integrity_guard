# ScholarLint · 投稿通

Academic paper pre-submission integrity checker. Upload a LaTeX project ZIP and get strict, rule-based plus LLM-assisted checks before you submit to a conference or journal.

ScholarLint is built as a commercializable SaaS, not a one-off demo. Strict checking is intentional: false positives are acceptable, missed integrity issues are not.

- App version: `5.3.92` (see [CHANGELOG.md](CHANGELOG.md))
- Stack: FastAPI + SQLite + a single-page HTML/JS frontend
- LLM features are advisory only and never fabricate references

## What It Does

- **Six quality gates** — structure, citations, reference authenticity, figures/tables, data integrity, and writing quality.
- **Reference authenticity** — verifies citations against authoritative sources (Crossref, Semantic Scholar, OpenAlex, DBLP, ACL Anthology). AI is never allowed to invent references, DOIs, authors, titles, or years.
- **In-browser editor** — open project files, apply fixes, re-check, and download a fixed ZIP.
- **AI assistance** — diagnosis report, batch fix suggestions, reviewer simulation, abstract optimization, and venue checklists (ARR / NeurIPS). Every AI output is labeled as a suggestion that requires human verification.
- **Accounts & billing** — email/password auth, credits, paid tiers (Free / Pro / Team), sandbox payments, and a Team mentor dashboard.
- **Sharing & reports** — read-only advisor share links and branded Markdown report export.

## Project Layout

```
app/
  main.py            FastAPI entry point: routers, middleware, security headers, health/ready/metrics
  config.py          Settings, loaded from env first then encrypted secret store
  api/
    routes.py        Core/legacy router: upload, jobs, files, reports, export, history, tools, checklist
    ai_routes.py     AI endpoints (ai-fix, ai-batch-fix, ai-review, ai-polish, ai-abstract, ai-diagnosis)
    auth_routes.py   register / login / me / dashboard / API tokens
    payment_routes.py packages / sandbox payment / callback / admin credits
  checks/            Six quality gates (gate_structure, gate_citations, gate_references,
                     gate_figures, gate_data, gate_writing)
  parsers/           LaTeX / BibTeX / ZIP parsing (tex_parser, bib_parser, zip_parser)
  services/          Service helpers (ai_guardrails, ai_reports, crossref, file_store,
                     llm, dimension_scores, style_analysis)
  storage.py         Encrypted report persistence under data/jobs/ (plaintext fallback)
  models_db.py       SQLite ORM: users, transactions, payment orders, API tokens
  static/            Brand assets and extracted JS helpers
  templates/         index.html single-page UI
docs/                Local run, testing, release, safe deploy, backup, do-not-do guides
scripts/             check-inline-js / test-js-helpers / secret-scan / backup_data
tests/               pytest suite (~100 tests)
```

## Request Flow

1. User uploads a ZIP through `POST /api/upload`.
2. The ZIP is validated and safely extracted (zip slip / zip bomb / dangerous file protections).
3. Gate runner logic builds a `FullReport`.
4. Reports are persisted via `app/storage.py` (encrypted when crypto is available).
5. The UI loads the report and files, then offers fixes, export, sharing, dashboard, and history.
6. Auth, payment, and tier logic live in SQLite.

## Quick Start

Requires Python 3.11+ and Node.js.

```bash
python -m venv .venv
.venv/Scripts/activate          # Windows; use source .venv/bin/activate on macOS/Linux
python -m pip install -U pip
python -m pip install -e ".[dev]"
npm install
```

Initialize secrets (env variables take priority over the encrypted store):

```bash
python -m app.secrets_setup --set LLM_API_KEY
python -m app.secrets_setup --set LLM_BASE_URL
python -m app.secrets_setup --set LLM_MODEL
```

Run the app (bind to loopback for local demos):

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open `http://localhost:8000`. See [docs/LOCAL_RUN.md](docs/LOCAL_RUN.md) for Docker Compose and health probes.

## Health & Monitoring

- `GET /healthz` — liveness probe, returns service version.
- `GET /readyz` — readiness probe for database, secret store, LLM config, payment sandbox state, and storage directories (sanitized fields only).
- `GET /metrics` — uptime, request counts, error rate, and latency aggregated per endpoint. Protect this behind a reverse proxy in production.

## Testing & Validation

Run after meaningful changes:

```bash
python -m ruff check app/ tests/ scripts/backup_data.py --select E,F,W --ignore E501
npm ci
npm run check:js
npm run test:js
npm run scan:secrets
python -m pytest -q
```

See [docs/TESTING_GUIDE.md](docs/TESTING_GUIDE.md) for focused commands by change type and [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md) for pre-release steps.

## Documentation

- [docs/README.md](docs/README.md) — documentation index
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — system structure, request flow, gates, services, permission model
- [docs/CONFIGURATION.md](docs/CONFIGURATION.md) — settings, secrets, and sourcing order
- [docs/API_OVERVIEW.md](docs/API_OVERVIEW.md) — endpoint reference by router
- [docs/LOCAL_RUN.md](docs/LOCAL_RUN.md) — local install, secrets, run, Docker, health checks
- [docs/TESTING_GUIDE.md](docs/TESTING_GUIDE.md) — test commands by change type
- [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md) — pre-release checks
- [docs/DEPLOY_SAFE.md](docs/DEPLOY_SAFE.md) — safe production deployment
- [docs/BACKUP.md](docs/BACKUP.md) — backup and restore
- [docs/DO_NOT_DO.md](docs/DO_NOT_DO.md) — operational guardrails
- [HANDOVER.md](HANDOVER.md) — handover notes for the next maintainer

## Operating Rules

- Never expose the dev server through a public tunnel provider. CI enforces a forbidden tunnel provider policy scan.
- Never commit secrets, `.env`, `data/secrets.enc`, uploaded papers, backups, or screenshots containing private content.
- AI must never fabricate references; reference authenticity issues never call the LLM.
- Do not make irreversible production or data changes without explicit approval.

## License

Proprietary. All rights reserved unless stated otherwise.
