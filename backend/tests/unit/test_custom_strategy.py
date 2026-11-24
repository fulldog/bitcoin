from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.domain.models import Bar
from app.services.platform import Platform


def minute_bar(index: int, close: str, symbol: str = "ETHUSDT") -> Bar:
    opened = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=index)
    price = Decimal(close)
    return Bar(symbol, "1m", opened, opened + timedelta(minutes=1), price, price + 1, price - 1, price, Decimal(1))


def test_custom_symbol_is_rejected_when_malformed() -> None:
    platform = Platform()
    with pytest.raises(ValueError, match="币种"):
        platform.add_symbol("btc")


def test_created_strategy_starts_and_receives_its_symbol() -> None:
    platform = Platform()
    created = platform.create_strategy("以太趋势", "ETHUSDT", 2, 3, Decimal(90))
    assert created["status"] == "running"
    assert "ETHUSDT" in platform.symbols
    platform.ingest_live_bar(minute_bar(0, "100"))
    runner = next(iter(platform.runners.values()))
    assert len(runner.history) == 1
    assert platform.klines("ETHUSDT")[0]["close"] == "100"
    assert platform.strategy_runs()["running"] == 1


class Broker:
    def __init__(self, quantity: Decimal) -> None:
        self.calls: list[tuple[str, str, Decimal]] = []
        self.quantity = quantity

    async def account(self) -> dict:
        return {"balances": [{"asset": "USDT", "free": "1000", "locked": "0"}, {"asset": "ETH", "free": "1", "locked": "0"}]}

    async def place_order(self, symbol: str, side: str, quantity: Decimal, client_order_id: str):
        self.calls.append((symbol, side, quantity))
        return type(
            "Report",
            (),
            {
                "symbol": symbol,
                "order_id": "1",
                "client_order_id": client_order_id,
                "status": "FILLED",
                "executed_quantity": self.quantity,
                "average_price": Decimal(100),
            },
        )()


@pytest.mark.asyncio
async def test_stop_without_position_does_not_sell() -> None:
    platform = Platform()
    created = platform.create_strategy("空仓", "ETHUSDT", 2, 3, Decimal(90))
    broker = Broker(Decimal(0))
    result = await platform.stop_strategy(broker, created["id"])
    assert result["order"] is None
    assert broker.calls == []
    assert platform.runners[created["id"]].status == "stopped"
    platform.ingest_live_bar(minute_bar(0, "100"))
    assert platform.runners[created["id"]].history == []
    assert platform.strategy_runs()["running"] == 0


@pytest.mark.asyncio
async def test_stop_market_sells_the_strategy_position() -> None:
    platform = Platform()
    platform.ensure_live()
    platform.live_unlocked = True
    created = platform.create_strategy("持仓", "ETHUSDT", 2, 3, Decimal(90))
    runner = platform.runners[created["id"]]
    runner.position_qty = Decimal("0.5")
    platform.prices["ETHUSDT"] = Decimal(100)
    broker = Broker(Decimal("0.5"))
    result = await platform.stop_strategy(broker, created["id"])
    assert broker.calls == [("ETHUSDT", "SELL", Decimal("0.5"))]
    assert runner.position_qty == 0
    assert runner.status == "stopped"
    assert result["strategy"]["last_decision"] == "已关闭并卖出"


@pytest.mark.asyncio
async def test_locked_stop_keeps_the_strategy_running() -> None:
    platform = Platform()
    created = platform.create_strategy("锁定", "ETHUSDT", 2, 3, Decimal(90))
    platform.runners[created["id"]].position_qty = Decimal("0.5")
    platform.prices["ETHUSDT"] = Decimal(100)
    with pytest.raises(PermissionError):
        await platform.stop_strategy(Broker(Decimal("0.5")), created["id"])
    assert platform.runners[created["id"]].status == "running"


def test_stopped_strategy_can_start_again() -> None:
    platform = Platform()
    created = platform.create_strategy("重启", "ETHUSDT", 2, 3, Decimal(90))
    platform.runners[created["id"]].status = "stopped"
    started = platform.start_strategy(created["id"])
    assert started["status"] == "running"
    platform.ingest_live_bar(minute_bar(0, "100"))
    assert len(platform.runners[created["id"]].history) == 1
