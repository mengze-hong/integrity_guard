"""Tests for job status persistence helpers."""

from app.api import routes


def test_save_failed_report_records_failed_status(monkeypatch):
    saved = {}

    def fake_save_report(job_id, report):
        saved[job_id] = report

    monkeypatch.setattr(routes.storage, "save_report", fake_save_report)
    routes._jobs.pop("failed-job", None)
    routes._job_status.pop("failed-job", None)
    routes._job_owners.pop("failed-job", None)

    routes._save_failed_report(
        "failed-job",
        "paper.zip",
        RuntimeError("boom"),
        {"owner_type": "session", "owner_id": "session-1", "share_token": "share-1"},
    )

    report = saved["failed-job"]
    assert routes._job_status["failed-job"] == "failed"
    assert report.metadata["status"] == "failed"
    assert report.metadata["owner_type"] == "session"
    assert report.metadata["share_token"] == "share-1"
    assert "boom" in report.metadata["error"]

    routes._jobs.pop("failed-job", None)
    routes._job_status.pop("failed-job", None)
    routes._job_owners.pop("failed-job", None)
