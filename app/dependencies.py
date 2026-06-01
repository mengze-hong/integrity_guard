"""Shared FastAPI dependencies."""

import hashlib
from datetime import datetime, timezone

from fastapi import Request, HTTPException

from app.database import SessionLocal
from app.auth import decode_token
from app.models_db import ApiToken, User

# Personal API tokens issued to Pro/Team users carry this prefix; see
# auth_routes._new_api_token. Anything Bearer-style starting with this prefix
# is looked up against the api_tokens table by SHA-256 hash, instead of being
# decoded as a JWT.
API_TOKEN_PREFIX = "sl_api_"


def get_db():
    """Yield a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _hash_api_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _user_for_api_token(plaintext: str) -> User | None:
    """Resolve a plaintext API token to its user, or None if invalid/revoked.

    Updates ``last_used_at`` on a successful match for audit visibility.
    Failures (unknown hash, revoked token, missing user) return None silently.
    The returned ``User`` is detached so callers can read its attributes
    after the session closes without triggering a lazy refresh.
    """
    db = SessionLocal()
    try:
        record = (
            db.query(ApiToken)
            .filter(ApiToken.token_hash == _hash_api_token(plaintext))
            .first()
        )
        if record is None or record.revoked_at is not None:
            return None
        user_id = record.user_id
        record.last_used_at = datetime.now(timezone.utc).isoformat()
        db.commit()

        # Re-fetch the user after commit so its attributes are loaded fresh,
        # then detach it from the session before returning.
        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            return None
        db.expunge(user)
        return user
    finally:
        db.close()


async def get_current_user_optional(request: Request) -> User | None:
    """Extract the current user from a session cookie, JWT, or API token.

    Returns ``None`` when no credential is present or any presented credential
    is invalid. Resolution order:

    1. ``token`` cookie (JWT for browser sessions).
    2. ``Authorization: Bearer <api_token>`` whose value starts with
       ``sl_api_`` — looked up in ``api_tokens`` by SHA-256 hash.
    3. ``Authorization: Bearer <jwt>`` — same JWT decoder as the cookie.
    """
    cookie_jwt = request.cookies.get("token")
    if cookie_jwt:
        payload = decode_token(cookie_jwt)
        if payload:
            db = SessionLocal()
            try:
                return db.query(User).filter(User.id == payload["sub"]).first()
            finally:
                db.close()
        return None

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        bearer = auth_header[7:].strip()
        if bearer.startswith(API_TOKEN_PREFIX):
            return _user_for_api_token(bearer)
        if bearer:
            payload = decode_token(bearer)
            if payload:
                db = SessionLocal()
                try:
                    return db.query(User).filter(User.id == payload["sub"]).first()
                finally:
                    db.close()
    return None


async def get_current_user(request: Request) -> User:
    """Require authentication. Raises 401 if not logged in."""
    user = await get_current_user_optional(request)
    if not user:
        raise HTTPException(status_code=401, detail="请先登录")
    return user
