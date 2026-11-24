from datetime import datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.main import app
from app.observability import sanitize
from app.portfolio.accounting import Portfolio
from app.services.platform import RateLimiter, parse_kline
from app.store.db import TradingStore
from tests.unit.test_domain import bar

client = TestClient(app)


def test_store_write_is_idempotent_and_audit_is_append_only() -> None:
    store = TradingStore()
    assert store.save_bars([bar(0, "10"), bar(1, "11")]) == 2
    assert store.save_bars([bar(0, "10")]) == 0
    store.append_event(1, "fill", "{}")
    store.append_event(2, "fill", "{}")
    assert [item.sequence for item in store.events()] == [1, 2]


def test_portfolio_preserves_nonnegative_balances() -> None:
    portfolio = Portfolio(Decimal(100))
    from app.domain.models import Fill, Side

    portfolio.apply_fill(Fill("BTCUSDT", Side.BUY, Decimal(2), Decimal(10), Decimal(1), bar(0, "10").open_time, "a"))
    assert portfolio.cash == Decimal(79)
    assert portfolio.position("BTCUSDT") == Decimal(2)
    try:
        portfolio.apply_fill(Fill("BTCUSDT", Side.SELL, Decimal(3), Decimal(10), Decimal(0), bar(1, "10").open_time, "b"))
    except ValueError as exc:
        assert "insufficient position" in str(exc)
    else:
        raise AssertionError("oversell was accepted")


def test_recorded_kline_and_rate_limit() -> None:
    parsed = parse_kline({"k": {"s": "BTCUSDT", "i": "1m", "t": 1767225600000, "T": 1767225659999, "o": "10", "h": "11", "l": "9", "c": "10.5", "v": "3", "x": True}})
    assert parsed.is_closed
    limiter = RateLimiter(1, __import__("datetime").timedelta(seconds=10))
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert limiter.allow(now)
    assert not limiter.allow(now)


def test_logs_redact_secrets() -> None:
    assert sanitize({"binance_api_secret": "abc", "symbol": "BTCUSDT"})["binance_api_secret"] == "***"


def test_control_plane_runs_research_without_direct_orders() -> None:
    bars = [
        {
            "symbol": "BTCUSDT",
            "interval": "1h",
            "open_time": item.open_time.isoformat(),
            "close_time": item.close_time.isoformat(),
            "open": str(item.open),
            "high": str(item.high),
            "low": str(item.low),
            "close": str(item.close),
            "volume": str(item.volume),
            "is_closed": True,
        }
        for item in [bar(index, close) for index, close in enumerate(["10", "10", "10", "12", "14", "16", "13", "9"])]
    ]
    imported = client.post("/api/datasets", json={"dataset_id": "btc", "bars": bars}, headers={"Idempotency-Key": "import-1"})
    assert imported.status_code == 200
    assert imported.json()["ready"] is True
    report = client.post("/api/backtests?dataset_id=btc", headers={"Idempotency-Key": "backtest-1"})
    assert report.status_code == 200
    body = report.json()
    assert body["assumptions"]["market_fill"] == "next_bar_open"
    assert client.get(f"/api/backtests/{body['id']}").status_code == 200
    denied = client.post("/api/orders")
    assert denied.status_code == 403
    started = client.post("/api/commands", json={"type": "start_paper", "cash": "1000"}, headers={"Idempotency-Key": "start-1"})
    assert started.status_code == 200
    assert client.post("/api/runtime/process", headers={"Idempotency-Key": "process-1"}).json()["processed"] == 1
    summary = client.get("/api/dashboard/summary")
    assert summary.status_code == 200
    assert summary.json()["mode"] == "PAPER"
    locked = client.post("/api/live/unlock", json={"confirmation": "wrong"}, headers={"Idempotency-Key": "live-1"})
    assert locked.status_code == 403
