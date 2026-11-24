from __future__ import annotations

from decimal import ROUND_DOWN, Decimal
from uuid import uuid4

import httpx

from app.adapters.binance_execution import BinanceExecution


class BinanceFutures(BinanceExecution):
    def __init__(self, base_url: str, api_key: str, api_secret: str, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(base_url, api_key, api_secret, client)

    async def symbol_filter(self, symbol: str) -> Decimal:
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=15)
        try:
            response = await client.get(f"{self.base_url}/fapi/v1/exchangeInfo", params={"symbol": symbol.upper()})
            response.raise_for_status()
            info = response.json()["symbols"][0]
        finally:
            if owns_client:
                await client.aclose()
        step = Decimal("0.001")
        for item in info["filters"]:
            if item["filterType"] == "LOT_SIZE":
                step = Decimal(item["stepSize"])
        return step

    async def set_leverage(self, symbol: str, leverage: int) -> None:
        await self._signed("POST", "/fapi/v1/leverage", {"symbol": symbol.upper(), "leverage": leverage})

    async def market_order(self, symbol: str, side: str, quantity: Decimal) -> dict[str, str]:
        step = await self.symbol_filter(symbol)
        rounded = (quantity / step).to_integral_value(rounding=ROUND_DOWN) * step
        if rounded <= 0:
            return {"symbol": symbol, "side": side, "status": "SKIPPED", "reason": "金额低于最小下单数量"}
        client_order_id = f"ay{uuid4().hex[:20]}"
        payload = await self._signed(
            "POST",
            "/fapi/v1/order",
            {
                "symbol": symbol.upper(),
                "side": side.upper(),
                "type": "MARKET",
                "quantity": format(rounded, "f"),
                "newClientOrderId": client_order_id,
                "newOrderRespType": "RESULT",
            },
        )
        executed = Decimal(payload.get("executedQty", "0"))
        average = Decimal(payload.get("avgPrice") or "0")
        return {
            "symbol": payload.get("symbol", symbol),
            "side": side,
            "status": payload.get("status", "UNKNOWN"),
            "quantity": format(executed or rounded, "f"),
            "average_price": format(average, "f"),
            "order_id": str(payload.get("orderId", "")),
            "client_order_id": payload.get("clientOrderId", client_order_id),
        }
