"""Create a local ScholarLint data backup archive.

This script intentionally writes a plain ZIP file for portability. Store the
result in encrypted storage if it contains user papers, reports, or secrets.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


DEFAULT_DATA_DIR = Path("data")
DEFAULT_UPLOADS_DIR = Path("uploads")
DEFAULT_OUTPUT_DIR = Path("backups")
SQLITE_SUFFIXES = {".db", ".sqlite", ".sqlite3"}


@dataclass(frozen=True)
class BackupSource:
    root: Path
    archive_prefix: str


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _iter_files(source: BackupSource) -> list[Path]:
    if not source.root.exists():
        return []
    return sorted(path for path in source.root.rglob("*") if path.is_file())


def _archive_name(source: BackupSource, file_path: Path) -> str:
    rel = file_path.relative_to(source.root).as_posix()
    return f"{source.archive_prefix}/{rel}"


def _add_sqlite_backup(zip_file: zipfile.ZipFile, source_file: Path, archive_name: str) -> None:
    with tempfile.TemporaryDirectory(prefix="scholarlint-db-backup-") as tmp_dir:
        backup_path = Path(tmp_dir) / source_file.name
        with closing(sqlite3.connect(source_file)) as src, closing(sqlite3.connect(backup_path)) as dst:
            src.backup(dst)
        zip_file.write(backup_path, archive_name)


def create_backup(
    *,
    data_dir: Path = DEFAULT_DATA_DIR,
    uploads_dir: Path = DEFAULT_UPLOADS_DIR,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    include_uploads: bool = False,
    dry_run: bool = False,
) -> dict:
    """Create a backup archive and return a JSON-serializable manifest."""
    sources = [BackupSource(data_dir, "data")]
    if include_uploads:
        sources.append(BackupSource(uploads_dir, "uploads"))

    files: list[tuple[BackupSource, Path]] = []
    for source in sources:
        files.extend((source, path) for path in _iter_files(source))

    manifest = {
        "created_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "include_uploads": include_uploads,
        "sources": [str(source.root) for source in sources],
        "file_count": len(files),
        "sqlite_files": [
            _archive_name(source, path)
            for source, path in files
            if path.suffix.lower() in SQLITE_SUFFIXES
        ],
    }

    if dry_run:
        manifest["archive"] = None
        return manifest

    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / f"scholarlint-backup-{_utc_stamp()}.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        for source, file_path in files:
            archive_name = _archive_name(source, file_path)
            if file_path.suffix.lower() in SQLITE_SUFFIXES:
                _add_sqlite_backup(zip_file, file_path, archive_name)
            else:
                zip_file.write(file_path, archive_name)
        zip_file.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    manifest["archive"] = str(archive_path)
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a ScholarLint data backup ZIP.")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--uploads-dir", type=Path, default=DEFAULT_UPLOADS_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--include-uploads", action="store_true", help="Include uploaded archives and extracted projects.")
    parser.add_argument("--dry-run", action="store_true", help="Print manifest without writing an archive.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = create_backup(
        data_dir=args.data_dir,
        uploads_dir=args.uploads_dir,
        output_dir=args.output_dir,
        include_uploads=args.include_uploads,
        dry_run=args.dry_run,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
