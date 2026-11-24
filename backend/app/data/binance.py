from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import ROUND_DOWN, Decimal
from typing import Any

import httpx

from app.domain.models import Bar


def _utc_millis(value: int) -> datetime:
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc)


def parse_kline(symbol: str, interval: str, row: list[Any]) -> Bar:
    return Bar(
        symbol=symbol,
        interval=interval,
        open_time=_utc_millis(int(row[0])),
        close_time=_utc_millis(int(row[6])),
        open=Decimal(str(row[1])),
        high=Decimal(str(row[2])),
        low=Decimal(str(row[3])),
        close=Decimal(str(row[4])),
        volume=Decimal(str(row[5])),
        is_closed=True,
    )


class BinanceMarketData:
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = client

    async def fetch_klines(
        self, symbol: str, interval: str, limit: int = 500, start_time: int | None = None
    ) -> list[Bar]:
        params: dict[str, str | int] = {"symbol": symbol.upper(), "interval": interval, "limit": limit}
        if start_time is not None:
            params["startTime"] = start_time
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=15)
        try:
            response = await client.get(f"{self.base_url}/api/v3/klines", params=params)
            response.raise_for_status()
            return [parse_kline(symbol.upper(), interval, row) for row in response.json()]
        finally:
            if owns_client:
                await client.aclose()

    async def fetch_closed_range(self, symbol: str, interval: str, start: datetime, end: datetime) -> list[Bar]:
        collected: list[Bar] = []
        cursor = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)
        now = datetime.now(timezone.utc)
        while cursor < end_ms and len(collected) < 5000:
            batch = await self.fetch_klines(symbol, interval, limit=1000, start_time=cursor)
            if not batch:
                break
            collected.extend(batch)
            nxt = int(batch[-1].open_time.timestamp() * 1000) + 1
            if nxt <= cursor:
                break
            cursor = nxt
            if len(batch) < 1000:
                break
        unique = {
            bar.open_time: bar
            for bar in collected
            if start <= bar.open_time < end and bar.close_time <= now
        }
        return [unique[key] for key in sorted(unique)]


def previous_utc_day(now: datetime | None = None) -> tuple[datetime, datetime]:
    moment = now or datetime.now(timezone.utc)
    day = moment.astimezone(timezone.utc).date() - timedelta(days=1)
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    return start, start + timedelta(days=1)


@dataclass(frozen=True, slots=True)
class SymbolRules:
    tick_size: Decimal
    step_size: Decimal
    min_notional: Decimal

    def round_price(self, value: Decimal) -> Decimal:
        return (value / self.tick_size).to_integral_value(rounding=ROUND_DOWN) * self.tick_size

    def round_quantity(self, value: Decimal) -> Decimal:
        return (value / self.step_size).to_integral_value(rounding=ROUND_DOWN) * self.step_size

    def validate(self, quantity: Decimal, price: Decimal) -> str | None:
        if quantity <= 0:
            return "quantity must be positive"
        if self.round_quantity(quantity) != quantity:
            return "quantity does not match step size"
        if quantity * price < self.min_notional:
            return "order is below minimum notional"
        return None
