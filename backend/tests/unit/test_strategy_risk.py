from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.domain.models import Bar, Side
from app.strategies.base import SmaCrossStrategy, StrategyContext


def closed_bar(index: int, close: str) -> Bar:
    opened = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=index)
    price = Decimal(close)
    return Bar("BTCUSDT", "1m", opened, opened + timedelta(minutes=1), price, price + 1, price - 1, price, Decimal(1))


def test_hundred_usdt_budget_keeps_a_reserve() -> None:
    strategy = SmaCrossStrategy(quote_amount=Decimal(100))
    assert strategy.buy_budget(Decimal(100)) == Decimal(90)


def test_small_cash_is_left_for_the_risk_check() -> None:
    strategy = SmaCrossStrategy(quote_amount=Decimal(100))
    assert strategy.buy_budget(Decimal(1)) == Decimal(100)


def test_stop_loss_sells_the_full_position() -> None:
    strategy = SmaCrossStrategy(cooldown_bars=0)
    history = [closed_bar(0, "100"), closed_bar(1, "100"), closed_bar(2, "100")]
    context = StrategyContext(history, Decimal("0.001"), Decimal(0), Decimal(100))
    intents = strategy.on_bar(context, closed_bar(2, "97"))
    assert intents[0].side is Side.SELL
    assert intents[0].quantity == Decimal("0.001")
    assert intents[0].client_order_id == "stop-loss"


def test_trailing_stop_locks_profit_after_the_offset() -> None:
    strategy = SmaCrossStrategy(cooldown_bars=0)
    first = StrategyContext([closed_bar(0, "102")], Decimal("0.001"), Decimal(0), Decimal(100))
    assert strategy.on_bar(first, first.history[-1]) == []
    second_bar = closed_bar(1, "101.4")
    second = StrategyContext([closed_bar(0, "102"), second_bar], Decimal("0.001"), Decimal(0), Decimal(100))
    intents = strategy.on_bar(second, second_bar)
    assert intents[0].client_order_id == "trailing-stop"


def test_roi_relaxes_after_the_trade_is_held() -> None:
    strategy = SmaCrossStrategy(cooldown_bars=0)
    strategy.minimal_roi = ((0, Decimal("0.03")), (3, Decimal(0)))
    bar = closed_bar(0, "100.2")
    assert strategy.on_bar(StrategyContext([bar], Decimal("0.001"), Decimal(0), Decimal(100)), bar) == []
    later = closed_bar(1, "100.2")
    assert strategy.on_bar(StrategyContext([bar, later], Decimal("0.001"), Decimal(0), Decimal(100)), later) == []
    aged = closed_bar(2, "100.2")
    intents = strategy.on_bar(StrategyContext([bar, later, aged], Decimal("0.001"), Decimal(0), Decimal(100)), aged)
    assert intents[0].client_order_id == "take-profit"


def test_repeated_stoploss_locks_new_entries() -> None:
    strategy = SmaCrossStrategy(cooldown_bars=0)
    strategy.stoploss_guard_limit = 2
    strategy.stoploss_guard_bars = 10
    losing = closed_bar(0, "97")
    context = StrategyContext([losing], Decimal("0.001"), Decimal(100), Decimal(100))
    strategy.on_bar(context, losing)
    strategy.on_bar(context, losing)
    assert strategy._entry_lock == 10


def test_take_profit_sells_before_a_new_signal() -> None:
    strategy = SmaCrossStrategy(cooldown_bars=0)
    history = [closed_bar(0, "100"), closed_bar(1, "100"), closed_bar(2, "104")]
    context = StrategyContext(history, Decimal("0.002"), Decimal(10), Decimal(100))
    intents = strategy.on_bar(context, history[-1])
    assert intents[0].client_order_id == "take-profit"
    assert intents[0].quantity == Decimal("0.002")
