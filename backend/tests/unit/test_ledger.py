from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.data.binance import previous_utc_day
from app.services.platform import Platform
from app.store.db import TradingStore


def test_strategy_position_survives_a_new_platform() -> None:
    store = TradingStore("sqlite+pysqlite:///:memory:")
    first = Platform()
    first.attach_ledger("ada", store)
    created = first.create_strategy("趋势", "ETHUSDT", 2, 3, Decimal(90))
    runner = first.runners[created["id"]]
    runner.position_qty = Decimal("0.2")
    runner.entry_price = Decimal(100)
    first._persist_runner(runner)

    second = Platform()
    second.attach_ledger("ada", store)
    restored = second.runners[created["id"]]
    assert restored.position_qty == Decimal("0.2")
    assert restored.entry_price == Decimal(100)
    assert restored.status == "running"
    assert "ETHUSDT" in second.symbols
    assert second.strategy_runs()["running"] == 1


@pytest.mark.asyncio
async def test_exchange_shortfall_blocks_new_buys() -> None:
    platform = Platform()
    created = platform.create_strategy("持仓", "ETHUSDT", 2, 3, Decimal(90))
    platform.runners[created["id"]].position_qty = Decimal(1)

    class Broker:
        async def account(self) -> dict:
            return {"balances": [{"asset": "ETH", "free": "0.2", "locked": "0"}]}

    report = await platform.reconcile_balances(Broker())
    assert report["ok"] is False
    platform.live_unlocked = True
    platform.prices["ETHUSDT"] = Decimal(100)
    with pytest.raises(PermissionError, match="禁止开仓"):
        await platform.submit_live_order(Broker(), "ETHUSDT", "BUY", Decimal("0.01"))


def test_previous_utc_day_stops_before_today() -> None:
    start, end = previous_utc_day(datetime(2026, 11, 24, 15, tzinfo=timezone.utc))
    assert start == datetime(2026, 11, 23, tzinfo=timezone.utc)
    assert end == datetime(2026, 11, 24, tzinfo=timezone.utc)
