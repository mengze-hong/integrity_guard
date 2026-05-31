# Release Checklist

Use this before every GitHub backup or demo release.

- Confirm `CHANGELOG.md` has a new entry describing user-visible changes and risk-relevant fixes.
- Confirm `app/main.py` `version` matches the top `CHANGELOG.md` entry before cutting a release.
- Confirm `docs/README.md` links the current local run, testing, release checklist, `docs/DO_NOT_DO.md`, and `docs/DEPLOY_SAFE.md` docs.
- Review `docs/DO_NOT_DO.md` before release prep and confirm the change does not violate research integrity, repository hygiene, secrets, or public exposure guardrails.
- Read `docs/DEPLOY_SAFE.md` before any production release and confirm production switches, especially `APP_ENV=production` and `PAYMENT_SANDBOX=false` when real payments are enabled.
- Confirm `docs/BACKUP.md` backup/restore steps are still valid after any storage, database, upload, or secret-store change.
- Run the relevant focused checks from `docs/TESTING_GUIDE.md` for the files changed.
- Run `ruff check app/ tests/ --select E,F,W --ignore E501`.
- Run the full pre-commit command set in `docs/TESTING_GUIDE.md`, including JS checks, policy scans, dependency audit, secret scan, and coverage.
- Check `git status --short` and do not commit `.env`, `data/secrets.enc`, uploaded papers, or `.cursor/plans` unless explicitly requested.
- Commit a small, focused change with a descriptive message.
- Push to GitHub after the commit as an external backup.
- Restart the local demo service only after tests pass.
