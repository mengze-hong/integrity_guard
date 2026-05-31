"""Payment system — Alipay/WeChat integration + sandbox mode.

In sandbox mode (no real credentials), payments auto-complete for testing.
In production, connects to Alipay SDK for real QR code payments.
"""

import uuid
import time
from datetime import datetime, timezone

from app.config import settings
from app.logging_config import logger

# Payment status tracking (in-memory, production should use DB)
_pending_orders: dict[str, dict] = {}


# === Pricing ===

PACKAGES = {
    "single": {"credits": 1, "price": 19.9, "name": "单次质检", "desc": "1 篇论文完整检查"},
    "starter": {"credits": 5, "price": 69, "name": "入门包", "desc": "适合投稿季集中使用"},
    "pro": {"credits": 20, "price": 199, "name": "专业包", "desc": "课题组/学期使用", "tier": "pro"},
    "lab": {"credits": 100, "price": 699, "name": "实验室包", "desc": "导师团队共享", "tier": "team"},
}


def create_order(user_id: str, package_id: str) -> dict:
    """Create a payment order. Returns order info with payment URL/QR."""
    package = PACKAGES.get(package_id)
    if not package:
        raise ValueError(f"Invalid package: {package_id}")

    order_id = f"IG{int(time.time())}{uuid.uuid4().hex[:6]}"
    order = {
        "order_id": order_id,
        "user_id": user_id,
        "package_id": package_id,
        "credits": package["credits"],
        "price": package["price"],
        "status": "pending",  # pending → paid → credited
        "created_at": datetime.now(timezone.utc).isoformat(),
        "paid_at": None,
    }
    _pending_orders[order_id] = order

    # In sandbox mode: auto-complete after creation
    if settings.payment_sandbox:
        order["status"] = "paid"
        order["paid_at"] = datetime.now(timezone.utc).isoformat()
        order["payment_url"] = None
        order["sandbox"] = True
        logger.info(f"[Sandbox] Order {order_id} auto-completed: {package['credits']} credits for user {user_id}")
    else:
        # Production: generate Alipay payment URL
        # TODO: Implement real Alipay SDK call here
        order["payment_url"] = f"https://openapi.alipay.com/gateway.do?order={order_id}"
        order["qr_content"] = f"alipay://pay?order={order_id}&amount={package['price']}"

    return order


def get_order(order_id: str) -> dict | None:
    """Get order by ID."""
    return _pending_orders.get(order_id)


def complete_order(order_id: str) -> dict | None:
    """Mark order as paid (called by payment callback or sandbox)."""
    order = _pending_orders.get(order_id)
    if not order:
        return None
    order["status"] = "paid"
    order["paid_at"] = datetime.now(timezone.utc).isoformat()
    return order


def verify_alipay_callback(params: dict) -> bool:
    """Verify Alipay callback signature.

    TODO: Implement real RSA2 signature verification with Alipay public key.
    """
    if settings.payment_sandbox:
        return True
    # Real implementation would verify sign using alipay public key
    return False
