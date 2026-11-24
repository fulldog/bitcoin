from decimal import Decimal

from app.domain.models import Fill, Position, Side


class Portfolio:
    def __init__(self, cash: Decimal) -> None:
        if cash < 0:
            raise ValueError("cash cannot be negative")
        self.cash = cash
        self.positions: dict[str, Decimal] = {}
        self.average_prices: dict[str, Decimal] = {}
        self.locked: dict[str, Decimal] = {}

    def position(self, symbol: str) -> Decimal:
        return self.positions.get(symbol, Decimal(0))

    def equity(self, prices: dict[str, Decimal]) -> Decimal:
        value = self.cash
        for symbol, quantity in self.positions.items():
            value += quantity * prices[symbol]
        return value

    def snapshot(self) -> list[Position]:
        return [
            Position(symbol, quantity, self.average_prices.get(symbol, Decimal(0)))
            for symbol, quantity in self.positions.items()
            if quantity > 0
        ]

    def apply_fill(self, fill: Fill) -> None:
        if fill.quantity <= 0:
            raise ValueError("fill quantity must be positive")
        gross = fill.quantity * fill.price
        current = self.position(fill.symbol)
        if fill.side is Side.BUY:
            total = gross + fill.fee
            if total > self.cash:
                raise ValueError("insufficient cash")
            new_qty = current + fill.quantity
            old_cost = self.average_prices.get(fill.symbol, Decimal(0)) * current
            self.average_prices[fill.symbol] = (old_cost + gross) / new_qty
            self.positions[fill.symbol] = new_qty
            self.cash -= total
        else:
            if fill.quantity > current:
                raise ValueError("insufficient position")
            self.positions[fill.symbol] = current - fill.quantity
            self.cash += gross - fill.fee
        if self.cash < 0 or self.position(fill.symbol) < 0:
            raise AssertionError("portfolio invariant broken")
