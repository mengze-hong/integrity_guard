# Architecture

This document describes how ScholarLint · 投稿通 is structured so a new engineer can navigate the codebase and extend it safely. It reflects the code at app version `5.3.83`.

## High-Level Overview

ScholarLint is a FastAPI monolith with a server-rendered single-page frontend. There is no separate frontend build step; the UI is delivered as `app/templates/index.html` plus a small set of static assets.

```
Browser (index.html SPA)
        │  HTTP/JSON
        ▼
FastAPI app (app/main.py)
   ├── middleware: monitoring, security headers
   ├── routers: api / ai / auth / payment
   ├── probes: /healthz /readyz /metrics
   │
   ├── checks/      six quality gates
   ├── parsers/     LaTeX / BibTeX / ZIP
   ├── services/    guardrails, reports, LLM, crossref, file store, scoring
   ├── storage.py   encrypted report persistence (data/jobs/)
   └── models_db.py SQLite ORM (users, transactions, orders, api tokens)
```

State lives in three places:
- **SQLite** (`data/integrity.db`) — users, transactions, payment orders, API tokens.
- **Encrypted report files** (`data/jobs/*.enc`, plaintext `*.json` fallback) — per-job `FullReport`.
- **In-memory route state** (`app/api/routes.py`) — `_job_status`, `_job_owners`, `_job_dirs`, progress, recheck locks. This is process-local and resets on restart; persisted reports are the durable source of truth.

## Application Entry Point

`app/main.py` builds the FastAPI app and wires everything together:

- **Lifespan startup** — initializes the database (`init_db`) and cleans expired jobs (`storage.cleanup_expired`).
- **Routers**, all mounted under `/api`:
  - `app/api/routes.py` → core/legacy router (upload, jobs, files, reports, export, history, tools, checklist).
  - `app/api/ai_routes.py` → AI endpoints.
  - `app/api/auth_routes.py` → auth, account, API tokens.
  - `app/api/payment_routes.py` → packages, payment, callback, admin credits.
- **Middleware**:
  - `monitoring_middleware` — records request counts, latency, and 5xx errors into `app/monitoring.py`.
  - `security_headers_middleware` — sets `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, and a CSP compatible with the current SPA and its CDN dependencies.
- **Global exception handler** — returns a clean JSON error and redacts secrets via `app.secrets_manager.redact`.
- **Pages** — `/` (upload SPA), `/report/{job_id}` (report page).
- **Probes** — `/healthz`, `/readyz`, `/metrics` (see below).

## Request Flow: Upload → Report

1. `POST /api/upload` receives a ZIP. The uploader is identified by a logged-in user or an anonymous `sl_session` cookie.
2. `app/parsers/zip_parser.py` validates and extracts the archive with zip-slip, zip-bomb, symlink, depth, and dangerous-file protections. Failed extraction cleans up the partial directory.
3. The gate runner (inside `app/api/routes.py`) parses files and runs the six gates, producing a `FullReport`.
4. `app/storage.py` persists the report (encrypted when crypto is available, plaintext fallback otherwise). Owner/share metadata is written into the report metadata.
5. The SPA polls `GET /api/status/{job_id}`, then loads `GET /api/report/{job_id}` and the file tree.
6. The user edits files, applies fixes, re-checks (`POST /api/recheck/{job_id}`), exports, or shares.

## Quality Gates

Located in `app/checks/`. Each gate extends the base in `app/checks/base.py` and returns issues with severity, location, evidence, and suggestions.

| File | Gate | Focus |
|---|---|---|
| `gate_structure.py` | Structure | `\label`/`\ref` integrity, figure/table cross-refs, graphics paths, image quality hints |
| `gate_citations.py` | Citations | citation freshness, self-citation ratio, citation hygiene |
| `gate_references.py` | Reference authenticity | verifies references against authoritative sources; the product's core integrity guarantee |
| `gate_figures.py` | Figures/Tables | figure/table presence, captions, references |
| `gate_data.py` | Data integrity | number consistency, p-value patterns, Benford's law, duplicate images |
| `gate_writing.py` | Writing quality | AI traces, anonymization, typos, paragraph duplication, filler text |

A gate score below `settings.reference_confidence_threshold` (default 60) marks the gate as failing.

## Parsers

Located in `app/parsers/`:
- `tex_parser.py` — extracts citations, refs, labels, graphics, and sections from LaTeX. Supports a broad set of natbib/biblatex/cleveref commands and optional args.
- `bib_parser.py` — parses BibTeX entries, normalizes DOIs, and tracks source file/line.
- `zip_parser.py` — safe extraction with the security protections listed above.

## Services

Located in `app/services/`. These are the intended extension points for new logic instead of growing the routers:
- `ai_guardrails.py` — reference-authenticity detection, `not_fixable` payloads, AI provenance, candidate metadata. **This is where the "AI never fabricates references" rule is enforced.**
- `ai_reports.py` — diagnosis input building, JSON-tolerant parsing, deterministic fallback.
- `llm.py` — unified LLM call layer (handles reasoning vs non-reasoning models, temperature retry, content fallback).
- `crossref.py` — Crossref client.
- `file_store.py` — safe in-project path resolution, editable file listing, project ZIP packaging.
- `dimension_scores.py` — Novelty/Soundness/Clarity/Significance heuristic scores.
- `style_analysis.py` — writing-style metrics.

## AI Guardrails (Critical Invariant)

Reference authenticity is the product's trust anchor. The following invariant must never be weakened:

- `reference_authenticity` gate issues (and "missing DOI / no trusted source / title search not found / unverified reference / source not found" issues) are classified as `not_fixable`.
- These issues **never call the LLM**. `ai-fix` returns a human-review payload; `ai-batch-fix` skips them.
- Real reference candidates only come from authoritative sources (Crossref / Semantic Scholar / OpenAlex / DBLP / ACL) via `POST /api/reference-candidates/{job_id}`, which does not use the LLM.
- All AI outputs are labeled as suggestions / simulations requiring human verification.

When a fix cannot be precisely anchored to the original text, the system does **not** write the file; it returns a copyable suggestion with a clear message instead.

## Permission Model

Implemented in `app/api/routes.py` (helpers) and `app/dependencies.py` (auth). There is no decorator-based guard; route handlers call shared helpers.

- **Owner identity** — a logged-in user (JWT in `token` cookie or `Authorization: Bearer`) or an anonymous `sl_session` cookie. Resolved per request.
- **Job ownership** — reports store `owner_type`, `owner_id`, and `share_token` in metadata.
- **Access checks** — `_require_job_access(...)` / `_can_access_report(...)`:
  - Owner match → full read/write access.
  - Valid `share` token → read-only access (cannot save, recheck, dismiss, or call AI/tools).
  - Legacy reports without owner metadata remain accessible for local-demo compatibility. **This is a known production-hardening gap** (see `HANDOVER.md`).
- **Admin** — `POST /api/payment/admin/add-credits` requires `Authorization: Bearer <admin_key>` or `X-Admin-Key`, plus rate limiting. The admin key is never accepted in the request body.

## Auth & Billing

- `app/auth.py` — password hashing and JWT encode/decode.
- `app/dependencies.py` — `get_db`, `get_current_user`, `get_current_user_optional`.
- `app/models_db.py` — SQLAlchemy models: `User`, `Transaction`, `PaymentOrder`, `ApiToken`.
- Tiers: `free` (3 monthly checks, lazy refresh), `pro` (unlimited checks), `team` (unlimited + mentor dashboard). Paid packages upgrade tiers; downgrades from `team` to `pro` are prevented.
- Payments run in sandbox mode by default (`PAYMENT_SANDBOX=true`). Real Alipay signing/verification is **not** implemented.

## Storage & Encryption

- `app/secrets_manager.py` — Fernet (AES-128-CBC + HMAC) encryption. The master key lives in the OS credential vault via `keyring`, never on disk. Provides `get_secret`, `get_or_create_secret`, `redact`, `is_available`.
- `app/storage.py` — encrypted report persistence under `data/jobs/`. Reads legacy `.json` and migrates to `.enc` on next save. Falls back to plaintext when the crypto stack is unavailable.
- `app/config.py` — settings resolved from environment variables first, then the encrypted store. No secret is hardcoded. See `docs/CONFIGURATION.md`.

## Health, Readiness & Metrics

- `GET /healthz` — liveness; returns service name and version.
- `GET /readyz` — readiness; checks database, encrypted store availability, LLM configuration, payment sandbox state (degraded in production), and storage directories. Returns sanitized booleans/status only — never secret values or internal endpoints.
- `GET /metrics` — uptime, request counts, error rate, and per-endpoint latency from `app/monitoring.py`, with high-cardinality path fields sanitized. No app-level auth; protect behind a reverse proxy in production.

## Known Maintainability Risks

These are the highest-value targets for the next engineer (also tracked in `HANDOVER.md`):
- `app/api/routes.py` is a large god-module mixing many responsibilities.
- `app/templates/index.html` is an overgrown single-page UI; extract static JS modules incrementally (do not rewrite to React/Vue yet).
- `app/api/ai_routes.py` still imports private helpers from `routes.py`.
- Tests share duplicated fixtures with no `tests/conftest.py`.
- Job data is split across encrypted reports, upload folders, and in-memory route state.

## Related Documents

- [CONFIGURATION.md](CONFIGURATION.md) — environment variables and settings.
- [API_OVERVIEW.md](API_OVERVIEW.md) — endpoint reference.
- [LOCAL_RUN.md](LOCAL_RUN.md) — local setup and run.
- [DEPLOY_SAFE.md](DEPLOY_SAFE.md) — safe production deployment.
- [../HANDOVER.md](../HANDOVER.md) — handover notes and next steps.
