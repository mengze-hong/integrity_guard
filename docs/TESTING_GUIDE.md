# Testing Guide

Use the focused command for the area you changed, then run the full pre-commit set before a backup, demo, or PR. Commands below match the current `package.json`, GitHub Actions workflow, and test file layout.

## Full Pre-Commit

Run these from the repository root:

```powershell
ruff check app/ tests/ --select E,F,W --ignore E501
npm run check:js
npm run test:js
$pattern = ('cloud' + 'flared|try' + 'cloud' + 'flare|cloud' + 'flare'); $hits = @(git grep --untracked -n -i -E $pattern -- . ':!.cursor/**' ':!.git/**' ':!.github/workflows/ci.yml' ':!_Archive/**' ':!CHANGELOG.md' ':!data/**' ':!uploads/**'); if ($hits.Count) { $hits; Write-Error 'Forbidden tunnel provider pattern found'; exit 1 } else { 'No forbidden tunnel provider pattern found'; exit 0 }
npm run scan:secrets
pip-audit -r requirements.txt
python -m pytest -q --cov=app --cov-report=term-missing --cov-fail-under=20
```

For a faster local smoke check while iterating:

```powershell
npm run check:js
npm run test:js
python -m pytest -q
```

## Frontend JS

Run after editing `app/templates/index.html`, inline handlers, or `app/static/js/helpers.js`:

```powershell
npm run check:js
npm run test:js
```

## AI Routes And Integrity

Run after editing `/api/ai-*` routes, AI guardrails, diagnosis reports, batch fixes, or LLM payload handling:

```powershell
python -m pytest -q tests/test_ai_routes.py tests/test_ai_integrity.py
```

## Upload And File Security

Run after editing upload handling, ZIP extraction, file read/write APIs, path validation, or security headers:

```powershell
python -m pytest -q tests/test_upload_api.py tests/test_file_store.py tests/test_security_headers.py
```

## Parsers And Gates

Run after editing TeX/BibTeX parsing, checklist templates, gate logic, or external reference resilience:

```powershell
python -m pytest -q tests/test_parsers.py tests/test_gates.py tests/test_checklists.py tests/test_reference_resilience.py
```

## Auth And Payment

Run after editing login, session ownership, share-token permissions, credits, admin recharge, payment orders, or callbacks:

```powershell
python -m pytest -q tests/test_auth_payment_security.py tests/test_job_ownership.py
```

## Export And Brand

Run after editing report export, Markdown branding, certificates, health/readiness metadata, or user-facing brand text:

```powershell
python -m pytest -q tests/test_export_report.py tests/test_health.py
```

If the change touches browser-rendered template text or JS handlers, also run:

```powershell
npm run check:js
```

## Minimal E2E

Run after changing upload-to-report flows, file editing, save/recheck behavior, or route wiring:

```powershell
python -m pytest -q tests/test_e2e_minimal.py
```

## Dependency Audit And Coverage

Run after dependency changes or before a release candidate:

```powershell
pip-audit -r requirements.txt
python -m pytest -q --cov=app --cov-report=term-missing --cov-fail-under=20
```
