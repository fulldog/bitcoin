from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal


@dataclass(frozen=True, slots=True)
class SymbolRules:
    symbol: str
    tick_size: Decimal
    step_size: Decimal
    min_qty: Decimal
    min_notional: Decimal
    market_step_size: Decimal | None = None
    market_min_qty: Decimal | None = None

    def normalize(self, quantity: Decimal, price: Decimal, market: bool = False) -> tuple[Decimal, str | None]:
        step = self.market_step_size if market and self.market_step_size else self.step_size
        minimum = self.market_min_qty if market and self.market_min_qty else self.min_qty
        quantity = round_down(quantity, step)
        price = round_down(price, self.tick_size)
        if quantity < minimum:
            return quantity, "LOT_SIZE"
        if price * quantity < self.min_notional:
            return quantity, "MIN_NOTIONAL"
        return quantity, None


def round_down(value: Decimal, step: Decimal) -> Decimal:
    if step <= 0:
        raise ValueError("step must be positive")
    units = (value / step).to_integral_value(rounding=ROUND_DOWN)
    return units * step


def parse_symbol_rules(payload: dict) -> SymbolRules:
    filters = {item["filterType"]: item for item in payload["filters"]}
    lot = filters["LOT_SIZE"]
    price = filters["PRICE_FILTER"]
    notional = filters.get("NOTIONAL", filters.get("MIN_NOTIONAL", {}))
    market = filters.get("MARKET_LOT_SIZE")
    return SymbolRules(
        symbol=payload["symbol"],
        tick_size=Decimal(price["tickSize"]),
        step_size=Decimal(lot["stepSize"]),
        min_qty=Decimal(lot["minQty"]),
        min_notional=Decimal(notional.get("minNotional", "0")),
        market_step_size=Decimal(market["stepSize"]) if market else None,
        market_min_qty=Decimal(market["minQty"]) if market else None,
    )
