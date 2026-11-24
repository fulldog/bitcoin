from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.backtest.engine import RestingOrder, slipped_price
from app.domain.filters import SymbolRules
from app.domain.models import Bar, Fill, Order, OrderStatus, RiskDecision, RunManifest
from app.portfolio.accounting import Portfolio
from app.risk.engine import RiskEngine, RiskState
from app.strategies.base import Strategy, StrategyContext


@dataclass
class RuntimeSnapshot:
    cash: Decimal
    positions: dict[str, str]
    sequence: int
    orders: list[dict]


def run_if_available(operation, kernel: "TradingKernel"):
    try:
        return operation()
    except ConnectionError:
        kernel.ready = False
        kernel.state.connector_ready = False
        kernel.state.reconciled = False
        return None


class TradingKernel:
    def __init__(self, strategy: Strategy, portfolio: Portfolio, risk: RiskEngine, rules: SymbolRules, manifest: RunManifest) -> None:
        self.strategy = strategy
        self.portfolio = portfolio
        self.risk = risk
        self.rules = rules
        self.manifest = manifest
        self.state = RiskState(day_start_equity=portfolio.cash, peak_equity=portfolio.cash)
        self.ready = False
        self.resting: list[RestingOrder] = []
        self.fills: list[Fill] = []
        self.events: list[dict] = []
        self.history: list[Bar] = []
        self.sequence = 0
        self.decisions: list[RiskDecision] = []
        self.strategy.initialize(StrategyContext([], portfolio.position(manifest.symbols[0]), portfolio.cash))

    def recover(self, snapshot: RuntimeSnapshot, events: list[dict]) -> None:
        self.portfolio.cash = snapshot.cash
        self.portfolio.positions = {symbol: Decimal(quantity) for symbol, quantity in snapshot.positions.items()}
        self.sequence = snapshot.sequence
        for event in events:
            if event.get("type") != "fill" or event["sequence"] <= snapshot.sequence:
                continue
            fill = Fill(
                event["symbol"],
                event["side"],
                Decimal(event["quantity"]),
                Decimal(event["price"]),
                Decimal(event["fee"]),
                datetime.fromisoformat(event["time"]),
                event["client_order_id"],
            )
            self.portfolio.apply_fill(fill)
            self.fills.append(fill)
            self.sequence = max(self.sequence, event["sequence"])
        self.ready = False

    def update_readiness(self, connector_ready: bool, reconciled: bool, data_gap: bool = False) -> None:
        self.state.connector_ready = connector_ready
        self.state.reconciled = reconciled
        self.state.data_gap = data_gap
        self.ready = connector_ready and reconciled and not self.state.kill_switch and not data_gap

    def kill(self) -> None:
        self.state.kill_switch = True
        self.ready = False

    def on_bar(self, bar: Bar, now: datetime) -> list[Fill]:
        self.history.append(bar)
        if not self.ready or not bar.is_closed:
            self.events.append({"type": "blocked", "reason": "not_ready", "time": now.isoformat()})
            return []
        produced = []
        index = len(self.history) - 1
        for item in self.resting:
            fill = self._fill(item, bar, index)
            if fill:
                produced.append(fill)
        symbol = self.manifest.symbols[0]
        mark = self.portfolio.equity({symbol: bar.close})
        self.state.peak_equity = max(self.state.peak_equity, mark)
        context = StrategyContext(self.history, self.portfolio.position(symbol), self.portfolio.cash, self.portfolio.average_prices.get(symbol))
        for offset, intent in enumerate(self.strategy.on_bar(context, bar)):
            decision = self.risk.evaluate(intent, self.portfolio, self.rules, self.state, now, bar.close_time, bar.close, mark)
            self.decisions.append(decision)
            if not decision.allowed:
                continue
            order = Order(intent.symbol, intent.side, intent.quantity, intent.client_order_id or f"live-{index}-{offset}")
            order.transition(OrderStatus.VALIDATED)
            order.transition(OrderStatus.SUBMITTING)
            order.transition(OrderStatus.ACKNOWLEDGED)
            self.resting.append(RestingOrder(order, intent.limit_price, index))
            self.state.last_order_at = now
        return produced

    def snapshot(self) -> RuntimeSnapshot:
        return RuntimeSnapshot(
            self.portfolio.cash,
            {symbol: str(quantity) for symbol, quantity in self.portfolio.positions.items()},
            self.sequence,
            [],
        )

    def _fill(self, item: RestingOrder, bar: Bar, index: int) -> Fill | None:
        if item.submitted_index >= index:
            return None
        raw = bar.open if item.limit_price is None else item.limit_price
        if item.limit_price is not None and not (bar.low <= item.limit_price <= bar.high):
            return None
        price = slipped_price(item.order.side, raw, self.manifest.slippage_bps)
        remaining = item.order.quantity - item.order.filled_quantity
        affordable = remaining
        if item.order.side.value == "BUY":
            unit = price * (Decimal(1) + self.manifest.fee_rate)
            affordable = self.portfolio.cash / unit if unit else Decimal(0)
        else:
            affordable = self.portfolio.position(item.order.symbol)
        quantity, reason = self.rules.normalize(min(remaining, affordable), price, market=item.limit_price is None)
        if reason or quantity <= 0 or quantity > remaining:
            return None
        fee = quantity * price * self.manifest.fee_rate
        fill = Fill(item.order.symbol, item.order.side, quantity, price, fee, bar.open_time, item.order.client_order_id)
        self.portfolio.apply_fill(fill)
        self.fills.append(fill)
        item.order.filled_quantity += quantity
        item.order.transition(OrderStatus.FILLED if item.order.filled_quantity >= item.order.quantity else OrderStatus.PARTIALLY_FILLED)
        self.sequence += 1
        self.events.append({"type": "fill", "sequence": self.sequence, "symbol": fill.symbol, "side": fill.side, "quantity": str(fill.quantity), "price": str(fill.price), "fee": str(fill.fee), "time": fill.time.isoformat(), "client_order_id": fill.client_order_id})
        return fill
