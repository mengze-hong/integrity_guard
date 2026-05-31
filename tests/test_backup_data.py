"""Tests for local data backup utility."""

import json
import sqlite3
import zipfile
from pathlib import Path

from scripts.backup_data import create_backup


def test_create_backup_includes_data_and_sqlite_consistent_copy(tmp_path):
    data_dir = tmp_path / "data"
    uploads_dir = tmp_path / "uploads"
    output_dir = tmp_path / "backups"
    data_dir.mkdir()
    uploads_dir.mkdir()
    (data_dir / "note.txt").write_text("hello", encoding="utf-8")
    (uploads_dir / "paper.zip").write_text("not included by default", encoding="utf-8")

    db_path = data_dir / "integrity.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE jobs (id TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO jobs VALUES ('job-1')")

    manifest = create_backup(data_dir=data_dir, uploads_dir=uploads_dir, output_dir=output_dir)

    backup_file = Path(manifest["archive"])
    with zipfile.ZipFile(backup_file) as zf:
        names = set(zf.namelist())
        assert "data/note.txt" in names
        assert "data/integrity.db" in names
        assert "uploads/paper.zip" not in names
        archive_manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        assert archive_manifest["file_count"] == 2

        extracted_db = tmp_path / "restored.db"
        extracted_db.write_bytes(zf.read("data/integrity.db"))
        with sqlite3.connect(extracted_db) as conn:
            assert conn.execute("SELECT id FROM jobs").fetchone()[0] == "job-1"


def test_create_backup_can_include_uploads_and_dry_run(tmp_path):
    data_dir = tmp_path / "data"
    uploads_dir = tmp_path / "uploads"
    output_dir = tmp_path / "backups"
    data_dir.mkdir()
    uploads_dir.mkdir()
    (data_dir / "report.json").write_text("{}", encoding="utf-8")
    (uploads_dir / "paper.zip").write_text("zip", encoding="utf-8")

    dry_manifest = create_backup(
        data_dir=data_dir,
        uploads_dir=uploads_dir,
        output_dir=output_dir,
        include_uploads=True,
        dry_run=True,
    )
    assert dry_manifest["archive"] is None
    assert dry_manifest["file_count"] == 2
    assert not output_dir.exists()

    manifest = create_backup(
        data_dir=data_dir,
        uploads_dir=uploads_dir,
        output_dir=output_dir,
        include_uploads=True,
    )
    with zipfile.ZipFile(manifest["archive"]) as zf:
        names = set(zf.namelist())
        assert "data/report.json" in names
        assert "uploads/paper.zip" in names
