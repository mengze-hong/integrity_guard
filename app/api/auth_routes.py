"""Authentication API routes: register, login, profile, OAuth."""

import hashlib
import os
import secrets
import time
from collections import defaultdict
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, Response, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import (
    register_user, authenticate_user, create_token,
    refresh_free_tier_monthly_credits,
)
from app.models_db import ApiToken, User
from app.dependencies import get_current_user, get_current_user_optional
from app.credits import get_transactions
from app.models_db import Transaction
from app import storage

router = APIRouter(prefix="/auth", tags=["auth"])

# --- Simple in-memory rate limiter for login/register brute-force protection ---
_login_attempts: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT_WINDOW = 300  # 5 minutes
_RATE_LIMIT_MAX = 10  # max attempts per window
API_TOKEN_PREFIX = "sl_api_"
API_TOKEN_ALLOWED_TIERS = {"pro", "team"}


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


class CreateApiTokenRequest(BaseModel):
    name: str = "Default API token"


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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_api_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _new_api_token() -> str:
    return f"{API_TOKEN_PREFIX}{secrets.token_urlsafe(32)}"


def _api_token_dict(token: ApiToken) -> dict:
    return {
        "id": token.id,
        "name": token.name,
        "token_prefix": token.token_prefix,
        "created_at": token.created_at,
        "revoked_at": token.revoked_at,
        "last_used_at": token.last_used_at,
    }


def _require_api_token_tier(user: User) -> None:
    if (user.tier or "free").lower() not in API_TOKEN_ALLOWED_TIERS:
        raise HTTPException(status_code=403, detail="API Token 仅 Pro/Team 用户可用")


def _build_team_dashboard(checks: list[dict]) -> dict:
    """Build a lightweight mentor dashboard from the user's recent checks."""
    total = len(checks)
    if total == 0:
        return {
            "available": True,
            "total_checks": 0,
            "avg_score": 0,
            "pass_rate": 0,
            "needs_attention": 0,
            "low_score_checks": [],
        }

    scores = [float(item.get("score") or 0) for item in checks]
    passed = sum(1 for item in checks if item.get("passed"))
    low_score_checks = sorted(
        [
            item for item in checks
            if not item.get("passed") or float(item.get("score") or 0) < 70
        ],
        key=lambda item: float(item.get("score") or 0),
    )[:5]
    return {
        "available": True,
        "total_checks": total,
        "avg_score": round(sum(scores) / total, 1),
        "pass_rate": round(passed / total * 100, 1),
        "needs_attention": len(low_score_checks),
        "low_score_checks": low_score_checks,
    }


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
    fresh_user = refresh_free_tier_monthly_credits(
        db,
        db.query(User).filter(User.id == user.id).first(),
    )
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


@router.get("/api-tokens")
async def list_api_tokens(request: Request, db: Session = Depends(get_db)):
    """List current user's API tokens without exposing secrets."""
    user = await get_current_user(request)
    fresh_user = db.query(User).filter(User.id == user.id).first()
    _require_api_token_tier(fresh_user)
    tokens = (
        db.query(ApiToken)
        .filter(ApiToken.user_id == user.id, ApiToken.revoked_at.is_(None))
        .order_by(ApiToken.created_at.desc())
        .all()
    )
    return {"tokens": [_api_token_dict(token) for token in tokens]}


@router.post("/api-tokens")
async def create_api_token(
    body: CreateApiTokenRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Create a Pro/Team API token. The plaintext token is returned once."""
    user = await get_current_user(request)
    fresh_user = db.query(User).filter(User.id == user.id).first()
    _require_api_token_tier(fresh_user)

    name = (body.name or "Default API token").strip()[:80] or "Default API token"
    plaintext = _new_api_token()
    token = ApiToken(
        user_id=user.id,
        name=name,
        token_hash=_hash_api_token(plaintext),
        token_prefix=plaintext[:14],
        created_at=_now(),
    )
    db.add(token)
    db.commit()
    db.refresh(token)
    payload = _api_token_dict(token)
    payload["token"] = plaintext
    return {"token": payload}


@router.delete("/api-tokens/{token_id}")
async def revoke_api_token(token_id: str, request: Request, db: Session = Depends(get_db)):
    """Revoke an API token owned by the current user."""
    user = await get_current_user(request)
    fresh_user = db.query(User).filter(User.id == user.id).first()
    _require_api_token_tier(fresh_user)
    token = (
        db.query(ApiToken)
        .filter(ApiToken.id == token_id, ApiToken.user_id == user.id)
        .first()
    )
    if not token:
        raise HTTPException(status_code=404, detail="API Token 不存在")
    if not token.revoked_at:
        token.revoked_at = _now()
        db.commit()
    return {"status": "ok"}


@router.get("/dashboard")
async def user_dashboard(request: Request, db: Session = Depends(get_db)):
    """Get user dashboard data: stats, recent checks, credit history."""
    user = await get_current_user(request)

    # Refresh user from DB
    fresh_user = refresh_free_tier_monthly_credits(
        db,
        db.query(User).filter(User.id == user.id).first(),
    )

    # Get transactions
    txns = get_transactions(db, user.id, limit=10)

    # Count total checks (consume type transactions)
    total_checks = db.query(Transaction).filter(
        Transaction.user_id == user.id,
        Transaction.type == "consume"
    ).count()
    recent_checks = storage.list_jobs(
        limit=8,
        owner_type="user",
        owner_id=str(user.id),
        include_legacy=False,
    )
    team_dashboard = None
    if (fresh_user.tier or "").lower() == "team":
        team_checks = storage.list_jobs(
            limit=50,
            owner_type="user",
            owner_id=str(user.id),
            include_legacy=False,
        )
        team_dashboard = _build_team_dashboard(team_checks)

    return {
        "user": _user_dict(fresh_user),
        "stats": {
            "total_checks": max(total_checks, len(recent_checks)),
            "credits_remaining": fresh_user.credits,
            "member_since": fresh_user.created_at,
        },
        "recent_transactions": txns,
        "recent_checks": recent_checks,
        "team_dashboard": team_dashboard,
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
