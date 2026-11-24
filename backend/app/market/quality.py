import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from hashlib import sha256

from app.domain.models import Bar

INTERVALS = {
    "1m": timedelta(minutes=1),
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "1d": timedelta(days=1),
}


@dataclass(frozen=True, slots=True)
class QualityReport:
    ready: bool
    duplicates: int
    out_of_order: int
    gaps: int
    unclosed: int
    issues: tuple[str, ...]


def inspect_bars(bars: list[Bar]) -> QualityReport:
    issues: list[str] = []
    duplicates = out_of_order = gaps = unclosed = 0
    seen: set[tuple[str, str, datetime]] = set()
    last: dict[tuple[str, str], datetime] = {}
    for bar in bars:
        key = (bar.symbol, bar.interval, bar.open_time)
        if key in seen:
            duplicates += 1
            issues.append(f"duplicate {bar.symbol} {bar.open_time.isoformat()}")
            continue
        seen.add(key)
        if not bar.is_closed:
            unclosed += 1
            issues.append(f"unclosed {bar.symbol} {bar.open_time.isoformat()}")
        series = (bar.symbol, bar.interval)
        previous = last.get(series)
        if previous is not None:
            if bar.open_time <= previous:
                out_of_order += 1
                issues.append(f"out_of_order {bar.symbol} {bar.open_time.isoformat()}")
            else:
                expected = previous + INTERVALS[bar.interval]
                if bar.open_time != expected:
                    gaps += 1
                    issues.append(f"gap {bar.symbol} {previous.isoformat()} -> {bar.open_time.isoformat()}")
        last[series] = bar.open_time
    ready = duplicates == 0 and out_of_order == 0 and gaps == 0 and unclosed == 0
    return QualityReport(ready, duplicates, out_of_order, gaps, unclosed, tuple(issues))


@dataclass
class Dataset:
    dataset_id: str
    bars: tuple[Bar, ...]
    digest: str
    quality: QualityReport

    @classmethod
    def freeze(cls, dataset_id: str, bars: list[Bar]) -> "Dataset":
        quality = inspect_bars(bars)
        ordered = tuple(sorted(bars, key=lambda bar: (bar.symbol, bar.interval, bar.open_time)))
        payload = [
            {
                "symbol": bar.symbol,
                "interval": bar.interval,
                "open_time": bar.open_time.isoformat(),
                "close": str(bar.close),
                "volume": str(bar.volume),
                "closed": bar.is_closed,
            }
            for bar in ordered
        ]
        digest = sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()
        return cls(dataset_id, ordered, digest, quality)


@dataclass
class MarketCursor:
    interval: str = "1m"
    ready: bool = False
    reconnects: int = 0
    last_open_time: datetime | None = None
    issues: list[str] = field(default_factory=list)

    def disconnect(self) -> None:
        self.ready = False
        self.reconnects += 1

    def observe(self, bar: Bar) -> None:
        if not bar.is_closed:
            self.ready = False
            self.issues.append("unclosed")
            return
        if self.last_open_time is not None:
            if bar.open_time < self.last_open_time:
                self.ready = False
                self.issues.append("out_of_order")
                return
            if bar.open_time == self.last_open_time:
                self.ready = False
                self.issues.append("duplicate")
                return
            if bar.open_time != self.last_open_time + INTERVALS[self.interval]:
                self.ready = False
                self.issues.append("gap")
                return
        self.last_open_time = bar.open_time
        self.ready = True


def backoff_seconds(attempt: int, base: float = 1, cap: float = 30) -> float:
    return min(cap, base * (2**attempt))
