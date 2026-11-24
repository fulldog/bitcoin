from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import urlencode

import httpx

from app.domain.models import Order, OrderStatus


@dataclass(frozen=True, slots=True)
class BinanceOrder:
    symbol: str
    order_id: str
    client_order_id: str
    status: str
    executed_quantity: Decimal
    average_price: Decimal


class BinanceExecution:
    def __init__(self, base_url: str, api_key: str, api_secret: str, client: httpx.AsyncClient | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.api_secret = api_secret.encode()
        self.client = client

    def signature(self, params: dict[str, str | int]) -> str:
        query = urlencode(params)
        return hmac.new(self.api_secret, query.encode(), hashlib.sha256).hexdigest()

    async def query_order(self, symbol: str, client_order_id: str) -> BinanceOrder:
        params: dict[str, str | int] = {
            "symbol": symbol.upper(),
            "origClientOrderId": client_order_id,
            "timestamp": int(time.time() * 1000),
        }
        params["signature"] = self.signature(params)
        headers = {"X-MBX-APIKEY": self.api_key}
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=15)
        try:
            response = await client.get(f"{self.base_url}/api/v3/order", params=params, headers=headers)
            response.raise_for_status()
            payload = response.json()
            executed = Decimal(payload.get("executedQty", "0"))
            price = Decimal(payload.get("price", "0"))
            return BinanceOrder(
                symbol=payload["symbol"],
                order_id=str(payload["orderId"]),
                client_order_id=payload["clientOrderId"],
                status=payload["status"],
                executed_quantity=executed,
                average_price=price,
            )
        finally:
            if owns_client:
                await client.aclose()


def apply_exchange_status(order: Order, exchange_status: str) -> None:
    mapping = {
        "NEW": OrderStatus.ACKNOWLEDGED,
        "PARTIALLY_FILLED": OrderStatus.PARTIALLY_FILLED,
        "FILLED": OrderStatus.FILLED,
        "CANCELED": OrderStatus.CANCELED,
        "REJECTED": OrderStatus.REJECTED,
        "EXPIRED": OrderStatus.CANCELED,
    }
    target = mapping.get(exchange_status)
    if target is None:
        raise ValueError(f"unsupported Binance order status: {exchange_status}")
    if target != order.status:
        order.transition(target)
