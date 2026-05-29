# Release Checklist

Use this before every GitHub backup or demo release.

- Confirm `CHANGELOG.md` has a new entry describing user-visible changes and risk-relevant fixes.
- Confirm `app/main.py` version matches the latest changelog entry.
- Run JavaScript syntax validation for inline scripts in `app/templates/index.html`.
- Run `python -m pytest -q`.
- Run a diff secret scan for internal API keys, internal endpoints, bearer tokens, and `.env` style assignments.
- Check `git status --short` and do not commit `.env`, `data/secrets.enc`, uploaded papers, or `.cursor/plans` unless explicitly requested.
- Commit a small, focused change with a descriptive message.
- Push to GitHub after the commit as an external backup.
- Restart the local demo service only after tests pass.
