from datetime import datetime, timedelta, timezone
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class FixedClock:
    def __init__(self, value: datetime) -> None:
        if value.tzinfo is None:
            raise ValueError("fixed clock must use a timezone-aware datetime")
        self._value = value.astimezone(timezone.utc)

    def now(self) -> datetime:
        return self._value

    def advance(self, seconds: int) -> None:
        self._value += timedelta(seconds=seconds)
