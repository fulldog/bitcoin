from decimal import Decimal

from app.domain.models import Bar, OrderIntent, Side


class StrategyContext:
    def __init__(self, history: list[Bar], position_qty: Decimal, cash: Decimal) -> None:
        self.history = list(history)
        self.position_qty = position_qty
        self.cash = cash


class Strategy:
    name = "strategy"
    version = "1"
    warmup = 0

    def initialize(self, context: StrategyContext) -> None:
        return None

    def on_bar(self, context: StrategyContext, bar: Bar) -> list[OrderIntent]:
        raise NotImplementedError

    def parameters(self) -> dict:
        return {}


def sma(values: list[Decimal], length: int) -> Decimal | None:
    if len(values) < length or length <= 0:
        return None
    window = values[-length:]
    return sum(window, Decimal(0)) / Decimal(length)


class SmaCrossStrategy(Strategy):
    name = "sma_cross"
    version = "1"

    def __init__(self, fast: int = 2, slow: int = 3, quote_amount: Decimal = Decimal(100)) -> None:
        if fast >= slow:
            raise ValueError("fast window must be shorter than slow window")
        self.fast = fast
        self.slow = slow
        self.quote_amount = quote_amount
        self.warmup = slow
        self._previous_spread: Decimal | None = None

    def initialize(self, context: StrategyContext) -> None:
        self._previous_spread = None

    def parameters(self) -> dict:
        return {"fast": self.fast, "slow": self.slow, "quote_amount": str(self.quote_amount)}

    def on_bar(self, context: StrategyContext, bar: Bar) -> list[OrderIntent]:
        closes = [
            item.close
            for item in context.history
            if item.symbol == bar.symbol and item.is_closed and item.open_time <= bar.open_time
        ]
        fast = sma(closes, self.fast)
        slow = sma(closes, self.slow)
        if fast is None or slow is None:
            return []
        spread = fast - slow
        intents: list[OrderIntent] = []
        if self._previous_spread is not None:
            crossed_up = self._previous_spread <= 0 and spread > 0 and context.position_qty == 0
            crossed_down = self._previous_spread >= 0 and spread < 0 and context.position_qty > 0
            if crossed_up:
                intents.append(OrderIntent(bar.symbol, Side.BUY, self.quote_amount / bar.close))
            elif crossed_down:
                intents.append(OrderIntent(bar.symbol, Side.SELL, context.position_qty))
        self._previous_spread = spread
        return intents


class FuturePeakStrategy(Strategy):
    """Test double that changes behavior when future bars are visible."""

    name = "future_peak"
    version = "1"

    def on_bar(self, context: StrategyContext, bar: Bar) -> list[OrderIntent]:
        peak = max(item.close for item in context.history)
        if bar.close == peak and context.position_qty == 0:
            return [OrderIntent(bar.symbol, Side.BUY, Decimal(1))]
        return []
