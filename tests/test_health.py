"""Tests for health and readiness probes."""

from fastapi.testclient import TestClient

from app.main import app


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
