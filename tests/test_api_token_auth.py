"""Tests for API token authentication via app.dependencies."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import dependencies
from app.database import Base
from app.models_db import ApiToken, User


@pytest.fixture()
def temp_db(monkeypatch):
    """In-memory DB shared across the dependency layer for one test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(dependencies, "SessionLocal", TestingSessionLocal)
    return TestingSessionLocal


def _make_user(db_factory, *, email="alice@example.com") -> str:
    """Insert a user; return the id (not the ORM instance, to avoid detached refresh)."""
    db = db_factory()
    user = User(id="u-1", email=email, password_hash="x", tier="pro")
    db.add(user)
    db.commit()
    user_id = user.id
    db.close()
    return user_id


def _make_token(db_factory, user_id: str, plaintext: str, *, revoked: bool = False) -> None:
    db = db_factory()
    record = ApiToken(
        id="tok-1",
        user_id=user_id,
        name="ci",
        token_hash=dependencies._hash_api_token(plaintext),
        token_prefix=plaintext[:8],
        revoked_at=datetime.now(timezone.utc).isoformat() if revoked else None,
    )
    db.add(record)
    db.commit()
    db.close()


def _bearer_request(token: str | None) -> Request:
    """Build a minimal Request with no cookie and the given Bearer header."""
    headers = []
    if token is not None:
        headers.append((b"authorization", f"Bearer {token}".encode()))
    scope = {
        "type": "http",
        "headers": headers,
        "method": "GET",
        "path": "/",
        "query_string": b"",
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_valid_api_token_returns_user(temp_db):
    user_id = _make_user(temp_db)
    plaintext = "sl_api_abcdefghij1234567890"
    _make_token(temp_db, user_id, plaintext)

    request = _bearer_request(plaintext)
    resolved = await dependencies.get_current_user_optional(request)

    assert resolved is not None
    assert resolved.id == user_id


@pytest.mark.asyncio
async def test_unknown_api_token_returns_none(temp_db):
    _make_user(temp_db)
    request = _bearer_request("sl_api_NOT_A_REAL_TOKEN_xxx")
    assert await dependencies.get_current_user_optional(request) is None


@pytest.mark.asyncio
async def test_revoked_api_token_returns_none(temp_db):
    user_id = _make_user(temp_db)
    plaintext = "sl_api_revokedtoken1234567890"
    _make_token(temp_db, user_id, plaintext, revoked=True)

    request = _bearer_request(plaintext)
    assert await dependencies.get_current_user_optional(request) is None


@pytest.mark.asyncio
async def test_api_token_updates_last_used_at(temp_db):
    user_id = _make_user(temp_db)
    plaintext = "sl_api_lastusedcheck1234567"
    _make_token(temp_db, user_id, plaintext)

    request = _bearer_request(plaintext)
    await dependencies.get_current_user_optional(request)

    db = temp_db()
    rec = db.query(ApiToken).filter(ApiToken.user_id == user_id).first()
    last_used = rec.last_used_at
    db.close()
    assert last_used is not None


@pytest.mark.asyncio
async def test_no_credentials_returns_none(temp_db):
    request = _bearer_request(None)
    assert await dependencies.get_current_user_optional(request) is None


@pytest.mark.asyncio
async def test_jwt_bearer_still_works(temp_db, monkeypatch):
    """Non-API-token Bearer values must still be tried as JWTs (backward compat)."""
    user_id = _make_user(temp_db)
    monkeypatch.setattr(dependencies, "decode_token", lambda t: {"sub": user_id} if t == "valid.jwt.token" else None)

    request = _bearer_request("valid.jwt.token")
    resolved = await dependencies.get_current_user_optional(request)
    assert resolved is not None and resolved.id == user_id


@pytest.mark.asyncio
async def test_invalid_jwt_bearer_returns_none(temp_db, monkeypatch):
    monkeypatch.setattr(dependencies, "decode_token", lambda t: None)
    request = _bearer_request("not.a.valid.jwt")
    assert await dependencies.get_current_user_optional(request) is None
