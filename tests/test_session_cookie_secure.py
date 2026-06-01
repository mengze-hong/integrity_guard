"""Tests for anonymous sl_session cookie Secure-flag alignment."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import routes
from app.config import settings
from tests.conftest import clear_route_state


@pytest.fixture()
def session_app():
    clear_route_state()
    app = FastAPI()
    app.include_router(routes.router, prefix="/api")
    yield TestClient(app)
    clear_route_state()


def _set_cookie_header(response) -> str:
    """Return the raw Set-Cookie header for the anonymous session, or ''."""
    for k, v in response.headers.items():
        if k.lower() == "set-cookie" and "sl_session=" in v:
            return v
    # multiple Set-Cookie headers
    for hdr in response.headers.raw if hasattr(response.headers, "raw") else []:
        name, value = hdr
        if name.lower() == b"set-cookie" and b"sl_session=" in value:
            return value.decode()
    return ""


def _trigger_session(client: TestClient, **headers) -> str:
    """Call any owner-aware endpoint to force the anonymous cookie to be set.

    `/api/history` is a read endpoint that resolves the request owner and
    therefore writes the sl_session cookie if absent.
    """
    r = client.get("/api/history", headers=headers)
    return _set_cookie_header(r)


def test_local_env_does_not_set_secure_flag(session_app, monkeypatch):
    monkeypatch.setattr(settings, "app_env", "local")
    cookie = _trigger_session(session_app)
    assert "sl_session=" in cookie
    assert "Secure" not in cookie  # casing matters in HTTP


def test_production_env_forces_secure_flag(session_app, monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    cookie = _trigger_session(session_app)
    assert "sl_session=" in cookie
    assert "Secure" in cookie


def test_prod_alias_forces_secure_flag(session_app, monkeypatch):
    monkeypatch.setattr(settings, "app_env", "prod")
    cookie = _trigger_session(session_app)
    assert "Secure" in cookie


def test_xforwarded_proto_https_sets_secure(session_app, monkeypatch):
    """Behind a reverse proxy that terminates TLS, x-forwarded-proto=https
    must trigger Secure even in local env."""
    monkeypatch.setattr(settings, "app_env", "local")
    cookie = _trigger_session(session_app, **{"x-forwarded-proto": "https"})
    assert "Secure" in cookie


def test_helper_returns_true_when_app_env_is_production(monkeypatch):
    """Lock in the production short-circuit even without a request hint."""
    from starlette.requests import Request

    monkeypatch.setattr(settings, "app_env", "production")
    req = Request({
        "type": "http",
        "scheme": "http",
        "headers": [],
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "server": ("testserver", 80),
    })
    assert routes._secure_session_cookie(req) is True


def test_helper_returns_false_in_local_plain_http(monkeypatch):
    from starlette.requests import Request

    monkeypatch.setattr(settings, "app_env", "local")
    req = Request({
        "type": "http",
        "scheme": "http",
        "headers": [],
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "server": ("testserver", 80),
    })
    assert routes._secure_session_cookie(req) is False
