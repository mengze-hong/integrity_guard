# Release Checklist

Use this before every GitHub backup or demo release.

- Confirm `CHANGELOG.md` has a new entry describing user-visible changes and risk-relevant fixes.
- Confirm `app/main.py` version matches the latest changelog entry.
- Run `npm run check:js` to validate inline scripts in `app/templates/index.html`.
- Run the CF tunnel policy scan in PowerShell: `$pattern = ('cloud' + 'flared|try' + 'cloud' + 'flare|cloud' + 'flare'); $hits = @(git grep --untracked -n -i -E $pattern -- . ':!.cursor/**' ':!.git/**' ':!.github/workflows/ci.yml' ':!CHANGELOG.md' ':!data/**' ':!uploads/**' ':!screenshots/**' ':!screenshots_new/**' ':!.playwright-mcp/**'); if ($hits.Count) { $hits; Write-Error 'Forbidden tunnel provider pattern found'; exit 1 } else { 'No forbidden tunnel provider pattern found'; exit 0 }`.
- Run `python -m pytest -q`.
- Run a diff secret scan for internal API keys, internal endpoints, bearer tokens, and `.env` style assignments.
- Check `git status --short` and do not commit `.env`, `data/secrets.enc`, uploaded papers, or `.cursor/plans` unless explicitly requested.
- Commit a small, focused change with a descriptive message.
- Push to GitHub after the commit as an external backup.
- Restart the local demo service only after tests pass.
