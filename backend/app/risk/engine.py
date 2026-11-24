from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from app.domain.filters import SymbolRules
from app.domain.models import OrderIntent, RiskDecision, Side
from app.portfolio.accounting import Portfolio


@dataclass
class RiskLimits:
    max_order_notional: Decimal = Decimal(100)
    max_symbol_notional: Decimal = Decimal(250)
    max_gross_notional: Decimal = Decimal(500)
    max_daily_loss: Decimal = Decimal(25)
    max_drawdown: Decimal = Decimal("0.2")
    max_orders_per_minute: int = 5
    market_data_max_age: timedelta = timedelta(seconds=120)
    cooldown: timedelta = timedelta(0)


@dataclass
class RiskState:
    kill_switch: bool = False
    connector_ready: bool = False
    reconciled: bool = False
    data_gap: bool = False
    halted_symbols: set[str] = field(default_factory=set)
    symbol_losses: dict[str, int] = field(default_factory=dict)
    order_times: list[datetime] = field(default_factory=list)
    last_order_at: datetime | None = None
    day_start_equity: Decimal = Decimal(0)
    peak_equity: Decimal = Decimal(0)


class RiskEngine:
    def __init__(self, limits: RiskLimits) -> None:
        self.limits = limits

    def evaluate(
        self,
        intent: OrderIntent,
        portfolio: Portfolio,
        rules: SymbolRules,
        state: RiskState,
        now: datetime,
        market_time: datetime,
        price: Decimal,
        equity: Decimal,
    ) -> RiskDecision:
        checks = (
            self._system,
            self._freshness,
            self._connector,
            self._rate,
            self._rules,
            self._balance,
            self._order_limit,
            self._symbol_limit,
            self._gross_limit,
            self._loss,
            self._cooldown,
        )
        context = {
            "intent": intent,
            "portfolio": portfolio,
            "rules": rules,
            "state": state,
            "now": now,
            "market_time": market_time,
            "price": price,
            "equity": equity,
        }
        for check in checks:
            decision = check(context)
            if decision is not None:
                return decision
        return RiskDecision(True, "accepted", "accepted", intent.client_order_id)

    def _system(self, ctx: dict) -> RiskDecision | None:
        state: RiskState = ctx["state"]
        intent: OrderIntent = ctx["intent"]
        if state.kill_switch:
            return self._deny("kill_switch", "global kill switch is active", intent)
        if intent.symbol in state.halted_symbols or state.data_gap:
            return self._deny("protection", "symbol or data protection is active", intent)
        return None

    def _freshness(self, ctx: dict) -> RiskDecision | None:
        age = ctx["now"] - ctx["market_time"]
        if age > self.limits.market_data_max_age:
            return self._deny("stale_market_data", "market data is stale", ctx["intent"])
        return None

    def _connector(self, ctx: dict) -> RiskDecision | None:
        state: RiskState = ctx["state"]
        if not state.connector_ready or not state.reconciled:
            return self._deny("not_ready", "connector is not ready or not reconciled", ctx["intent"])
        return None

    def _rate(self, ctx: dict) -> RiskDecision | None:
        now: datetime = ctx["now"]
        state: RiskState = ctx["state"]
        state.order_times = [item for item in state.order_times if now - item < timedelta(minutes=1)]
        if len(state.order_times) >= self.limits.max_orders_per_minute:
            return self._deny("rate_limit", "order rate limit exceeded", ctx["intent"])
        return None

    def _rules(self, ctx: dict) -> RiskDecision | None:
        intent: OrderIntent = ctx["intent"]
        _, reason = ctx["rules"].normalize(intent.quantity, ctx["price"], market=intent.limit_price is None)
        if reason:
            return self._deny(reason, f"exchange filter rejected order: {reason}", intent)
        return None

    def _balance(self, ctx: dict) -> RiskDecision | None:
        intent: OrderIntent = ctx["intent"]
        portfolio: Portfolio = ctx["portfolio"]
        if intent.side is Side.BUY and intent.quantity * ctx["price"] > portfolio.cash:
            return self._deny("insufficient_cash", "insufficient cash", intent)
        if intent.side is Side.SELL and intent.quantity > portfolio.position(intent.symbol):
            return self._deny("insufficient_position", "insufficient position", intent)
        return None

    def _order_limit(self, ctx: dict) -> RiskDecision | None:
        if ctx["intent"].quantity * ctx["price"] > self.limits.max_order_notional:
            return self._deny("max_order_notional", "order exceeds notional limit", ctx["intent"])
        return None

    def _symbol_limit(self, ctx: dict) -> RiskDecision | None:
        intent: OrderIntent = ctx["intent"]
        current = ctx["portfolio"].position(intent.symbol) * ctx["price"]
        delta = intent.quantity * ctx["price"]
        projected = current + delta if intent.side is Side.BUY else current
        if projected > self.limits.max_symbol_notional:
            return self._deny("max_symbol_position", "symbol position limit exceeded", intent)
        return None

    def _gross_limit(self, ctx: dict) -> RiskDecision | None:
        prices = {ctx["intent"].symbol: ctx["price"]}
        gross = sum(ctx["portfolio"].position(symbol) * price for symbol, price in prices.items())
        if ctx["intent"].side is Side.BUY:
            gross += ctx["intent"].quantity * ctx["price"]
        if gross > self.limits.max_gross_notional:
            return self._deny("max_gross_exposure", "gross exposure limit exceeded", ctx["intent"])
        return None

    def _loss(self, ctx: dict) -> RiskDecision | None:
        state: RiskState = ctx["state"]
        equity: Decimal = ctx["equity"]
        if state.day_start_equity - equity > self.limits.max_daily_loss:
            return self._deny("max_daily_loss", "daily loss limit exceeded", ctx["intent"])
        if state.peak_equity > 0:
            drawdown = (state.peak_equity - equity) / state.peak_equity
            if drawdown > self.limits.max_drawdown:
                return self._deny("max_drawdown", "drawdown limit exceeded", ctx["intent"])
        return None

    def _cooldown(self, ctx: dict) -> RiskDecision | None:
        state: RiskState = ctx["state"]
        if state.last_order_at and ctx["now"] - state.last_order_at < self.limits.cooldown:
            return self._deny("cooldown", "cooldown is active", ctx["intent"])
        return None

    def _deny(self, code: str, message: str, intent: OrderIntent) -> RiskDecision:
        return RiskDecision(False, code, message, intent.client_order_id)
