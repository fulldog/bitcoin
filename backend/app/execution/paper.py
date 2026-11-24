from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.domain.models import Fill, Order, OrderIntent, OrderStatus, Side


@dataclass(slots=True)
class PaperAccount:
    cash: Decimal = Decimal(1000)
    position: Decimal = Decimal(0)


class PaperBroker:
    def __init__(self, account: PaperAccount | None = None, fee_rate: Decimal = Decimal("0.001")) -> None:
        self.account = account or PaperAccount()
        self.fee_rate = fee_rate
        self.orders: dict[str, Order] = {}

    def submit(self, intent: OrderIntent, price: Decimal, timestamp) -> Fill:
        order_id = intent.client_order_id or f"paper-{len(self.orders) + 1}"
        if order_id in self.orders:
            order = self.orders[order_id]
            if order.status is OrderStatus.FILLED:
                return Fill(intent.symbol, intent.side, order.filled_quantity, order.average_price or price, Decimal(0), timestamp, order_id)
            raise ValueError("duplicate active client order id")
        order = Order(intent.symbol, intent.side, intent.quantity, order_id)
        order.transition(OrderStatus.VALIDATED)
        order.transition(OrderStatus.SUBMITTING)
        order.transition(OrderStatus.ACKNOWLEDGED)
        notional = intent.quantity * price
        fee = notional * self.fee_rate
        if intent.side is Side.BUY:
            if self.account.cash < notional + fee:
                order.transition(OrderStatus.REJECTED, "insufficient cash")
                raise ValueError("insufficient cash")
            self.account.cash -= notional + fee
            self.account.position += intent.quantity
        else:
            if self.account.position < intent.quantity:
                order.transition(OrderStatus.REJECTED, "insufficient position")
                raise ValueError("insufficient position")
            self.account.cash += notional - fee
            self.account.position -= intent.quantity
        order.filled_quantity = intent.quantity
        order.average_price = price
        order.transition(OrderStatus.FILLED)
        self.orders[order_id] = order
        return Fill(intent.symbol, intent.side, intent.quantity, price, fee, timestamp, order_id)
