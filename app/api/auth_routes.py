"""Authentication API routes: register, login, profile, OAuth."""

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


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str = None


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/register")
async def register(body: RegisterRequest, response: Response, db: Session = Depends(get_db)):
    """Register a new user with email + password."""
    # Check if email already exists
    existing = db.query(User).filter(User.email == body.email.lower().strip()).first()
    if existing:
        raise HTTPException(status_code=409, detail="该邮箱已注册")

    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="密码至少 6 位")

    user = register_user(db, body.email, body.password, body.name)
    token = create_token(user.id)

    # Set cookie
    response.set_cookie("token", token, httponly=True, max_age=7*86400, samesite="lax")

    return {
        "status": "ok",
        "user": _user_dict(user),
        "token": token,
    }


@router.post("/login")
async def login(body: LoginRequest, response: Response, db: Session = Depends(get_db)):
    """Login with email + password."""
    user = authenticate_user(db, body.email, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="邮箱或密码错误")

    token = create_token(user.id)
    response.set_cookie("token", token, httponly=True, max_age=7*86400, samesite="lax")

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
