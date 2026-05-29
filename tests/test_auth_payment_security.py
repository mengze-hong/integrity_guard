"""Security tests for auth throttling/cookies and payment idempotency."""

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import auth_routes, payment_routes
from app.database import Base
from app.models_db import PaymentOrder, Transaction, User


@pytest.fixture()
def temp_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    yield TestingSessionLocal


@pytest.fixture()
def auth_app(temp_db):
    auth_routes._login_attempts.clear()

    def override_get_db():
        db = temp_db()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.dependency_overrides[auth_routes.get_db] = override_get_db
    app.include_router(auth_routes.router)
    yield app
    auth_routes._login_attempts.clear()


@pytest.fixture()
def payment_app(temp_db, monkeypatch):
    monkeypatch.setattr(payment_routes, "SessionLocal", temp_db)
    monkeypatch.setattr(payment_routes, "verify_alipay_callback", lambda params: True)
    monkeypatch.setattr(payment_routes.settings, "admin_key", "admintest")
    monkeypatch.setattr(payment_routes.settings, "alipay_app_id", "app_123")
    payment_routes._admin_attempts.clear()

    db = temp_db()
    try:
        db.add(User(id="u1", email="user@example.com", password_hash="x", credits=0))
        db.add(PaymentOrder(
            id="ORDER1",
            user_id="u1",
            package_id="single",
            credits=1,
            price=19.9,
            status="pending",
            sandbox=False,
            created_at=datetime.now(timezone.utc).isoformat(),
        ))
        db.commit()
    finally:
        db.close()

    app = FastAPI()
    app.include_router(payment_routes.router)
    yield app
    payment_routes._admin_attempts.clear()


def test_login_rate_limit_blocks_repeated_failures(auth_app):
    client = TestClient(auth_app)
    payload = {"email": "nobody@example.com", "password": "bad"}

    for _ in range(10):
        assert client.post("/auth/login", json=payload).status_code == 401
    assert client.post("/auth/login", json=payload).status_code == 429


def test_auth_cookie_secure_behind_https(auth_app):
    client = TestClient(auth_app)
    response = client.post(
        "/auth/register",
        json={"email": "new@example.com", "password": "12345678"},
        headers={"x-forwarded-proto": "https"},
    )

    assert response.status_code == 200
    assert "secure" in response.headers["set-cookie"].lower()
    assert "httponly" in response.headers["set-cookie"].lower()


def test_admin_add_credits_requires_header_key(payment_app, temp_db):
    client = TestClient(payment_app)
    body_key = client.post(
        "/payment/admin/add-credits",
        json={"email": "user@example.com", "amount": 3, "admin_key": "admintest"},
    )
    assert body_key.status_code == 403

    header_key = client.post(
        "/payment/admin/add-credits",
        json={"email": "user@example.com", "amount": 3},
        headers={"x-admin-key": "admintest"},
    )
    assert header_key.status_code == 200
    assert header_key.json()["new_balance"] == 3


def test_alipay_callback_is_idempotent_and_validates_amount(payment_app, temp_db):
    client = TestClient(payment_app)
    callback = {
        "out_trade_no": "ORDER1",
        "trade_status": "TRADE_SUCCESS",
        "total_amount": "19.90",
        "app_id": "app_123",
    }

    assert client.post("/payment/callback/alipay", data=callback).status_code == 200
    assert client.post("/payment/callback/alipay", data=callback).status_code == 200

    db = temp_db()
    try:
        txns = db.query(Transaction).filter(Transaction.payment_id == "ORDER1").all()
        user = db.query(User).filter(User.id == "u1").first()
        assert len(txns) == 1
        assert user.credits == 1
    finally:
        db.close()

    bad_amount = {**callback, "out_trade_no": "ORDER1", "total_amount": "1.00"}
    assert client.post("/payment/callback/alipay", data=bad_amount).status_code == 400
