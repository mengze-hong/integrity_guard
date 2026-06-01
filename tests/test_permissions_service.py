"""Tests for app.services.permissions — the stateless permission helpers.

Covers the share-token reading / Secure-flag policy / owner metadata
extraction / decision-tree access logic that used to live as
underscored helpers in ``app.api.routes``. The legacy bindings in
``routes.py`` are tested indirectly by the upload / job-ownership /
session-cookie suites; this module pins down the unit semantics.
"""

from __future__ import annotations

import pytest
from starlette.requests import Request

from app.config import settings
from app.services import permissions


def _req(scheme: str = "http", **headers) -> Request:
    """Build a minimal starlette Request for unit-level helper tests."""
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({
        "type": "http",
        "scheme": scheme,
        "headers": raw,
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "server": ("testserver", 80),
    })


# ── request_share_token ──────────────────────────────────────


def test_share_token_from_header():
    req = _req(**{"X-Share-Token": "abc123"})
    assert permissions.request_share_token(req) == "abc123"


def test_share_token_missing_returns_empty():
    assert permissions.request_share_token(_req()) == ""


def test_share_token_strips_whitespace():
    req = _req(**{"X-Share-Token": "  spaced  "})
    assert permissions.request_share_token(req) == "spaced"


# ── secure_session_cookie ────────────────────────────────────


def test_secure_cookie_in_production(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    assert permissions.secure_session_cookie(_req()) is True


def test_secure_cookie_in_prod_alias(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "prod")
    assert permissions.secure_session_cookie(_req()) is True


def test_secure_cookie_local_plain_http(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "local")
    assert permissions.secure_session_cookie(_req()) is False


def test_secure_cookie_xforwarded_proto_https(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "local")
    req = _req(**{"x-forwarded-proto": "https"})
    assert permissions.secure_session_cookie(req) is True


# ── owner_metadata / extract_owner_metadata ──────────────────


def test_owner_metadata_auto_generates_share_token():
    metadata = permissions.owner_metadata({"owner_type": "user", "owner_id": "u1"})
    assert metadata["owner_type"] == "user"
    assert metadata["owner_id"] == "u1"
    assert isinstance(metadata["share_token"], str) and len(metadata["share_token"]) > 16
    # session_id only present when the input owner had one
    assert "session_id" not in metadata


def test_owner_metadata_preserves_session_id():
    metadata = permissions.owner_metadata({
        "owner_type": "session",
        "owner_id": "sess-1",
        "session_id": "sess-1",
    })
    assert metadata["session_id"] == "sess-1"


def test_owner_metadata_keeps_explicit_share_token():
    metadata = permissions.owner_metadata(
        {"owner_type": "user", "owner_id": "u1"},
        share_token="explicit-token",
    )
    assert metadata["share_token"] == "explicit-token"


def test_extract_owner_metadata_missing_fields_become_none():
    extracted = permissions.extract_owner_metadata({"owner_type": "user"})
    assert extracted == {
        "owner_type": "user",
        "owner_id": None,
        "session_id": None,
        "share_token": None,
    }


# ── owner_metadata_allows decision tree ──────────────────────


async def _owner_loader(_request, _response):
    """Stub loader returning a fixed owner."""
    return {"owner_type": "user", "owner_id": "u1"}


async def _other_owner_loader(_request, _response):
    return {"owner_type": "user", "owner_id": "someone-else"}


@pytest.mark.asyncio
async def test_legacy_metadata_allowed_in_local(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "local")
    allowed = await permissions.owner_metadata_allows(
        {},
        _req(),
        None,
        request_owner_loader=_owner_loader,
    )
    assert allowed is True


@pytest.mark.asyncio
async def test_legacy_metadata_denied_in_production(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    allowed = await permissions.owner_metadata_allows(
        {},
        _req(),
        None,
        request_owner_loader=_owner_loader,
    )
    assert allowed is False


@pytest.mark.asyncio
async def test_owner_match_grants_write(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "local")
    metadata = {"owner_type": "user", "owner_id": "u1", "share_token": "tok"}
    allowed = await permissions.owner_metadata_allows(
        metadata,
        _req(),
        None,
        request_owner_loader=_owner_loader,
        write=True,
    )
    assert allowed is True


@pytest.mark.asyncio
async def test_share_token_grants_read_only(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "local")
    metadata = {"owner_type": "user", "owner_id": "u1", "share_token": "tok"}
    req = _req(**{"X-Share-Token": "tok"})
    # Different owner but valid share token
    can_read = await permissions.owner_metadata_allows(
        metadata, req, None, request_owner_loader=_other_owner_loader
    )
    can_write = await permissions.owner_metadata_allows(
        metadata, req, None, request_owner_loader=_other_owner_loader, write=True
    )
    assert can_read is True
    assert can_write is False


@pytest.mark.asyncio
async def test_share_token_blocked_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "local")
    metadata = {"owner_type": "user", "owner_id": "u1", "share_token": "tok"}
    req = _req(**{"X-Share-Token": "tok"})
    allowed = await permissions.owner_metadata_allows(
        metadata,
        req,
        None,
        request_owner_loader=_other_owner_loader,
        allow_share=False,
    )
    assert allowed is False


@pytest.mark.asyncio
async def test_wrong_share_token_denied(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "local")
    metadata = {"owner_type": "user", "owner_id": "u1", "share_token": "tok"}
    req = _req(**{"X-Share-Token": "WRONG"})
    allowed = await permissions.owner_metadata_allows(
        metadata, req, None, request_owner_loader=_other_owner_loader
    )
    assert allowed is False
