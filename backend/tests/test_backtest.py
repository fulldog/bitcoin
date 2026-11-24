from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.backtest.engine import BacktestEngine
from app.domain.filters import SymbolRules
from app.domain.models import Bar, RunManifest
from app.strategies.sma_cross import SmaCrossStrategy


def bars() -> list[Bar]:
    result = []
    for index in range(30):
        start = datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=index)
        price = Decimal(100) + Decimal(index)
        result.append(
            Bar(
                symbol="BTCUSDT",
                interval="1m",
                open_time=start,
                close_time=start + timedelta(minutes=1),
                open=price,
                high=price + 1,
                low=price - 1,
                close=price,
                volume=Decimal(1),
            )
        )
    return result


def manifest() -> RunManifest:
    return RunManifest(
        strategy_name="sma_cross",
        strategy_version="1",
        parameters={"fast": 3, "slow": 5},
        dataset_id="fixture",
        symbols=("BTCUSDT",),
        interval="1m",
        fee_rate=Decimal("0.001"),
        slippage_bps=Decimal(5),
    )


def test_backtest_is_reproducible():
    rules = SymbolRules(
        symbol="BTCUSDT",
        tick_size=Decimal("0.01"),
        step_size=Decimal("0.001"),
        min_qty=Decimal("0.001"),
        min_notional=Decimal(10),
    )
    engine = BacktestEngine(rules)
    first = engine.run(SmaCrossStrategy(3, 5), bars(), manifest(), Decimal(1000))
    second = engine.run(SmaCrossStrategy(3, 5), bars(), manifest(), Decimal(1000))
    assert first.fill_hash == second.fill_hash
    assert first.metrics.total_return == second.metrics.total_return
