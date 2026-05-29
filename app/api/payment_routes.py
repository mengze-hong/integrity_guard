"""Payment API routes — create orders, check status, handle callbacks."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.dependencies import get_current_user
from app.credits import add_credits, get_balance
from app.payment import (
    PACKAGES, create_order, get_order, complete_order, verify_alipay_callback
)
from app.models_db import User
from app.logging_config import logger

router = APIRouter(prefix="/payment", tags=["payment"])


class CreateOrderRequest(BaseModel):
    package_id: str  # 'starter' | 'standard' | 'pro' | 'team'


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

    # If sandbox mode, immediately credit the user
    if order.get("sandbox"):
        db = SessionLocal()
        try:
            new_balance = add_credits(
                db, user.id, order["credits"],
                f"充值 {PACKAGES[body.package_id]['name']}",
                payment_id=order["order_id"],
            )
            order["new_balance"] = new_balance
            order["status"] = "credited"
        finally:
            db.close()

    return {
        "order_id": order["order_id"],
        "status": order["status"],
        "credits": order["credits"],
        "price": order["price"],
        "payment_url": order.get("payment_url"),
        "new_balance": order.get("new_balance"),
        "sandbox": order.get("sandbox", False),
    }


@router.get("/status/{order_id}")
async def check_order_status(order_id: str, request: Request):
    """Check payment order status (for frontend polling)."""
    user = await get_current_user(request)
    order = get_order(order_id)
    if not order or order["user_id"] != user.id:
        raise HTTPException(404, "订单不存在")

    return {
        "order_id": order["order_id"],
        "status": order["status"],
        "credits": order["credits"],
        "price": order["price"],
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
        order = complete_order(order_id)
        if order and order["status"] == "paid":
            db = SessionLocal()
            try:
                add_credits(
                    db, order["user_id"], order["credits"],
                    f"充值 {PACKAGES[order['package_id']]['name']}",
                    payment_id=order_id,
                )
                order["status"] = "credited"
                logger.info(f"Payment completed: {order_id}, +{order['credits']} credits")
            finally:
                db.close()

    return "success"  # Alipay expects "success" string response


# === Admin endpoint (for manual crediting during MVP) ===

@router.post("/admin/add-credits")
async def admin_add_credits(request: Request):
    """Admin: manually add credits to a user (for testing/MVP)."""
    body = await request.json()
    user_email = body.get("email")
    amount = body.get("amount", 100)
    admin_key = body.get("admin_key")

    # Simple admin auth (loaded from environment)
    from app.config import settings
    if admin_key != settings.admin_key:
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
