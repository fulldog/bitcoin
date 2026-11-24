from datetime import timedelta
from decimal import Decimal

from app.domain.filters import SymbolRules
from app.domain.models import Order, OrderIntent, OrderStatus, RunManifest, Side
from app.execution.binance import BinanceSpotAdapter, MemoryTransport, reconcile
from app.kernel.runtime import TradingKernel
from app.portfolio.accounting import Portfolio
from app.risk.engine import RiskEngine, RiskLimits, RiskState
from tests.unit.test_domain import START, bar

RULES = SymbolRules("BTCUSDT", Decimal("0.01"), Decimal("0.00001"), Decimal("0.00001"), Decimal(5))


def decision(state: RiskState, cash: str = "1000", quantity: str = "1", age: timedelta = timedelta(0)):
    portfolio = Portfolio(Decimal(cash))
    return RiskEngine(RiskLimits()).evaluate(
        OrderIntent("BTCUSDT", Side.BUY, Decimal(quantity)),
        portfolio,
        RULES,
        state,
        START + age,
        START,
        Decimal(20),
        Decimal(cash),
    )


def test_risk_checks_run_in_protective_order() -> None:
    state = RiskState(connector_ready=True, reconciled=True, day_start_equity=Decimal(1000), peak_equity=Decimal(1000))
    state.kill_switch = True
    assert decision(state).code == "kill_switch"
    state.kill_switch = False
    assert decision(state, age=timedelta(minutes=5)).code == "stale_market_data"
    state = RiskState(connector_ready=False, reconciled=False, day_start_equity=Decimal(1000), peak_equity=Decimal(1000))
    assert decision(state).code == "not_ready"


def test_risk_rejects_undersized_notional() -> None:
    state = RiskState(connector_ready=True, reconciled=True, day_start_equity=Decimal(1000), peak_equity=Decimal(1000))
    assert decision(state, quantity="0.0001").code == "MIN_NOTIONAL"


def test_timeout_queries_existing_order_without_retrying() -> None:
    order = Order("BTCUSDT", Side.BUY, Decimal(1), "cid-1")
    transport = MemoryTransport(mode="timeout")
    result = BinanceSpotAdapter(transport).submit(order)
    assert transport.calls == 1
    assert result.status is OrderStatus.ACKNOWLEDGED


def test_unknown_order_remains_unknown_when_venue_has_no_record() -> None:
    order = Order("BTCUSDT", Side.BUY, Decimal(1), "cid-2")
    result = BinanceSpotAdapter(MemoryTransport(mode="timeout_lost")).submit(order)
    assert result.status is OrderStatus.UNKNOWN


def test_not_sent_error_is_safe_to_retry() -> None:
    order = Order("BTCUSDT", Side.BUY, Decimal(1), "cid-3")
    transport = MemoryTransport(mode="not_sent")
    result = BinanceSpotAdapter(transport).submit(order)
    assert transport.calls == 2
    assert result.status is OrderStatus.ACKNOWLEDGED


def test_reconciliation_repairs_drift_and_reports_conflicts() -> None:
    local = Order("BTCUSDT", Side.BUY, Decimal(1), "cid")
    local.transition(OrderStatus.VALIDATED)
    local.transition(OrderStatus.SUBMITTING)
    local.transition(OrderStatus.UNKNOWN)
    venue = MemoryTransport().new_order(local)
    assert reconcile([local], [venue]) == []
    assert local.status is OrderStatus.ACKNOWLEDGED
    local.transition(OrderStatus.FILLED)
    conflict = MemoryTransport()
    canceled = conflict.new_order(Order("BTCUSDT", Side.BUY, Decimal(1), "other"))
    canceled = type(canceled)(local.client_order_id, OrderStatus.CANCELED, Decimal(0), None)
    assert reconcile([local], [canceled]) == ["status_conflict:cid:FILLED->CANCELED"]


def test_kernel_blocks_orders_until_ready_and_replays_snapshot() -> None:
    strategy_cash = Decimal(1000)
    kernel = TradingKernel(
        __import__("app.strategies.base", fromlist=["SmaCrossStrategy"]).SmaCrossStrategy(),
        Portfolio(strategy_cash),
        RiskEngine(RiskLimits(max_order_notional=Decimal(1000), max_symbol_notional=Decimal(1000), max_gross_notional=Decimal(1000))),
        RULES,
        RunManifest("sma_cross", "1", {}, "live", ("BTCUSDT",), "1h", Decimal(0), Decimal(0)),
    )
    assert kernel.on_bar(bar(0, "10"), START) == []
    kernel.update_readiness(True, True)
    kernel.on_bar(bar(1, "10"), START + timedelta(hours=1))
    snapshot = kernel.snapshot()
    kernel.events.append(
        {
            "type": "fill",
            "sequence": 1,
            "symbol": "BTCUSDT",
            "side": Side.BUY,
            "quantity": "1",
            "price": "10",
            "fee": "0",
            "time": START.isoformat(),
            "client_order_id": "replay",
        }
    )
    restored = TradingKernel(
        __import__("app.strategies.base", fromlist=["SmaCrossStrategy"]).SmaCrossStrategy(),
        Portfolio(Decimal(0)),
        RiskEngine(RiskLimits()),
        RULES,
        kernel.manifest,
    )
    restored.recover(snapshot, kernel.events)
    assert restored.portfolio.cash == Decimal(990)
    assert restored.portfolio.position("BTCUSDT") == Decimal(1)
    restored.update_readiness(False, False)
    assert restored.on_bar(bar(2, "10"), START + timedelta(hours=2)) == []


def test_dependency_outage_blocks_trading() -> None:
    from app.kernel.runtime import TradingKernel, run_if_available

    kernel = TradingKernel(
        __import__("app.strategies.base", fromlist=["SmaCrossStrategy"]).SmaCrossStrategy(),
        Portfolio(Decimal(1000)),
        RiskEngine(RiskLimits()),
        RULES,
        RunManifest("sma_cross", "1", {}, "live", ("BTCUSDT",), "1h", Decimal(0), Decimal(0)),
    )
    kernel.update_readiness(True, True)
    assert run_if_available(lambda: (_ for _ in ()).throw(ConnectionError("postgres unavailable")), kernel) is None
    assert kernel.on_bar(bar(0, "10"), START) == []
