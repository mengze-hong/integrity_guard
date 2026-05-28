"""Shared FastAPI dependencies."""

from fastapi import Request, HTTPException
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.auth import decode_token
from app.models_db import User


def get_db():
    """Yield a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_current_user_optional(request: Request) -> User | None:
    """Extract current user from JWT token. Returns None if not authenticated.

    Supports both cookie-based and header-based auth.
    """
    token = request.cookies.get("token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

    if not token:
        return None

    payload = decode_token(token)
    if not payload:
        return None

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == payload["sub"]).first()
        return user
    finally:
        db.close()


async def get_current_user(request: Request) -> User:
    """Require authentication. Raises 401 if not logged in."""
    user = await get_current_user_optional(request)
    if not user:
        raise HTTPException(status_code=401, detail="请先登录")
    return user
