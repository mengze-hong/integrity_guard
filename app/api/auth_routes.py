"""Authentication API routes: register, login, profile, OAuth."""

import os
import time
from collections import defaultdict
from fastapi import APIRouter, HTTPException, Depends, Response, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import (
    register_user, authenticate_user, create_token,
)
from app.models_db import User
from app.dependencies import get_current_user, get_current_user_optional
from app.credits import get_balance, get_transactions
from app.models_db import User, Transaction

router = APIRouter(prefix="/auth", tags=["auth"])

# --- Simple in-memory rate limiter for login/register brute-force protection ---
_login_attempts: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT_WINDOW = 300  # 5 minutes
_RATE_LIMIT_MAX = 10  # max attempts per window


def _check_rate_limit(key: str):
    """Raise 429 if too many attempts in the window."""
    now = time.time()
    attempts = _login_attempts[key]
    # Prune old entries
    _login_attempts[key] = [t for t in attempts if now - t < _RATE_LIMIT_WINDOW]
    if len(_login_attempts[key]) >= _RATE_LIMIT_MAX:
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")
    _login_attempts[key].append(now)
    # Bound cache size: remove keys older than window
    if len(_login_attempts) > 10000:
        stale_keys = [k for k, v in _login_attempts.items() if not v or now - v[-1] > _RATE_LIMIT_WINDOW]
        for k in stale_keys:
            del _login_attempts[k]


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str = None


class LoginRequest(BaseModel):
    email: str
    password: str


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _secure_cookie(request: Request) -> bool:
    """Use secure cookies automatically behind HTTPS / production deployments."""
    if os.environ.get("APP_ENV", "").lower() in {"prod", "production"}:
        return True
    return (
        request.url.scheme == "https"
        or request.headers.get("x-forwarded-proto", "").lower() == "https"
    )


def _set_auth_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        "token",
        token,
        httponly=True,
        secure=_secure_cookie(request),
        max_age=7 * 86400,
        samesite="lax",
    )


@router.post("/register")
async def register(body: RegisterRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    """Register a new user with email + password."""
    _check_rate_limit(f"register:{_client_ip(request)}:{body.email.lower().strip()}")
    # Check if email already exists
    existing = db.query(User).filter(User.email == body.email.lower().strip()).first()
    if existing:
        raise HTTPException(status_code=409, detail="该邮箱已注册")

    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="密码至少 6 位")

    user = register_user(db, body.email, body.password, body.name)
    token = create_token(user.id)

    _set_auth_cookie(response, request, token)

    return {
        "status": "ok",
        "user": _user_dict(user),
        "token": token,
    }


@router.post("/login")
async def login(body: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    """Login with email + password."""
    _check_rate_limit(f"login:{_client_ip(request)}:{body.email.lower().strip()}")
    user = authenticate_user(db, body.email, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="邮箱或密码错误")

    token = create_token(user.id)
    _set_auth_cookie(response, request, token)

    return {
        "status": "ok",
        "user": _user_dict(user),
        "token": token,
    }


@router.post("/logout")
async def logout(response: Response):
    """Clear auth cookie."""
    response.delete_cookie("token")
    return {"status": "ok"}


@router.get("/me")
async def get_me(request: Request, db: Session = Depends(get_db)):
    """Get current user profile + balance."""
    user = await get_current_user_optional(request)
    if not user:
        return {"authenticated": False}

    # Refresh from DB to get latest credits
    fresh_user = db.query(User).filter(User.id == user.id).first()
    if not fresh_user:
        return {"authenticated": False}

    return {
        "authenticated": True,
        "user": _user_dict(fresh_user),
    }


@router.get("/transactions")
async def my_transactions(request: Request, db: Session = Depends(get_db)):
    """Get current user's credit transactions."""
    user = await get_current_user(request)
    txns = get_transactions(db, user.id)
    return {"transactions": txns}


@router.get("/dashboard")
async def user_dashboard(request: Request, db: Session = Depends(get_db)):
    """Get user dashboard data: stats, recent checks, credit history."""
    user = await get_current_user(request)

    # Refresh user from DB
    fresh_user = db.query(User).filter(User.id == user.id).first()

    # Get transactions
    txns = get_transactions(db, user.id, limit=10)

    # Count total checks (consume type transactions)
    total_checks = db.query(Transaction).filter(
        Transaction.user_id == user.id,
        Transaction.type == "consume"
    ).count()

    return {
        "user": _user_dict(fresh_user),
        "stats": {
            "total_checks": total_checks,
            "credits_remaining": fresh_user.credits,
            "member_since": fresh_user.created_at,
        },
        "recent_transactions": txns,
    }


def _user_dict(user: User) -> dict:
    """Serialize user for API response (exclude password)."""
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "avatar_url": user.avatar_url,
        "credits": user.credits,
        "tier": user.tier,
        "created_at": user.created_at,
    }
