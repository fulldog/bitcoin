import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from hashlib import sha256
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    CREATED = "CREATED"
    VALIDATED = "VALIDATED"
    SUBMITTING = "SUBMITTING"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


OPEN_STATUSES = {
    OrderStatus.CREATED,
    OrderStatus.VALIDATED,
    OrderStatus.SUBMITTING,
    OrderStatus.ACKNOWLEDGED,
    OrderStatus.PARTIALLY_FILLED,
    OrderStatus.UNKNOWN,
}


@dataclass(frozen=True, slots=True)
class Bar:
    symbol: str
    interval: str
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    is_closed: bool = True
    source: str = "binance"
    quality: str = "ok"

    def __post_init__(self) -> None:
        if self.open_time.tzinfo is None or self.close_time.tzinfo is None:
            raise ValueError("bar timestamps must be timezone-aware")
        if self.high < max(self.open, self.close, self.low) or self.low > min(self.open, self.close, self.high):
            raise ValueError("bar OHLC values are inconsistent")
        if self.volume < 0:
            raise ValueError("bar volume cannot be negative")


@dataclass(frozen=True, slots=True)
class Signal:
    symbol: str
    side: Side | None
    reason: str
    time: datetime


@dataclass(frozen=True, slots=True)
class OrderIntent:
    symbol: str
    side: Side
    quantity: Decimal
    limit_price: Decimal | None = None
    client_order_id: str | None = None


@dataclass(slots=True)
class Order:
    symbol: str
    side: Side
    quantity: Decimal
    client_order_id: str
    status: OrderStatus = OrderStatus.CREATED
    filled_quantity: Decimal = Decimal(0)
    average_price: Decimal | None = None
    reason: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def transition(self, status: OrderStatus, reason: str | None = None) -> None:
        allowed = {
            OrderStatus.CREATED: {OrderStatus.VALIDATED, OrderStatus.REJECTED},
            OrderStatus.VALIDATED: {OrderStatus.SUBMITTING, OrderStatus.REJECTED},
            OrderStatus.SUBMITTING: {
                OrderStatus.ACKNOWLEDGED,
                OrderStatus.UNKNOWN,
                OrderStatus.REJECTED,
            },
            OrderStatus.ACKNOWLEDGED: {
                OrderStatus.PARTIALLY_FILLED,
                OrderStatus.FILLED,
                OrderStatus.CANCELED,
                OrderStatus.UNKNOWN,
            },
            OrderStatus.PARTIALLY_FILLED: {
                OrderStatus.PARTIALLY_FILLED,
                OrderStatus.FILLED,
                OrderStatus.CANCELED,
                OrderStatus.UNKNOWN,
            },
            OrderStatus.UNKNOWN: {
                OrderStatus.ACKNOWLEDGED,
                OrderStatus.PARTIALLY_FILLED,
                OrderStatus.FILLED,
                OrderStatus.CANCELED,
                OrderStatus.REJECTED,
            },
            OrderStatus.FILLED: set(),
            OrderStatus.CANCELED: set(),
            OrderStatus.REJECTED: set(),
        }
        if status not in allowed[self.status]:
            raise ValueError(f"invalid order transition {self.status} -> {status}")
        self.status = status
        self.reason = reason
        self.updated_at = utc_now()


@dataclass(frozen=True, slots=True)
class RiskDecision:
    allowed: bool
    code: str
    message: str
    client_order_id: str | None = None


@dataclass(frozen=True, slots=True)
class Fill:
    symbol: str
    side: Side
    quantity: Decimal
    price: Decimal
    fee: Decimal
    time: datetime
    client_order_id: str


@dataclass(frozen=True, slots=True)
class ExecutionReport:
    client_order_id: str
    status: OrderStatus
    filled_quantity: Decimal
    average_price: Decimal | None
    venue_order_id: str | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class Balance:
    asset: str
    free: Decimal
    locked: Decimal = Decimal(0)


@dataclass(frozen=True, slots=True)
class Position:
    symbol: str
    quantity: Decimal
    average_price: Decimal


@dataclass(frozen=True, slots=True)
class EquityPoint:
    time: datetime
    equity: Decimal


@dataclass(frozen=True, slots=True)
class RunManifest:
    strategy_name: str
    strategy_version: str
    parameters: dict[str, Any]
    dataset_id: str
    symbols: tuple[str, ...]
    interval: str
    fee_rate: Decimal
    slippage_bps: Decimal
    engine_version: str = "0.1.0"
    random_seed: int = 0
    code_sha: str = "unknown"
    started_at: str = ""
    ended_at: str = ""

    def fingerprint(self) -> str:
        payload = {
            "strategy_name": self.strategy_name,
            "strategy_version": self.strategy_version,
            "parameters": self.parameters,
            "dataset_id": self.dataset_id,
            "symbols": list(self.symbols),
            "interval": self.interval,
            "fee_rate": str(self.fee_rate),
            "slippage_bps": str(self.slippage_bps),
            "engine_version": self.engine_version,
            "random_seed": self.random_seed,
            "code_sha": self.code_sha,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return sha256(encoded).hexdigest()


def fill_fingerprint(fills: list[Fill]) -> str:
    rows = [
        {
            "time": item.time.isoformat(),
            "symbol": item.symbol,
            "side": item.side.value,
            "quantity": f"{item.quantity:.8f}",
            "price": f"{item.price:.8f}",
            "fee": f"{item.fee:.8f}",
            "client_order_id": item.client_order_id,
        }
        for item in fills
    ]
    encoded = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    return sha256(encoded).hexdigest()
