from dataclasses import dataclass
from decimal import Decimal

from app.backtest.metrics import Performance, performance
from app.domain.filters import SymbolRules
from app.domain.models import (
    Bar,
    EquityPoint,
    Fill,
    Order,
    OrderStatus,
    RunManifest,
    Side,
    fill_fingerprint,
)
from app.portfolio.accounting import Portfolio
from app.risk.engine import RiskEngine, RiskLimits, RiskState
from app.strategies.base import Strategy, StrategyContext


def slipped_price(side: Side, price: Decimal, slippage_bps: Decimal) -> Decimal:
    slip = slippage_bps / Decimal(10000)
    return price * (Decimal(1) + slip) if side is Side.BUY else price * (Decimal(1) - slip)


@dataclass
class RestingOrder:
    order: Order
    limit_price: Decimal | None
    submitted_index: int


@dataclass
class BacktestResult:
    manifest: RunManifest
    fills: list[Fill]
    equity: list[EquityPoint]
    decisions: list
    assumptions: dict
    fill_hash: str
    metrics: Performance


class BacktestEngine:
    assumptions = {
        "market_fill": "next_bar_open",
        "limit_fill": "later_bar_touch",
        "new_order_same_bar_fill": False,
        "fee": "quote_notional",
        "partial_fill": "available_balance_and_position",
    }

    def __init__(self, rules: SymbolRules, limits: RiskLimits | None = None) -> None:
        self.rules = rules
        self.risk = RiskEngine(limits or RiskLimits())

    def run(self, strategy: Strategy, bars: list[Bar], manifest: RunManifest, cash: Decimal) -> BacktestResult:
        strategy.initialize(StrategyContext([], Decimal(0), cash))
        portfolio = Portfolio(cash)
        state = RiskState(connector_ready=True, reconciled=True, day_start_equity=cash, peak_equity=cash)
        resting: list[RestingOrder] = []
        fills: list[Fill] = []
        equity: list[EquityPoint] = []
        decisions = []
        exposed = 0
        for index, bar in enumerate(bars):
            if not bar.is_closed:
                continue
            self._match(resting, bar, index, portfolio, fills, manifest)
            resting = [item for item in resting if item.order.status not in {OrderStatus.FILLED, OrderStatus.REJECTED, OrderStatus.CANCELED}]
            mark = portfolio.equity({bar.symbol: bar.close})
            state.peak_equity = max(state.peak_equity, mark)
            if portfolio.position(bar.symbol) > 0:
                exposed += 1
            equity.append(EquityPoint(bar.close_time, mark))
            context = StrategyContext(bars[: index + 1], portfolio.position(bar.symbol), portfolio.cash, portfolio.average_prices.get(bar.symbol))
            for offset, intent in enumerate(strategy.on_bar(context, bar)):
                decision = self.risk.evaluate(intent, portfolio, self.rules, state, bar.close_time, bar.close_time, bar.close, mark)
                decisions.append(decision)
                if not decision.allowed:
                    continue
                order = Order(
                    symbol=intent.symbol,
                    side=intent.side,
                    quantity=intent.quantity,
                    client_order_id=intent.client_order_id or f"{bar.symbol}-{index}-{offset}",
                )
                order.transition(OrderStatus.VALIDATED)
                order.transition(OrderStatus.SUBMITTING)
                order.transition(OrderStatus.ACKNOWLEDGED)
                resting.append(RestingOrder(order, intent.limit_price, index))
                state.last_order_at = bar.close_time
                state.order_times.append(bar.close_time)
        metrics = performance(equity, fills, manifest.interval, exposed)
        return BacktestResult(manifest, fills, equity, decisions, dict(self.assumptions), fill_fingerprint(fills), metrics)

    def _match(self, resting: list[RestingOrder], bar: Bar, index: int, portfolio: Portfolio, fills: list[Fill], manifest: RunManifest) -> None:
        for item in resting:
            if item.submitted_index >= index or item.order.symbol != bar.symbol:
                continue
            raw = bar.open if item.limit_price is None else item.limit_price
            if item.limit_price is not None and not (bar.low <= item.limit_price <= bar.high):
                continue
            price = slipped_price(item.order.side, raw, manifest.slippage_bps)
            remaining = item.order.quantity - item.order.filled_quantity
            affordable = remaining
            if item.order.side is Side.BUY:
                unit = price * (Decimal(1) + manifest.fee_rate)
                affordable = portfolio.cash / unit if unit else Decimal(0)
            else:
                affordable = portfolio.position(item.order.symbol)
            quantity = min(remaining, affordable)
            quantity, reason = self.rules.normalize(quantity, price, market=item.limit_price is None)
            if reason or quantity <= 0:
                continue
            fee = quantity * price * manifest.fee_rate
            fill = Fill(item.order.symbol, item.order.side, quantity, price, fee, bar.open_time, item.order.client_order_id)
            portfolio.apply_fill(fill)
            fills.append(fill)
            item.order.filled_quantity += quantity
            item.order.average_price = price
            status = OrderStatus.FILLED if item.order.filled_quantity >= item.order.quantity else OrderStatus.PARTIALLY_FILLED
            item.order.transition(status)


def lookahead_divergence(strategy_factory, bars: list[Bar]) -> bool:
    def collect(leak: bool) -> list[tuple]:
        strategy = strategy_factory()
        strategy.initialize(StrategyContext([], Decimal(0), Decimal(1000)))
        position = Decimal(0)
        output = []
        for index, bar in enumerate(bars):
            history = bars if leak else bars[: index + 1]
            intents = strategy.on_bar(StrategyContext(history, position, Decimal(1000)), bar)
            output.append(tuple((item.side.value, f"{item.quantity:.8f}") for item in intents))
            for item in intents:
                position += item.quantity if item.side is Side.BUY else -item.quantity
        return output

    return collect(False) != collect(True)


def walk_forward(engine: BacktestEngine, strategy_factory, bars: list[Bar], manifest: RunManifest, cash: Decimal, folds: int = 2) -> list[dict]:
    if folds < 1 or len(bars) < folds + 1:
        raise ValueError("not enough bars for walk-forward")
    width = len(bars) // (folds + 1)
    reports = []
    for fold in range(folds):
        train_end = width * (fold + 1)
        test_end = width * (fold + 2)
        train = engine.run(strategy_factory(), bars[:train_end], manifest, cash)
        test = engine.run(strategy_factory(), bars[train_end:test_end], manifest, cash)
        reports.append({"fold": fold, "train_return": train.metrics.total_return, "test_return": test.metrics.total_return})
    return reports
