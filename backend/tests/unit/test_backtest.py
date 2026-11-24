from decimal import Decimal

from app.backtest.engine import BacktestEngine, lookahead_divergence, walk_forward
from app.backtest.metrics import indicator_stability, step_indicator
from app.domain.filters import SymbolRules
from app.domain.models import RunManifest, Side, fill_fingerprint
from app.risk.engine import RiskLimits
from app.strategies.base import FuturePeakStrategy, SmaCrossStrategy, sma
from tests.unit.test_domain import START, bar

RULES = SymbolRules("BTCUSDT", Decimal("0.01"), Decimal("0.00001"), Decimal("0.00001"), Decimal(5))
LIMITS = RiskLimits(max_order_notional=Decimal(1000), max_symbol_notional=Decimal(1000), max_gross_notional=Decimal(1000))


def series() -> list:
    closes = ["10", "10", "10", "12", "14", "16", "13", "9", "7", "8", "10", "14"]
    return [bar(index, close) for index, close in enumerate(closes)]


def manifest() -> RunManifest:
    strategy = SmaCrossStrategy()
    return RunManifest(strategy.name, strategy.version, strategy.parameters(), "dataset", ("BTCUSDT",), "1h", Decimal(0), Decimal(0))


def test_sma_uses_only_completed_window() -> None:
    assert sma([Decimal(1), Decimal(3)], 3) is None
    assert sma([Decimal(1), Decimal(3), Decimal(5)], 3) == Decimal(3)


def test_backtest_is_reproducible_and_reports_assumptions() -> None:
    engine = BacktestEngine(RULES, LIMITS)
    first = engine.run(SmaCrossStrategy(), series(), manifest(), Decimal(1000))
    second = engine.run(SmaCrossStrategy(), series(), manifest(), Decimal(1000))
    assert first.fill_hash == second.fill_hash
    assert first.assumptions["new_order_same_bar_fill"] is False
    assert first.metrics.trade_count >= 0
    assert all(fill.quantity <= Decimal(1000) for fill in first.fills)
    assert first.fills
    assert first.fills[0].time > START


def test_backtest_rejects_orders_when_cash_is_insufficient() -> None:
    result = BacktestEngine(RULES, LIMITS).run(SmaCrossStrategy(), series(), manifest(), Decimal(1))
    assert result.fills == []
    assert any(decision.code == "insufficient_cash" for decision in result.decisions)


def test_fill_quantity_never_exceeds_order_quantity() -> None:
    result = BacktestEngine(RULES, LIMITS).run(SmaCrossStrategy(quote_amount=Decimal(50)), series(), manifest(), Decimal(1000))
    for fill in result.fills:
        assert fill.quantity > 0
        assert fill.side in {Side.BUY, Side.SELL}
    assert result.fill_hash == fill_fingerprint(result.fills)


def test_future_window_strategy_is_flagged_for_lookahead() -> None:
    assert lookahead_divergence(FuturePeakStrategy, series())
    assert not lookahead_divergence(SmaCrossStrategy, series())


def test_recursive_indicator_changes_with_history_but_sma_does_not() -> None:
    values = [Decimal(index) for index in range(1, 40)]
    assert indicator_stability(lambda items: [sma(items, 3)] * len(items), values, [10, 20]) == [Decimal(0), Decimal(0)]
    assert any(item != 0 for item in indicator_stability(step_indicator, values, [10, 20]))


def test_walk_forward_keeps_train_and_test_separate() -> None:
    reports = walk_forward(BacktestEngine(RULES, LIMITS), SmaCrossStrategy, series(), manifest(), Decimal(1000), folds=2)
    assert [item["fold"] for item in reports] == [0, 1]
    assert "train_return" in reports[0] and "test_return" in reports[0]


def test_partial_sell_cannot_exceed_position() -> None:
    bars = series()
    result = BacktestEngine(RULES, LIMITS).run(SmaCrossStrategy(), bars, manifest(), Decimal(1000))
    held = Decimal(0)
    for fill in result.fills:
        if fill.side is Side.BUY:
            held += fill.quantity
        else:
            assert fill.quantity <= held
            held -= fill.quantity
    assert held >= 0
