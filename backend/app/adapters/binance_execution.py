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

    async def _signed(self, method: str, path: str, params: dict[str, str | int]) -> dict:
        payload = dict(params)
        payload["timestamp"] = int(time.time() * 1000)
        payload["recvWindow"] = 5000
        payload["signature"] = self.signature(payload)
        headers = {"X-MBX-APIKEY": self.api_key}
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=15)
        try:
            response = await client.request(method, f"{self.base_url}{path}", params=payload, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException as exc:
            raise TimeoutError("Binance request timed out") from exc
        finally:
            if owns_client:
                await client.aclose()

    async def account(self) -> dict:
        payload = await self._signed("GET", "/api/v3/account", {})
        balances = [
            {"asset": item["asset"], "free": item["free"], "locked": item["locked"]}
            for item in payload.get("balances", [])
            if Decimal(item["free"]) > 0 or Decimal(item["locked"]) > 0
        ]
        return {"can_trade": payload.get("canTrade", False), "balances": balances}

    async def place_order(self, symbol: str, side: str, quantity: Decimal, client_order_id: str) -> BinanceOrder:
        payload = await self._signed(
            "POST",
            "/api/v3/order",
            {
                "symbol": symbol.upper(),
                "side": side.upper(),
                "type": "MARKET",
                "quantity": format(quantity, "f"),
                "newClientOrderId": client_order_id,
                "newOrderRespType": "FULL",
            },
        )
        return self._order(payload)

    async def cancel_order(self, symbol: str, client_order_id: str) -> BinanceOrder:
        payload = await self._signed(
            "DELETE",
            "/api/v3/order",
            {"symbol": symbol.upper(), "origClientOrderId": client_order_id},
        )
        return self._order(payload)

    async def query_order(self, symbol: str, client_order_id: str) -> BinanceOrder:
        payload = await self._signed(
            "GET",
            "/api/v3/order",
            {"symbol": symbol.upper(), "origClientOrderId": client_order_id},
        )
        return self._order(payload)

    async def open_orders(self, symbol: str) -> list[BinanceOrder]:
        payload = await self._signed("GET", "/api/v3/openOrders", {"symbol": symbol.upper()})
        return [self._order(item) for item in payload]

    def _order(self, payload: dict) -> BinanceOrder:
        executed = Decimal(payload.get("executedQty", "0"))
        quote = Decimal(payload.get("cummulativeQuoteQty", "0"))
        average = quote / executed if executed else Decimal(payload.get("price", "0"))
        return BinanceOrder(
            symbol=payload["symbol"],
            order_id=str(payload["orderId"]),
            client_order_id=payload["clientOrderId"],
            status=payload["status"],
            executed_quantity=executed,
            average_price=average,
        )


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
