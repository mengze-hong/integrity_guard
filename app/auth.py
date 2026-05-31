"""Authentication utilities: JWT, password hashing, user management."""

import uuid
from datetime import datetime, timezone, timedelta

import bcrypt
import jwt
from sqlalchemy.orm import Session

from app.models_db import User, Transaction
from app.config import settings

JWT_SECRET = settings.jwt_secret
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 7
FREE_TIER_STARTING_CREDITS = 3
FREE_TIER_MONTHLY_GIFT_PREFIX = "Free tier 月度赠送"


# === Password Hashing ===

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


# === JWT ===

def create_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRE_DAYS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


# === User Operations ===

def register_user(db: Session, email: str, password: str, name: str = None) -> User:
    """Create a new user with email + password."""
    user = User(
        id=uuid.uuid4().hex[:12],
        email=email.lower().strip(),
        password_hash=hash_password(password),
        name=name or email.split("@")[0],
        credits=FREE_TIER_STARTING_CREDITS,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    db.add(user)

    # Record welcome gift
    db.add(Transaction(
        id=uuid.uuid4().hex[:12],
        user_id=user.id,
        type="gift",
        amount=FREE_TIER_STARTING_CREDITS,
        balance_after=FREE_TIER_STARTING_CREDITS,
        description=f"注册赠送 {FREE_TIER_STARTING_CREDITS} 次免费质检",
        created_at=datetime.now(timezone.utc).isoformat(),
    ))
    db.commit()
    db.refresh(user)
    return user


def _current_month_key(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return now.astimezone(timezone.utc).strftime("%Y-%m")


def refresh_free_tier_monthly_credits(
    db: Session, user: User | None, now: datetime | None = None
) -> User | None:
    """Top up free users to the monthly free-check balance once per month."""
    if not user or user.tier != "free":
        return user

    month_key = _current_month_key(now)
    if str(user.created_at or "").startswith(month_key):
        return user

    description = f"{FREE_TIER_MONTHLY_GIFT_PREFIX} {month_key}"
    existing = db.query(Transaction).filter(
        Transaction.user_id == user.id,
        Transaction.type == "gift",
        Transaction.description == description,
    ).first()
    if existing:
        return user

    current_credits = int(user.credits or 0)
    top_up = max(0, FREE_TIER_STARTING_CREDITS - current_credits)
    if top_up <= 0:
        return user

    user.credits = current_credits + top_up
    db.add(Transaction(
        id=uuid.uuid4().hex[:12],
        user_id=user.id,
        type="gift",
        amount=top_up,
        balance_after=user.credits,
        description=description,
        created_at=(now or datetime.now(timezone.utc)).isoformat(),
    ))
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    """Verify email + password, return user or None."""
    user = db.query(User).filter(User.email == email.lower().strip()).first()
    if not user or not user.password_hash:
        return None
    if not verify_password(password, user.password_hash):
        return None
    # Update last login
    user.last_login_at = datetime.now(timezone.utc).isoformat()
    db.commit()
    return refresh_free_tier_monthly_credits(db, user)


def get_or_create_oauth_user(
    db: Session, provider: str, oauth_id: str, email: str, name: str = None, avatar: str = None
) -> User:
    """Find or create a user from OAuth login."""
    # Try to find by oauth_id first
    user = db.query(User).filter(
        User.oauth_provider == provider, User.oauth_id == oauth_id
    ).first()
    if user:
        user.last_login_at = datetime.now(timezone.utc).isoformat()
        db.commit()
        return refresh_free_tier_monthly_credits(db, user)

    # Try to find by email (link accounts)
    user = db.query(User).filter(User.email == email.lower()).first()
    if user:
        user.oauth_provider = provider
        user.oauth_id = oauth_id
        if avatar:
            user.avatar_url = avatar
        user.last_login_at = datetime.now(timezone.utc).isoformat()
        db.commit()
        return refresh_free_tier_monthly_credits(db, user)

    # Create new user
    user = User(
        id=uuid.uuid4().hex[:12],
        email=email.lower(),
        name=name or email.split("@")[0],
        avatar_url=avatar,
        oauth_provider=provider,
        oauth_id=oauth_id,
        credits=FREE_TIER_STARTING_CREDITS,
        created_at=datetime.now(timezone.utc).isoformat(),
        last_login_at=datetime.now(timezone.utc).isoformat(),
    )
    db.add(user)
    db.add(Transaction(
        id=uuid.uuid4().hex[:12],
        user_id=user.id,
        type="gift",
        amount=FREE_TIER_STARTING_CREDITS,
        balance_after=FREE_TIER_STARTING_CREDITS,
        description=f"注册赠送 {FREE_TIER_STARTING_CREDITS} 次免费质检",
        created_at=datetime.now(timezone.utc).isoformat(),
    ))
    db.commit()
    db.refresh(user)
    return user
