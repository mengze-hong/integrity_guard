"""Credits management: check, deduct, add."""

from datetime import datetime, timezone
import uuid

from sqlalchemy.orm import Session

from app.models_db import User, Transaction

UNLIMITED_CHECK_TIERS = {"pro", "team"}


class InsufficientCredits(Exception):
    """Raised when user doesn't have enough credits."""
    pass


def has_unlimited_checks(user: User | None) -> bool:
    """Return whether a user tier includes unlimited full checks."""
    return bool(user and (user.tier or "").lower() in UNLIMITED_CHECK_TIERS)


def check_credits(db: Session, user_id: str, required: int) -> bool:
    """Check if user has enough credits."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return False
    return user.credits >= required


def deduct_credits(db: Session, user_id: str, amount: int, description: str) -> int:
    """Deduct credits from user. Returns new balance. Raises InsufficientCredits."""
    user = db.query(User).filter(User.id == user_id).with_for_update().first()
    if not user:
        raise InsufficientCredits()
    if user.credits < amount:
        raise InsufficientCredits()

    user.credits -= amount
    db.add(Transaction(
        id=str(uuid.uuid4().hex[:12]),
        user_id=user_id,
        type="consume",
        amount=-amount,
        balance_after=user.credits,
        description=description,
        created_at=datetime.now(timezone.utc).isoformat(),
    ))
    db.commit()
    return user.credits


def deduct_check_credit(db: Session, user_id: str, amount: int, description: str) -> int:
    """Deduct a full-check credit unless the user's tier includes unlimited checks."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise InsufficientCredits()
    if has_unlimited_checks(user):
        return int(user.credits or 0)
    return deduct_credits(db, user_id, amount, description)


def add_credits(db: Session, user_id: str, amount: int, description: str, payment_id: str = None) -> int:
    """Add credits to user. Returns new balance."""
    user = db.query(User).filter(User.id == user_id).with_for_update().first()
    if not user:
        raise ValueError(f"User {user_id} not found")

    user.credits += amount
    db.add(Transaction(
        id=str(uuid.uuid4().hex[:12]),
        user_id=user_id,
        type="purchase",
        amount=amount,
        balance_after=user.credits,
        description=description,
        payment_id=payment_id,
        created_at=datetime.now(timezone.utc).isoformat(),
    ))
    db.commit()
    return user.credits


def get_balance(db: Session, user_id: str) -> int:
    """Get current credit balance."""
    user = db.query(User).filter(User.id == user_id).first()
    return user.credits if user else 0


def get_transactions(db: Session, user_id: str, limit: int = 20) -> list[dict]:
    """Get recent transactions for a user."""
    txns = (
        db.query(Transaction)
        .filter(Transaction.user_id == user_id)
        .order_by(Transaction.created_at.desc())
        .limit(limit)
        .all()
    )
    return [{
        "id": t.id,
        "type": t.type,
        "amount": t.amount,
        "balance_after": t.balance_after,
        "description": t.description,
        "created_at": t.created_at,
    } for t in txns]
