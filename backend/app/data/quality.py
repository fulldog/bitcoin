from dataclasses import dataclass
from datetime import timedelta

from app.domain.models import Bar


@dataclass(frozen=True, slots=True)
class DataQuality:
    accepted: bool
    reason: str = "ok"


def validate_bars(bars: list[Bar], expected_seconds: int) -> DataQuality:
    if not bars:
        return DataQuality(False, "empty dataset")
    previous = None
    expected_gap = timedelta(seconds=expected_seconds)
    for bar in bars:
        if not bar.is_closed:
            return DataQuality(False, "dataset contains an open bar")
        if previous is not None:
            if bar.open_time <= previous.open_time:
                return DataQuality(False, "bars are not strictly ordered")
            if bar.open_time - previous.open_time != expected_gap:
                return DataQuality(False, "dataset contains a gap or duplicate")
        previous = bar
    return DataQuality(True)


def deduplicate_bars(bars: list[Bar]) -> list[Bar]:
    unique = {bar.open_time: bar for bar in bars}
    return [unique[key] for key in sorted(unique)]
