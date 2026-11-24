from decimal import Decimal

import httpx
import pytest

from app.adapters.binance_execution import BinanceExecution
from app.services.platform import Platform


def response_for(request: httpx.Request) -> httpx.Response:
    assert request.headers["X-MBX-APIKEY"] == "key"
    assert b"signature=" in request.url.query
    if request.url.path == "/api/v3/account":
        return httpx.Response(200, json={"canTrade": True, "balances": [{"asset": "USDT", "free": "25", "locked": "0"}, {"asset": "BTC", "free": "0", "locked": "0"}]})
    return httpx.Response(200, json={"symbol": "BTCUSDT", "orderId": 10, "clientOrderId": "live-1", "status": "FILLED", "executedQty": "0.001", "cummulativeQuoteQty": "100", "price": "0"})


@pytest.mark.asyncio
async def test_signed_account_request_uses_binance_spot_api():
    client = httpx.AsyncClient(transport=httpx.MockTransport(response_for), base_url="https://api.binance.com")
    broker = BinanceExecution("https://api.binance.com", "key", "secret", client)
    account = await broker.account()
    assert account["can_trade"] is True
    assert account["balances"] == [{"asset": "USDT", "free": "25", "locked": "0"}]


@pytest.mark.asyncio
async def test_live_order_reaches_binance_only_after_unlock():
    platform = Platform()
    platform.last_price = Decimal(100000)
    client = httpx.AsyncClient(transport=httpx.MockTransport(response_for), base_url="https://api.binance.com")
    broker = BinanceExecution("https://api.binance.com", "key", "secret", client)
    with pytest.raises(PermissionError):
        await platform.submit_live_order(broker, "BTCUSDT", "BUY", Decimal("0.001"))
    platform.live_unlocked = True
    report = await platform.submit_live_order(broker, "BTCUSDT", "BUY", Decimal("0.001"))
    assert report["status"] == "FILLED"
    assert report["average_price"] == "100000"
    await client.aclose()
