from decimal import Decimal

import httpx
import pytest

from app.copytrade.aoying import AoyingMonitor, build_copy_plan, normalize_position


def test_hidden_positions_are_not_inferred() -> None:
    assert normalize_position({"symbol": "btcusdt", "positionAmt": "-0.2", "entryPrice": "60000", "markPrice": "61000", "leverage": 10})["side"] == "SHORT"


def test_copy_plan_scales_to_budget_and_caps_leverage() -> None:
    positions = [
        normalize_position({"symbol": "BTCUSDT", "side": "LONG", "size": "1", "entryPrice": "100", "markPrice": "100"}),
        normalize_position({"symbol": "ETHUSDT", "side": "SHORT", "size": "1", "entryPrice": "100", "markPrice": "300"}),
    ]
    plan = build_copy_plan(positions, Decimal(100))
    assert [item["notional"] for item in plan] == [Decimal("25.00"), Decimal("75.00")]
    assert [item["side"] for item in plan] == ["BUY", "SELL"]
    assert {item["leverage"] for item in plan} == {1}


def test_copy_plan_rejects_empty_positions() -> None:
    with pytest.raises(ValueError, match="没有可跟"):
        build_copy_plan([], Decimal(100))


@pytest.mark.asyncio
async def test_snapshot_keeps_hidden_positions_empty() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/detail"):
            data = {"nickname": "熬鹰资本", "status": "ACTIVE", "positionShow": False, "aumAmount": "10", "description": "公开说明", "tagItemVos": []}
        elif request.url.path.endswith("/query-list"):
            data = {"list": [{"roi": "1", "pnl": "2", "mdd": "3", "winRate": "4"}]}
        elif request.url.path.endswith("/positions"):
            data = [{"symbol": "BTCUSDT", "side": "LONG", "size": "1", "entryPrice": "10", "markPrice": "11"}]
        else:
            data = {"list": [{"symbol": "BTCUSDT", "side": "Long", "leverage": "2", "avgCost": "10", "avgClosePrice": "11", "closingPnl": "1", "roi": "0.1", "opened": 1, "closed": 2, "isolated": "Cross"}]}
        return httpx.Response(200, json={"code": "000000", "data": data})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    snapshot = await AoyingMonitor(client).snapshot()
    await client.aclose()
    assert snapshot["positions_public"] is False
    assert snapshot["positions"] == []
    assert snapshot["history"][0]["symbol"] == "BTCUSDT"
