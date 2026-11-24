from dataclasses import dataclass, field

from app.domain.models import OPEN_STATUSES, ExecutionReport, Order, OrderStatus


class NotSent(Exception):
    """The request never left the local process and may be retried."""


class VenueTimeout(Exception):
    """The venue result is unknown; the request must not be retried blindly."""


@dataclass
class MemoryTransport:
    mode: str = "ok"
    calls: int = 0
    orders: dict[str, ExecutionReport] = field(default_factory=dict)

    def new_order(self, order: Order) -> ExecutionReport:
        self.calls += 1
        if self.mode == "not_sent" and self.calls == 1:
            raise NotSent()
        if self.mode == "timeout_lost":
            raise VenueTimeout()
        report = ExecutionReport(order.client_order_id, OrderStatus.ACKNOWLEDGED, order.filled_quantity, order.average_price, f"venue-{self.calls}")
        self.orders[order.client_order_id] = report
        if self.mode == "timeout":
            raise VenueTimeout()
        return report

    def get_order(self, client_order_id: str) -> ExecutionReport | None:
        return self.orders.get(client_order_id)

    def open_orders(self) -> list[ExecutionReport]:
        return list(self.orders.values())


class BinanceSpotAdapter:
    def __init__(self, transport: MemoryTransport) -> None:
        self.transport = transport

    def submit(self, order: Order) -> Order:
        if order.status is OrderStatus.CREATED:
            order.transition(OrderStatus.VALIDATED)
        if order.status is OrderStatus.VALIDATED:
            order.transition(OrderStatus.SUBMITTING)
        try:
            report: ExecutionReport | None = self._place(order)
        except NotSent:
            report = self._place(order)
        except VenueTimeout:
            order.transition(OrderStatus.UNKNOWN, "timeout")
            report = self.transport.get_order(order.client_order_id)
            if report is None:
                return order
        if report is None:
            return order
        self.apply_report(order, report)
        return order

    def _place(self, order: Order) -> ExecutionReport:
        return self.transport.new_order(order)

    def apply_report(self, order: Order, report: ExecutionReport) -> None:
        if report.status is not order.status:
            order.transition(report.status, report.reason or "venue")
        order.filled_quantity = report.filled_quantity
        order.average_price = report.average_price


def reconcile(local_orders: list[Order], venue_orders: list[ExecutionReport]) -> list[str]:
    venue = {item.client_order_id: item for item in venue_orders}
    alerts: list[str] = []
    for order in local_orders:
        report = venue.get(order.client_order_id)
        if report is None:
            if order.status in OPEN_STATUSES:
                alerts.append(f"missing_on_venue:{order.client_order_id}")
            continue
        if report.status is order.status:
            continue
        try:
            order.transition(report.status, "reconciled")
            order.filled_quantity = report.filled_quantity
        except ValueError:
            alerts.append(f"status_conflict:{order.client_order_id}:{order.status}->{report.status}")
    return alerts
