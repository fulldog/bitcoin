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
