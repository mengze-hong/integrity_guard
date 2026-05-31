# Backup And Restore

Use this guide before running a production demo or changing storage layout.

## What To Back Up

- `data/integrity.db` for users, credits, orders, and application state.
- `data/jobs/` for encrypted report JSON and job metadata.
- `data/secrets.enc` if encrypted secrets are used. The OS vault master key is still required to read it after restore.
- `uploads/` only when you intentionally need uploaded archives or extracted project files. They may contain full user papers and can grow quickly.

## Create A Backup

Default backup, excluding uploads:

```bash
python scripts/backup_data.py
```

Include uploads when a full restore of active project files is required:

```bash
python scripts/backup_data.py --include-uploads
```

Preview what would be included without writing an archive:

```bash
python scripts/backup_data.py --dry-run --include-uploads
```

Backups are written to `backups/scholarlint-backup-<timestamp>.zip` and include a `manifest.json`. Keep this directory out of git and store archives in encrypted storage.

## Restore Checklist

- Stop the app or make sure no writes are running.
- Restore the `data/` files from the archive.
- Restore `uploads/` only if the backup intentionally included it.
- Restore the OS vault master key before relying on `data/secrets.enc`.
- Start the app and check `/healthz`, `/readyz`, and `/metrics`.
- Run a small upload or report-read smoke test before exposing the restored instance.
