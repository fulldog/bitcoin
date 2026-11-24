from decimal import Decimal

from app.adapters.binance_execution import BinanceExecution, apply_exchange_status
from app.domain.models import Order, OrderStatus, Side


def test_signature_is_deterministic():
    adapter = BinanceExecution("https://example.invalid", "key", "secret")
    assert (
        adapter.signature({"symbol": "BTCUSDT", "timestamp": 1})
        == "ef9d3d77a34d9a13a21a4c2d7f3e8cb091888a74ca62b5b62f430e78eded95ba"
    )


def test_unknown_order_can_be_reconciled():
    order = Order("BTCUSDT", Side.BUY, Decimal(1), "client-1")
    order.transition(OrderStatus.VALIDATED)
    order.transition(OrderStatus.SUBMITTING)
    order.transition(OrderStatus.UNKNOWN)
    apply_exchange_status(order, "FILLED")
    assert order.status is OrderStatus.FILLED
