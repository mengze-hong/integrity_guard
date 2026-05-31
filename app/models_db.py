"""SQLAlchemy ORM models for users, transactions, and jobs."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Integer, Float, Text, ForeignKey, Boolean
from sqlalchemy.orm import relationship

from app.database import Base


def _uuid():
    return str(uuid.uuid4())[:8]


def _now():
    return datetime.now(timezone.utc).isoformat()


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=_uuid)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=True)  # nullable for OAuth users
    name = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)
    oauth_provider = Column(String, nullable=True)  # 'google'|'github'
    oauth_id = Column(String, nullable=True)
    credits = Column(Integer, default=3)  # 注册送 3 次免费质检
    tier = Column(String, default="free")  # 'free'|'pro'|'team'
    created_at = Column(String, default=_now)
    last_login_at = Column(String, nullable=True)

    transactions = relationship("Transaction", back_populates="user")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    type = Column(String, nullable=False)  # 'purchase'|'consume'|'gift'|'refund'
    amount = Column(Integer, nullable=False)  # positive=credit, negative=debit
    balance_after = Column(Integer, nullable=False)
    description = Column(String, nullable=True)
    payment_id = Column(String, nullable=True)  # external payment order ID
    created_at = Column(String, default=_now)

    user = relationship("User", back_populates="transactions")


class PaymentOrder(Base):
    __tablename__ = "payment_orders"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    package_id = Column(String, nullable=False)
    credits = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)
    status = Column(String, default="pending", index=True)  # pending|paid|credited|failed
    sandbox = Column(Boolean, default=False)
    payment_url = Column(Text, nullable=True)
    created_at = Column(String, default=_now)
    paid_at = Column(String, nullable=True)
    credited_at = Column(String, nullable=True)

    user = relationship("User")


class ApiToken(Base):
    __tablename__ = "api_tokens"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    token_hash = Column(String, unique=True, nullable=False, index=True)
    token_prefix = Column(String, nullable=False)
    created_at = Column(String, default=_now)
    revoked_at = Column(String, nullable=True)
    last_used_at = Column(String, nullable=True)

    user = relationship("User")
