"""Payment API routes — create orders, check status, handle callbacks."""

import secrets
import time
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.config import settings
from app.database import SessionLocal
from app.dependencies import get_current_user
from app.credits import add_credits
from app.payment import (
    PACKAGES, create_order, get_order, complete_order, verify_alipay_callback
)
from app.models_db import User, Transaction, PaymentOrder
from app.logging_config import logger

router = APIRouter(prefix="/payment", tags=["payment"])

_admin_attempts: dict[str, list[float]] = defaultdict(list)
_ADMIN_RATE_LIMIT_WINDOW = 300
_ADMIN_RATE_LIMIT_MAX = 20
_TIER_RANK = {"free": 0, "pro": 1, "team": 2}


class CreateOrderRequest(BaseModel):
    package_id: str  # 'starter' | 'standard' | 'pro' | 'team'


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_admin_rate_limit(request: Request) -> None:
    key = _client_ip(request)
    now = time.time()
    _admin_attempts[key] = [t for t in _admin_attempts[key] if now - t < _ADMIN_RATE_LIMIT_WINDOW]
    if len(_admin_attempts[key]) >= _ADMIN_RATE_LIMIT_MAX:
        raise HTTPException(429, "请求过于频繁，请稍后再试")
    _admin_attempts[key].append(now)


def _admin_key_from_headers(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.headers.get("x-admin-key", "").strip()


def _persist_order(db, order: dict) -> None:
    db.merge(PaymentOrder(
        id=order["order_id"],
        user_id=order["user_id"],
        package_id=order["package_id"],
        credits=order["credits"],
        price=float(order["price"]),
        status=order["status"],
        sandbox=bool(order.get("sandbox", False)),
        payment_url=order.get("payment_url"),
        created_at=order["created_at"],
        paid_at=order.get("paid_at"),
        credited_at=_now() if order["status"] == "credited" else None,
    ))
    db.commit()


def _order_dict(order: PaymentOrder) -> dict:
    return {
        "order_id": order.id,
        "user_id": order.user_id,
        "package_id": order.package_id,
        "credits": order.credits,
        "price": order.price,
        "status": order.status,
        "payment_url": order.payment_url,
        "sandbox": order.sandbox,
    }


def _validate_callback_app(params: dict) -> None:
    app_id = params.get("app_id")
    if settings.alipay_app_id and app_id and not secrets.compare_digest(app_id, settings.alipay_app_id):
        logger.warning(f"Alipay app_id mismatch: {app_id}")
        raise HTTPException(400, "应用 ID 不匹配")


def _validate_callback_amount(order: PaymentOrder, params: dict) -> None:
    amount = params.get("total_amount") or params.get("buyer_pay_amount")
    if amount is None:
        return
    try:
        paid = float(amount)
    except (TypeError, ValueError):
        raise HTTPException(400, "支付金额格式错误")
    if abs(paid - float(order.price)) > 0.01:
        logger.warning(f"Payment amount mismatch: {order.id}, paid={paid}, expected={order.price}")
        raise HTTPException(400, "支付金额不匹配")


def _apply_package_tier(db, user_id: str, package_id: str) -> str | None:
    target_tier = PACKAGES.get(package_id, {}).get("tier")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return None
    if not target_tier:
        return user.tier

    current_rank = _TIER_RANK.get((user.tier or "free").lower(), 0)
    target_rank = _TIER_RANK.get(target_tier, 0)
    if target_rank > current_rank:
        user.tier = target_tier
        db.commit()
        db.refresh(user)
    return user.tier


def _credit_order_once(db, order: PaymentOrder) -> int:
    """Credit a paid order exactly once, even if callbacks are replayed."""
    existing = db.query(Transaction).filter(Transaction.payment_id == order.id).first()
    if existing:
        _apply_package_tier(db, order.user_id, order.package_id)
        order.status = "credited"
        order.credited_at = order.credited_at or _now()
        db.commit()
        user = db.query(User).filter(User.id == order.user_id).first()
        return user.credits if user else existing.balance_after

    new_balance = add_credits(
        db,
        order.user_id,
        order.credits,
        f"充值 {PACKAGES[order.package_id]['name']}",
        payment_id=order.id,
    )
    _apply_package_tier(db, order.user_id, order.package_id)
    order.status = "credited"
    order.credited_at = _now()
    db.commit()
    return new_balance


@router.get("/packages")
async def list_packages():
    """Return available credit packages."""
    return {"packages": [
        {"id": k, **v} for k, v in PACKAGES.items()
    ]}


@router.post("/create")
async def create_payment(body: CreateOrderRequest, request: Request):
    """Create a payment order for the logged-in user."""
    user = await get_current_user(request)

    if body.package_id not in PACKAGES:
        raise HTTPException(400, "无效的套餐")

    order = create_order(user.id, body.package_id)

    db = SessionLocal()
    try:
        _persist_order(db, order)
        db_order = db.query(PaymentOrder).filter(PaymentOrder.id == order["order_id"]).first()
        if order.get("sandbox"):
            order["new_balance"] = _credit_order_once(db, db_order)
            order["status"] = db_order.status
            credited_user = db.query(User).filter(User.id == user.id).first()
            order["new_tier"] = credited_user.tier if credited_user else user.tier
    finally:
        db.close()

    return {
        "order_id": order["order_id"],
        "status": order["status"],
        "credits": order["credits"],
        "price": order["price"],
        "payment_url": order.get("payment_url"),
        "new_balance": order.get("new_balance"),
        "new_tier": order.get("new_tier", user.tier),
        "sandbox": order.get("sandbox", False),
    }


@router.get("/status/{order_id}")
async def check_order_status(order_id: str, request: Request):
    """Check payment order status (for frontend polling)."""
    user = await get_current_user(request)
    db = SessionLocal()
    try:
        db_order = db.query(PaymentOrder).filter(PaymentOrder.id == order_id).first()
        order = _order_dict(db_order) if db_order else get_order(order_id)
    finally:
        db.close()
    if not order or order["user_id"] != user.id:
        raise HTTPException(404, "订单不存在")

    return {
        "order_id": order["order_id"],
        "status": order["status"],
        "credits": order["credits"],
        "price": order["price"],
        "tier": PACKAGES.get(order["package_id"], {}).get("tier", user.tier),
    }


@router.post("/callback/alipay")
async def alipay_callback(request: Request):
    """Handle Alipay async notification callback."""
    form_data = await request.form()
    params = dict(form_data)

    if not verify_alipay_callback(params):
        logger.warning(f"Alipay callback verification failed: {params.get('out_trade_no')}")
        raise HTTPException(400, "签名验证失败")

    order_id = params.get("out_trade_no")
    trade_status = params.get("trade_status")

    if trade_status in ("TRADE_SUCCESS", "TRADE_FINISHED"):
        db = SessionLocal()
        try:
            db_order = db.query(PaymentOrder).filter(PaymentOrder.id == order_id).first()
            if not db_order:
                order = complete_order(order_id)
                if not order:
                    logger.warning(f"Unknown payment callback order: {order_id}")
                    return "success"
                _persist_order(db, order)
                db_order = db.query(PaymentOrder).filter(PaymentOrder.id == order_id).first()

            _validate_callback_app(params)
            _validate_callback_amount(db_order, params)
            if db_order.status != "credited":
                db_order.status = "paid"
                db_order.paid_at = db_order.paid_at or _now()
                new_balance = _credit_order_once(db, db_order)
                logger.info(f"Payment completed: {order_id}, +{db_order.credits} credits, balance={new_balance}")
        finally:
            db.close()

    return "success"  # Alipay expects "success" string response


# === Admin endpoint (for manual crediting during MVP) ===

@router.post("/admin/add-credits")
async def admin_add_credits(request: Request):
    """Admin: manually add credits to a user (for testing/MVP)."""
    _check_admin_rate_limit(request)
    body = await request.json()
    user_email = body.get("email")
    amount = body.get("amount", 100)
    admin_key = _admin_key_from_headers(request)

    if not admin_key or not secrets.compare_digest(admin_key, settings.admin_key):
        raise HTTPException(403, "Unauthorized")

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == user_email).first()
        if not user:
            raise HTTPException(404, f"User {user_email} not found")
        new_balance = add_credits(db, user.id, amount, f"管理员充值 +{amount}")
        return {"email": user_email, "added": amount, "new_balance": new_balance}
    finally:
        db.close()
