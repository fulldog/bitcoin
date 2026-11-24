from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.data.clock import FixedClock
from app.data.quality import deduplicate_bars, validate_bars
from app.domain.models import Bar


def make_bar(index: int) -> Bar:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=index)
    return Bar(
        symbol="BTCUSDT",
        interval="1m",
        open_time=start,
        close_time=start + timedelta(minutes=1),
        open=Decimal(100),
        high=Decimal(101),
        low=Decimal(99),
        close=Decimal(100),
        volume=Decimal(1),
    )


def test_fixed_clock_is_deterministic():
    clock = FixedClock(datetime(2025, 1, 1, tzinfo=timezone.utc))
    assert clock.now().isoformat() == "2025-01-01T00:00:00+00:00"
    clock.advance(60)
    assert clock.now().minute == 1


def test_quality_rejects_a_gap():
    assert validate_bars([make_bar(0), make_bar(2)], 60).accepted is False


def test_quality_deduplicates_by_open_time():
    bars = [make_bar(1), make_bar(0), make_bar(1)]
    result = deduplicate_bars(bars)
    assert [bar.open_time for bar in result] == [make_bar(0).open_time, make_bar(1).open_time]
