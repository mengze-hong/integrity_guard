# API Overview

Endpoint reference for ScholarLint · 投稿通, grouped by router. All API routes are mounted under the `/api` prefix. Page and probe routes live at the root. This reflects the code at app version `5.3.83`.

## Conventions

- **Auth** — a logged-in user (JWT in `token` cookie or `Authorization: Bearer <jwt>`) or an anonymous `sl_session` cookie identifies the caller.
- **Job access** — job endpoints check ownership via report metadata (`owner_type`, `owner_id`, `share_token`):
  - **Owner** — full read/write.
  - **Share token** (`?share=<token>`) — read-only; cannot save, recheck, dismiss, or call AI/tools.
  - **Legacy** — reports without owner metadata stay accessible for local-demo compatibility (a production-hardening gap).
- **Errors** — unhandled exceptions return `500` with a redacted message. Access failures return `403`; missing jobs return `404`; auth-required failures return `401`; insufficient credits return `402`.

## Pages & Probes (root, no `/api` prefix)

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Upload SPA (`index.html`). |
| GET | `/report/{job_id}` | Standalone report page. |
| GET | `/healthz` | Liveness probe; returns service version. |
| GET | `/readyz` | Readiness probe; sanitized checks for DB, crypto, LLM, payment, storage. |
| GET | `/metrics` | Uptime, request counts, error rate, per-endpoint latency. Protect behind a reverse proxy. |

## Core Router (`app/api/routes.py`)

### Jobs & Reports

| Method | Path | Access | Purpose |
|---|---|---|---|
| POST | `/api/upload` | user or anon session; consumes 1 credit (free tier) | Upload a ZIP, validate/extract, run gates, create a job. |
| GET | `/api/status/{job_id}` | job read | Poll processing status. |
| GET | `/api/report/{job_id}` | job read | Full report JSON (gates, issues, scores, dimension scores). |
| POST | `/api/recheck/{job_id}` | job write | Re-run gates after edits (free; concurrency-locked). |
| GET | `/api/history` | caller-scoped | Recent checks for the current owner. |
| GET | `/api/compare/{job_id}` | job read | Compare with the previous check (score/error/warning deltas). |
| GET | `/api/score-trend/{job_id}` | job read | Score trend across checks. |
| GET | `/api/analysis/{job_id}` | job read | Section word counts, citation years, writing-style metrics. |
| DELETE | `/api/job/{job_id}` | job owner | Delete a job and its artifacts. |

### Files

| Method | Path | Access | Purpose |
|---|---|---|---|
| GET | `/api/files/{job_id}` | job read | List editable project files (file tree). |
| GET | `/api/files/{job_id}/{file_path}` | job read | Read a file's content. |
| PUT | `/api/files/{job_id}/{file_path}` | job write | Save a file (text-source allowlist; preserves CRLF/LF). |
| GET | `/api/download/{job_id}` | job read | Download the current project as a ZIP. |

> As of v5.3.94 these four endpoints live in `app/api/file_routes.py`, not the legacy `app/api/routes.py`. URLs are unchanged.

### Issues & Export

| Method | Path | Access | Purpose |
|---|---|---|---|
| POST | `/api/dismiss/{job_id}` | job write | Dismiss an issue with a reason (human-in-the-loop). |
| GET | `/api/export/{job_id}` | job read | Branded Markdown report (author or share-readonly variant). |

### Edit History

| Method | Path | Access | Purpose |
|---|---|---|---|
| GET | `/api/history-edits/{job_id}` | job read | List edit history (newest first); optional `?file=` filter. Metadata only, no file contents. |
| GET | `/api/history-edits/{job_id}/{entry_id}` | job read | One history entry with before/after content for a diff view. |
| POST | `/api/history-edits/{job_id}/{entry_id}/revert` | job write | Revert a file to the entry's "before" content. Recorded as a new history entry. Share-token readers get `403`. |

### Tools

| Method | Path | Access | Purpose |
|---|---|---|---|
| POST | `/api/bib-clean/{job_id}` | job write | Clean/sort BibTeX, separate unused entries. |
| GET | `/api/fetch-bib/{doi}` | open | Fetch official BibTeX for a DOI (ACL/DBLP/ACM/IEEE/Crossref). |
| POST | `/api/reference-candidates/{job_id}` | job read | Search real reference candidates from Crossref/S2/OpenAlex. **No LLM.** |
| GET | `/api/tidyup/{job_id}` | job read | Preview tidyup changes (extract tables to `floats/`). |
| POST | `/api/tidyup/{job_id}` | job write | Apply tidyup. |
| POST | `/api/format-normalize/{job_id}` | job write | Normalize LaTeX formatting (refs, abbreviations, whitespace, conservative cite). |
| POST | `/api/venue-checklist/{job_id}` | job read | Generate ARR or NeurIPS checklist with evidence and rewrite suggestions. |

> As of v5.3.95, the bib/tidyup/format/reference-candidates endpoints live in `app/api/tool_routes.py`; URLs are unchanged.
> As of v5.3.96, the venue-checklist endpoint lives in `app/api/checklist_routes.py`; URL unchanged.

## AI Router (`app/api/ai_routes.py`)

All AI endpoints enforce the reference-authenticity guardrail and LLM usage caps. Outputs are labeled as suggestions/simulations requiring human verification.

| Method | Path | Access | Purpose |
|---|---|---|---|
| POST | `/api/ai-diagnosis/{job_id}` | job read | Structured paper diagnosis (summary, top priorities, quick wins, estimated time, risks, next actions) from gate summaries + LLM, with JSON-tolerant fallback. |
| POST | `/api/ai-fix/{job_id}` | job write | Single-issue fix suggestion with diff/provenance. Reference-authenticity issues return `not_fixable` (no LLM). |
| POST | `/api/ai-batch-fix/{job_id}` | job write | Batch fix suggestions with dry-run summary, by-gate grouping, skipped reasons. Skips reference-authenticity (no LLM). |
| POST | `/api/ai-review/{job_id}` | job read | Simulated reviewer feedback (Strengths/Weaknesses/Questions/Score/Action Items). |
| POST | `/api/ai-polish/{job_id}` | job write | Language polish suggestions (academic/concise/formal). |
| POST | `/api/ai-abstract/{job_id}` | job write | Abstract optimization with a claim-consistency guard. |

## Auth Router (`app/api/auth_routes.py`, prefix `/api/auth`)

| Method | Path | Access | Purpose |
|---|---|---|---|
| POST | `/api/auth/register` | open (rate-limited) | Email/password registration; grants free starting credits. |
| POST | `/api/auth/login` | open (rate-limited) | Login; sets auth cookie. |
| POST | `/api/auth/logout` | any | Clear auth cookie. |
| GET | `/api/auth/me` | user | Current user profile, tier, credits. |
| GET | `/api/auth/transactions` | user | Credit transaction history. |
| GET | `/api/auth/api-tokens` | Pro/Team | List personal API tokens (hash/prefix only). Free tier gets `403`. |
| POST | `/api/auth/api-tokens` | Pro/Team | Create an API token (plaintext returned once). Free tier gets `403`. |
| DELETE | `/api/auth/api-tokens/{token_id}` | Pro/Team | Revoke an API token. Free tier gets `403`. |
| GET | `/api/auth/dashboard` | user | Dashboard data; Team tier also gets `team_dashboard` (avg score, pass rate, needs-attention, low-score list). |

## Payment Router (`app/api/payment_routes.py`, prefix `/api/payment`)

| Method | Path | Access | Purpose |
|---|---|---|---|
| GET | `/api/payment/packages` | open | List purchasable packages with tier entitlements. |
| POST | `/api/payment/create` | user | Create a payment order. |
| GET | `/api/payment/status/{order_id}` | user | Poll order status. |
| POST | `/api/payment/callback/alipay` | external | Payment callback. Idempotent; validates amount and `app_id`. Sandbox auto-credits. |
| POST | `/api/payment/admin/add-credits` | admin | Add credits. Requires `Authorization: Bearer <admin_key>` or `X-Admin-Key`; rate-limited; never accepts the key in the body. |

> Note: the auth and payment routers carry their own `/auth` and `/payment` prefixes, so paths like `/api/payment/status/{order_id}` do not collide with the core router's `/api/status/{job_id}`.

## Guardrail Summary

- Reference-authenticity issues never reach the LLM.
- Reference candidates come only from authoritative sources, never generated.
- Fixes that cannot be precisely anchored are not auto-applied; the user gets a copyable suggestion.
- Share tokens are strictly read-only for write/AI/tool actions.

## Related Documents

- [ARCHITECTURE.md](ARCHITECTURE.md) — system structure and permission model.
- [CONFIGURATION.md](CONFIGURATION.md) — settings and secrets.
