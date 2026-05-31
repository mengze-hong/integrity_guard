"""Tests for health and readiness probes."""

from fastapi.testclient import TestClient

from app.main import app
from app.monitoring import request_metrics


def test_healthz_reports_liveness():
    client = TestClient(app)
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "scholarlint"


def test_readyz_never_exposes_secret_values():
    client = TestClient(app)
    response = client.get("/readyz")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"ready", "degraded"}
    assert "checks" in body
    rendered = str(body)
    assert "sk-" not in rendered
    assert "Bearer" not in rendered


def test_metrics_reports_uptime_latency_and_error_rate():
    request_metrics.reset()
    client = TestClient(app)

    client.get("/healthz")
    response = client.get("/metrics")

    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "scholarlint"
    assert body["version"] == app.version
    assert body["uptime_seconds"] >= 0
    assert body["requests_total"] >= 1
    assert body["avg_latency_ms"] >= 0
    assert body["error_rate"] == 0
    assert body["recent_window"]["requests"] >= 1
    assert any(row["path"] == "/healthz" for row in body["endpoints"])


def test_metrics_redacts_high_cardinality_path_segments():
    request_metrics.reset()
    request_metrics.record("GET", "/api/report/job_1234567890abcdef", 500, 12.5)

    body = request_metrics.snapshot(service="scholarlint", version=app.version)

    assert body["requests_total"] == 1
    assert body["errors_total"] == 1
    assert body["error_rate"] == 1
    assert body["endpoints"][0]["path"] == "/api/report/{id}"
    assert "job_1234567890abcdef" not in str(body)
