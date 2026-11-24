from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from app.domain.filters import SymbolRules
from app.domain.models import OrderIntent, Side
from app.execution.paper import PaperAccount, PaperBroker
from app.kernel.snapshot import load_snapshot, save_snapshot
from app.portfolio.accounting import Portfolio
from app.risk.engine import RiskEngine, RiskLimits, RiskState


def test_risk_blocks_orders_over_limit():
    risk = RiskEngine(RiskLimits(max_order_notional=Decimal(10)))
    portfolio = Portfolio(Decimal(1000))
    rules = SymbolRules("BTCUSDT", Decimal("0.01"), Decimal("0.001"), Decimal("0.001"), Decimal(10))
    state = RiskState(connector_ready=True, reconciled=True, day_start_equity=Decimal(1000), peak_equity=Decimal(1000))
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    decision = risk.evaluate(
        OrderIntent("BTCUSDT", Side.BUY, Decimal(1)),
        portfolio,
        rules,
        state,
        now,
        now,
        Decimal(100),
        Decimal(1000),
    )
    assert decision.allowed is False
    assert decision.code == "max_order_notional"


def test_paper_broker_is_idempotent_for_filled_order():
    broker = PaperBroker(PaperAccount(cash=Decimal(1000)))
    intent = OrderIntent("BTCUSDT", Side.BUY, Decimal(1), client_order_id="same")
    timestamp = datetime(2025, 1, 1, tzinfo=timezone.utc)
    first = broker.submit(intent, Decimal(100), timestamp)
    second = broker.submit(intent, Decimal(100), timestamp)
    assert first.client_order_id == second.client_order_id
    assert broker.account.position == Decimal(1)


def test_snapshot_round_trip(tmp_path: Path):
    path = tmp_path / "snapshot.json"
    account = PaperAccount(Decimal("12.5"), Decimal("0.2"))
    save_snapshot(path, account, "READY")
    restored, status = load_snapshot(path)
    assert restored.cash == account.cash
    assert restored.position == account.position
    assert status == "READY"
