# ScholarLint · 投稿通 Handover

Last updated: 2026-05-31
Current app version: `5.3.81`
Current branch: `main`
Latest pushed commit before this handover: `a7a0214 feat: add paid tier api tokens`

This document is for the next AI/agent taking over the project. Read this before changing code.

## Project Goal
ScholarLint · 投稿通 is a pre-submission quality gate SaaS for academic LaTeX papers. It checks ZIP uploads before conference submission, surfaces strict rule-based and LLM-assisted issues, supports editor-based fixes, reports, account tiers, credits, payments, team dashboards, and future API/automation usage.

Primary product direction:
- Commercializable SaaS, not a research toy.
- Strict checking is acceptable; false positives are better than missed serious integrity issues.
- Prioritize maintainability, security, docs, and robust iterative delivery.
- Do not add low-value or high-complexity features just because they are interesting.

## Non-Negotiable Operating Rules
- Reply to the user in Chinese.
- Keep iterating proactively; do not wait for loop ticks.
- For each completed change: update `TODO.md` and `CHANGELOG.md`, run relevant validation, commit, and push if the user has asked for continuous committed iteration.
- Never use unapproved public tunnel exposure. CI has a forbidden tunnel provider policy scan.
- Do not put secrets, real credentials, uploaded papers, backups, `.env`, `data/secrets.enc`, or `uploads/` into git.
- Do not make irreversible production/data/destructive changes without explicit user approval.
- External accounts, payment credentials, legal/compliance decisions, or final brand decisions are blockers; otherwise continue with sensible defaults.

## Current State Summary
The repo has moved quickly from feature completion toward commercialization scaffolding.

Recently completed:
- Free tier aligned to 3 free checks and monthly lazy refresh.
- Pro/Team users get unlimited full checks.
- Paid packages upgrade tier:
  - `pro` package upgrades user to `pro`.
  - `lab` package upgrades user to `team`.
- Team mentor dashboard in account modal:
  - average score
  - pass rate
  - needs-attention count
  - low-score paper list
- Hardened GitHub Actions CI:
  - `ruff`
  - `npm ci`
  - JS syntax check
  - JS helper tests
  - secret scan
  - forbidden tunnel provider policy scan
  - pytest with coverage
- Pro/Team API Token foundation:
  - `api_tokens` DB table
  - create/list/revoke endpoints
  - token plaintext returned only once
  - server stores SHA-256 hash and short prefix only
  - Free tier gets 403

## Current Architecture
Important paths:
- `app/main.py` — FastAPI app, routers, middleware, security headers, health/ready/metrics.
- `app/api/routes.py` — still large legacy/core router: upload, jobs, files, reports, export, history, compare, checklist helpers, tool endpoints.
- `app/api/ai_routes.py` — AI endpoints, still depends on some private helpers in `routes.py`.
- `app/api/auth_routes.py` — register/login/me/dashboard/API tokens.
- `app/api/payment_routes.py` — packages, sandbox payment, callback, admin credits.
- `app/models_db.py` — SQLite ORM for users, transactions, payment orders, API tokens.
- `app/storage.py` — encrypted report persistence under `data/jobs/`, with plaintext fallback if crypto unavailable.
- `app/checks/` — quality gates.
- `app/parsers/` — LaTeX/BibTeX parsing.
- `app/services/` — newer service helpers; still incomplete as architecture boundary.
- `app/templates/index.html` — very large single-page UI. This is a major maintainability risk.
- `app/static/js/helpers.js` — extracted/tested frontend helper functions.
- `docs/` — local run, testing, release, safe deploy, backup, do-not-do docs.
- `tests/` — pytest suite; currently about 100 tests.

High-level request flow:
1. User uploads ZIP through `/api/upload`.
2. ZIP is validated/extracted.
3. Gate runner logic inside `app/api/routes.py` creates `FullReport`.
4. Reports are persisted through `app/storage.py`.
5. UI loads report/files and offers fixes, export, sharing, dashboard, and history.
6. Auth/payment/tier logic lives in SQLite.

## Known Engineering Problems
Highest priority maintainability issues:
- No root `README.md` yet. GitHub onboarding is weak.
- `app/api/routes.py` is still too large and mixes too many responsibilities.
- `app/templates/index.html` is overgrown and should be gradually split into static JS modules.
- Tests have duplicated fixtures and state cleanup; there is no shared `tests/conftest.py`.
- `ai_routes.py` still imports private legacy helpers from `routes.py`.
- Job data is split across encrypted JSON reports, upload folders, and in-memory route state.
- `pyproject.toml` version is `0.1.0`; app release version is in `app/main.py` and `CHANGELOG.md`.

Important plan file:
- `工程基线强化_5884ad9d.plan.md` was created for the maintainability/security/docs strengthening plan.
- If continuing the engineering hardening work, follow that plan in small commits.

## Security Notes
Already good:
- ZIP Slip / dangerous file cleanup / zip bomb style protections exist and have tests.
- Share token is read-only for protected write/AI actions.
- Secret scan and forbidden tunnel scan exist in CI.
- Baseline browser security headers exist.
- API tokens are stored hashed, not plaintext.

Needs improvement before public production:
- Legacy jobs without owner metadata may be too permissive. Tighten production behavior.
- API Tokens exist but are not yet accepted by actual business API dependencies.
- Real Alipay production signing/verification is not implemented. Sandbox auto-credit works for MVP testing only.
- Admin credit endpoint must stay protected by strong secret plus reverse proxy/network ACL in production.
- `/metrics` has no app-level auth; protect via reverse proxy or add app-level auth.
- Global exception redaction should cover JWT/admin/payment/API-token patterns more aggressively.
- `sl_session` anonymous cookie secure behavior should be aligned with auth cookies.
- Rate limiting is in-memory and not multi-instance safe.
- Extracted uploaded papers are plaintext in `uploads/` until retention cleanup.

## Verification Commands
Run these after meaningful changes:

```powershell
python -m ruff check app/ tests/ scripts/backup_data.py --select E,F,W --ignore E501
npm ci
npm run check:js
npm run test:js
npm run scan:secrets
python -m pytest -q
```

Forbidden tunnel provider policy scan for PowerShell:

```powershell
$pattern = ('cloud' + 'flared|try' + 'cloud' + 'flare|cloud' + 'flare')
$hits = @(git grep --untracked -n -i -E $pattern -- . ':!.cursor/**' ':!.git/**' ':!_Archive/**' ':!CHANGELOG.md' ':!data/**' ':!uploads/**')
if ($hits.Count) { $hits; Write-Error 'Forbidden tunnel provider pattern found'; exit 1 } else { 'No forbidden tunnel provider pattern found'; exit 0 }
```

Focused tests by area:
- Auth/payment/tier/API token: `python -m pytest -q tests/test_auth_payment_security.py`
- Upload/ZIP/file safety: `python -m pytest -q tests/test_upload_api.py tests/test_parsers.py tests/test_file_store.py`
- Ownership/share token: `python -m pytest -q tests/test_job_ownership.py`
- AI guardrails: `python -m pytest -q tests/test_ai_routes.py tests/test_ai_integrity.py`
- Health/metrics: `python -m pytest -q tests/test_health.py`
- Frontend helpers: `npm run check:js && npm run test:js`

## Recommended Next Work
Follow this order. Keep each step small and commit after validation.

1. Documentation baseline:
   - Add root `README.md`.
   - Add `docs/ARCHITECTURE.md`.
   - Add `docs/CONFIGURATION.md`.
   - Add `docs/API_OVERVIEW.md`.
   - Update `docs/README.md`, `docs/TESTING_GUIDE.md`, and `docs/RELEASE_CHECKLIST.md`.

2. Security baseline:
   - Tighten legacy no-owner job behavior in production.
   - Extend API token authentication in `app/dependencies.py`.
   - Add API token end-to-end tests.
   - Improve redaction for JWT/admin/payment/API-token secrets.
   - Align anonymous `sl_session` cookie secure behavior.

3. Test maintainability:
   - Add `tests/conftest.py`.
   - Move shared DB/client/route-state fixtures into it.
   - Refactor one test file at a time.

4. Backend architecture:
   - Extract `app/services/job_runtime.py`.
   - Extract `app/services/check_runner.py`.
   - Extract report export logic.
   - Gradually split `app/api/routes.py` without changing existing URL paths.

5. Frontend maintainability:
   - Do not rewrite to React/Vue yet.
   - First extract static JS modules from `index.html`:
     - `api.js`
     - `auth.js`
     - `dashboard.js`
     - `workspace.js`
     - `editor.js`
   - Keep JS syntax/helper tests green.

## Current TODO Highlights
Open valuable tasks:
- Pro tier still says: unlimited checks + LLM deep analysis + Copilot fix + priority API. Unlimited checks and API Token foundation are done; LLM deep analysis/priority API behavior still incomplete.
- Team tier still says: mentor dashboard + batch checks + API access. Mentor dashboard is partially done; batch/API workflow is not complete.
- OAuth login is not done.
- Real Stripe/Alipay production integration is not done.
- Root README and architecture docs are not done.
- Route/frontend modularization is not done.

## Recent Commit Trail
Useful recent commits:
- `a7a0214 feat: add paid tier api tokens`
- `b260bf9 ci: harden safety checks`
- `08bc1dc feat: add team mentor dashboard`
- `095b307 feat: upgrade tiers from paid packages`
- `65c8ae4 feat: add paid tier unlimited checks`
- `50f944e feat: refresh free tier credits monthly`
- `fa23dd1 fix: align free tier credit checks`
- `bfffbc8 feat: add multi-dimensional paper scores`

## Prior Conversation Reference
If using Cursor's previous chat history, see [ScholarLint continuous iteration](0f7637a0-1a05-4568-9bea-e0334f14b8c6).

## Do Not Do Next
- Do not start a full Vue/React rewrite.
- Do not migrate jobs to PostgreSQL/ORM before docs/security/fixtures are stable.
- Do not expose the dev server publicly through any tunnel provider.
- Do not implement real payment collection without proper signature verification and external credentials.
- Do not weaken reference authenticity safeguards or allow AI to fabricate references.
- Do not commit data, uploads, backups, screenshots containing private paper content, or secrets.

