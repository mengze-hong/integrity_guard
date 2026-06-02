# Documentation

Use this directory as the starting point for local operation, release checks, and future deployment notes.

## Available Guides

- [Architecture](ARCHITECTURE.md) — system structure, request flow, quality gates, services, AI guardrails, permission model, storage, and known risks.
- [Configuration](CONFIGURATION.md) — every setting and secret, defaults, sourcing order, and production tips.
- [API Overview](API_OVERVIEW.md) — endpoint reference grouped by router, with access requirements.
- [Local Run Guide](LOCAL_RUN.md) — install dependencies, initialize secrets, start the app locally, run Docker Compose, and check readiness.
- [Testing Guide](TESTING_GUIDE.md) — focused commands by change type, full pre-commit checks, coverage, dependency audit, and policy scans.
- [Release Checklist](RELEASE_CHECKLIST.md) — pre-release checks for tests, scans, docs, and version alignment.
- [Do Not Do](DO_NOT_DO.md) — operational guardrails for research integrity, repository hygiene, secrets, and public exposure.
- [Safe Production Deployment](DEPLOY_SAFE.md) — Docker, reverse proxy, HTTPS, production switches, secrets, upload safety, probes, backups, and public exposure checks.
- [Tencent Cloud Lighthouse Deployment](DEPLOY_TENCENT.md) — concrete walkthrough for hosting on Tencent Cloud Lighthouse: instance sizing, secret injection, Nginx + Tencent SSL, ICP filing, COS-backed backups.
- [Backup And Restore](BACKUP.md) — local backup script usage, upload backup boundaries, encrypted storage reminders, and restore smoke checks.

For a top-level project overview and quick start, see the [root README](../README.md). For handover notes and next steps, see [HANDOVER.md](../HANDOVER.md).
