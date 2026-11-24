from decimal import Decimal

from app.domain.models import Bar, OrderIntent, Side


class StrategyContext:
    def __init__(self, history: list[Bar], position_qty: Decimal, cash: Decimal, entry_price: Decimal | None = None) -> None:
        self.history = list(history)
        self.position_qty = position_qty
        self.cash = cash
        self.entry_price = entry_price


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
    version = "2"

    def __init__(
        self,
        fast: int = 2,
        slow: int = 3,
        quote_amount: Decimal = Decimal(100),
        cash_fraction: Decimal = Decimal("0.9"),
        stop_loss: Decimal = Decimal("0.02"),
        take_profit: Decimal = Decimal("0.03"),
        cooldown_bars: int = 5,
    ) -> None:
        if fast >= slow:
            raise ValueError("fast window must be shorter than slow window")
        if not Decimal(0) < cash_fraction <= 1:
            raise ValueError("cash fraction must be between 0 and 1")
        self.fast = fast
        self.slow = slow
        self.quote_amount = quote_amount
        self.cash_fraction = cash_fraction
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.cooldown_bars = cooldown_bars
        self.trailing_offset = Decimal("0.015")
        self.trailing_distance = Decimal("0.005")
        self.minimal_roi = ((0, take_profit), (15, Decimal("0.015")), (30, Decimal(0)))
        self.stoploss_guard_limit = 2
        self.stoploss_guard_bars = 15
        self.warmup = slow
        self._previous_spread: Decimal | None = None
        self._cooldown = 0
        self._bars_held = 0
        self._peak: Decimal | None = None
        self._stoploss_hits = 0
        self._entry_lock = 0

    def initialize(self, context: StrategyContext) -> None:
        del context
        self._previous_spread = None
        self._cooldown = 0
        self._bars_held = 0
        self._peak = None
        self._stoploss_hits = 0
        self._entry_lock = 0

    def parameters(self) -> dict:
        return {
            "fast": self.fast,
            "slow": self.slow,
            "quote_amount": str(self.quote_amount),
            "cash_fraction": str(self.cash_fraction),
            "stop_loss": str(self.stop_loss),
            "take_profit": str(self.take_profit),
            "cooldown_bars": self.cooldown_bars,
            "trailing_offset": str(self.trailing_offset),
            "trailing_distance": str(self.trailing_distance),
            "minimal_roi": ",".join(f"{bars}:{ratio}" for bars, ratio in self.minimal_roi),
            "stoploss_guard_limit": self.stoploss_guard_limit,
        }

    def buy_budget(self, cash: Decimal) -> Decimal:
        if cash < self.quote_amount:
            return self.quote_amount
        budget = min(self.quote_amount, cash * self.cash_fraction)
        reserve = min(Decimal(1), cash * Decimal("0.1"))
        return min(budget, cash - reserve)

    def roi_target(self, bars_held: int) -> Decimal:
        target = self.minimal_roi[0][1]
        for after_bars, ratio in self.minimal_roi:
            if bars_held >= after_bars:
                target = ratio
        return target

    def exit_reason(self, context: StrategyContext, bar: Bar) -> str | None:
        entry = context.entry_price
        if context.position_qty <= 0 or entry is None or entry <= 0:
            self._bars_held = 0
            self._peak = None
            return None
        self._bars_held += 1
        self._peak = bar.close if self._peak is None else max(self._peak, bar.close)
        if bar.close <= entry * (Decimal(1) - self.stop_loss):
            self._stoploss_hits += 1
            if self._stoploss_hits >= self.stoploss_guard_limit:
                self._entry_lock = self.stoploss_guard_bars
            return "stop-loss"
        if self._peak >= entry * (Decimal(1) + self.trailing_offset) and bar.close <= self._peak * (Decimal(1) - self.trailing_distance):
            return "trailing-stop"
        if (bar.close - entry) / entry >= self.roi_target(self._bars_held):
            return "take-profit"
        return None

    def on_bar(self, context: StrategyContext, bar: Bar) -> list[OrderIntent]:
        if self._cooldown > 0:
            self._cooldown -= 1
        if self._entry_lock > 0:
            self._entry_lock -= 1
        exit_id = self.exit_reason(context, bar)
        closes = [
            item.close
            for item in context.history
            if item.symbol == bar.symbol and item.is_closed and item.open_time <= bar.open_time
        ]
        fast = sma(closes, self.fast)
        slow = sma(closes, self.slow)
        spread = None if fast is None or slow is None else fast - slow
        intents: list[OrderIntent] = []
        if exit_id:
            intents.append(OrderIntent(bar.symbol, Side.SELL, context.position_qty, client_order_id=exit_id))
        elif spread is not None and self._previous_spread is not None and self._cooldown == 0 and self._entry_lock == 0:
            crossed_up = self._previous_spread <= 0 and spread > 0 and context.position_qty == 0
            crossed_down = self._previous_spread >= 0 and spread < 0 and context.position_qty > 0
            if crossed_up:
                quantity = self.buy_budget(context.cash) / bar.close
                if quantity > 0:
                    intents.append(OrderIntent(bar.symbol, Side.BUY, quantity, client_order_id="sma-buy"))
            elif crossed_down:
                intents.append(OrderIntent(bar.symbol, Side.SELL, context.position_qty, client_order_id="sma-sell"))
        if spread is not None:
            self._previous_spread = spread
        if intents:
            self._cooldown = self.cooldown_bars
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
