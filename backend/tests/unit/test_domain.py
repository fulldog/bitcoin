from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.domain.filters import parse_symbol_rules, round_down
from app.domain.models import Bar, Order, OrderStatus, RunManifest, Side
from app.market.quality import Dataset, MarketCursor, backoff_seconds, inspect_bars

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def bar(index: int, close: str, interval: str = "1h", closed: bool = True, symbol: str = "BTCUSDT") -> Bar:
    open_time = START + timedelta(hours=index)
    price = Decimal(close)
    return Bar(symbol, interval, open_time, open_time + timedelta(hours=1), price, price + 1, price - 1, price, Decimal(10), closed)


def test_order_timeout_can_only_move_to_known_venue_states() -> None:
    order = Order("BTCUSDT", Side.BUY, Decimal(1), "cid")
    order.transition(OrderStatus.VALIDATED)
    order.transition(OrderStatus.SUBMITTING)
    order.transition(OrderStatus.UNKNOWN, "timeout")
    order.transition(OrderStatus.ACKNOWLEDGED, "queried")


def test_terminal_order_cannot_be_resubmitted() -> None:
    order = Order("BTCUSDT", Side.SELL, Decimal(1), "cid")
    order.transition(OrderStatus.REJECTED, "risk")
    try:
        order.transition(OrderStatus.SUBMITTING)
    except ValueError as exc:
        assert "invalid order transition" in str(exc)
    else:
        raise AssertionError("terminal order was resubmitted")


def test_manifest_fingerprint_is_stable() -> None:
    manifest = RunManifest("sma_cross", "1", {"fast": 2}, "data", ("BTCUSDT",), "1h", Decimal("0.001"), Decimal(1))
    assert manifest.fingerprint() == manifest.fingerprint()
    changed = RunManifest("sma_cross", "1", {"fast": 3}, "data", ("BTCUSDT",), "1h", Decimal("0.001"), Decimal(1))
    assert manifest.fingerprint() != changed.fingerprint()


def test_exchange_filters_round_down_and_reject_min_notional() -> None:
    rules = parse_symbol_rules(
        {
            "symbol": "BTCUSDT",
            "filters": [
                {"filterType": "PRICE_FILTER", "tickSize": "0.01000000"},
                {"filterType": "LOT_SIZE", "minQty": "0.00100000", "stepSize": "0.00100000"},
                {"filterType": "MARKET_LOT_SIZE", "minQty": "0.00100000", "stepSize": "0.00100000"},
                {"filterType": "NOTIONAL", "minNotional": "10.00000000"},
            ],
        }
    )
    assert round_down(Decimal("1.239"), Decimal("0.01")) == Decimal("1.23")
    quantity, reason = rules.normalize(Decimal("0.0019"), Decimal(100), market=True)
    assert quantity == Decimal("0.001")
    assert reason == "MIN_NOTIONAL"


def test_bar_inspection_detects_duplicates_gaps_and_unclosed_bars() -> None:
    bars = [bar(0, "10"), bar(0, "10"), bar(2, "11"), bar(3, "12", closed=False)]
    report = inspect_bars(bars)
    assert not report.ready
    assert report.duplicates == 1
    assert report.gaps == 1
    assert report.unclosed == 1


def test_dataset_digest_is_independent_of_input_order() -> None:
    left = Dataset.freeze("btc", [bar(1, "11"), bar(0, "10")])
    right = Dataset.freeze("btc", [bar(0, "10"), bar(1, "11")])
    assert left.digest == right.digest
    assert not left.quality.ready
    assert Dataset.freeze("btc", [bar(0, "10"), bar(1, "11")]).quality.ready


def test_market_cursor_stays_unready_until_gap_is_resolved() -> None:
    cursor = MarketCursor()
    cursor.observe(bar(0, "10"))
    cursor.disconnect()
    assert cursor.reconnects == 1
    cursor.observe(bar(2, "12"))
    assert not cursor.ready
    assert "gap" in cursor.issues
    assert backoff_seconds(3) == 8
