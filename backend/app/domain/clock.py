from datetime import datetime, timedelta, timezone


class Clock:
    def now(self) -> datetime:
        raise NotImplementedError


class SystemClock(Clock):
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class DeterministicClock(Clock):
    def __init__(self, start: datetime) -> None:
        if start.tzinfo is None:
            raise ValueError("clock must use timezone-aware UTC time")
        self._now = start.astimezone(timezone.utc)

    def now(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> datetime:
        self._now += delta
        return self._now

    def set(self, moment: datetime) -> None:
        self._now = moment.astimezone(timezone.utc)
