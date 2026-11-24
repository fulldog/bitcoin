from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from app.domain.filters import SymbolRules
from app.domain.models import OrderIntent, Side
from app.kernel.snapshot import AccountSnapshot, load_snapshot, save_snapshot
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


def test_snapshot_round_trip(tmp_path: Path):
    path = tmp_path / "snapshot.json"
    account = AccountSnapshot(Decimal("12.5"), Decimal("0.2"))
    save_snapshot(path, account, "READY")
    restored, status = load_snapshot(path)
    assert restored.cash == account.cash
    assert restored.position == account.position
    assert status == "READY"
