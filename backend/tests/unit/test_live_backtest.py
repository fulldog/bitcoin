from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api import routes
from app.domain.models import Bar
from app.main import app
from app.security import create_token
from app.services.platform import Platform, contiguous_closed_bars


def minute_bar(index: int, close: str) -> Bar:
    opened = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=index)
    price = Decimal(close)
    return Bar("BTCUSDT", "1m", opened, opened + timedelta(minutes=1), price, price + 1, price - 1, price, Decimal(1))


def test_contiguous_closed_bars_stop_at_a_gap() -> None:
    bars = [minute_bar(0, "10"), minute_bar(1, "11"), minute_bar(3, "12"), minute_bar(4, "13")]
    assert [bar.open_time for bar in contiguous_closed_bars(bars)] == [bars[2].open_time, bars[3].open_time]


def test_missing_dataset_backtest_uses_live_bars() -> None:
    platform = Platform()
    platform.live_bars = [minute_bar(index, close) for index, close in enumerate(["10", "11", "12", "13", "14", "15"])]
    report = platform.run_backtest("btc")
    assert report["assumptions"]["market_fill"] == "next_bar_open"
    assert platform.datasets["btc"].quality.ready is True


def test_backtest_loads_public_klines_when_live_history_is_short(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch(self: object, symbol: str, interval: str, limit: int = 500, start_time: int | None = None) -> list[Bar]:
        del self, symbol, interval, limit, start_time
        return [minute_bar(index, str(10 + index)) for index in range(8)]

    monkeypatch.setattr(routes.BinanceMarketData, "fetch_klines", fake_fetch)
    client = TestClient(app)
    response = client.post(
        "/api/backtests?dataset_id=public-btc",
        headers={"Authorization": f"Bearer {create_token('xiongyk')}", "Idempotency-Key": "public-btc"},
    )
    assert response.status_code == 200
    assert response.json()["assumptions"]["market_fill"] == "next_bar_open"


def test_missing_dataset_without_enough_bars_is_rejected() -> None:
    platform = Platform()
    platform.live_bars = [minute_bar(0, "10"), minute_bar(1, "11")]
    with pytest.raises(ValueError, match="4"):
        platform.run_backtest("btc")
