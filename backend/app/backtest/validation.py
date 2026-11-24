from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from app.domain.models import Bar


@dataclass(frozen=True, slots=True)
class BiasReport:
    passed: bool
    differing_indices: tuple[int, ...]
    message: str


def detect_lookahead(
    bars: list[Bar], signal_fn: Callable[[list[Bar]], list[object]]
) -> BiasReport:
    baseline = signal_fn(bars)
    differences: list[int] = []
    for index in range(len(bars)):
        truncated = signal_fn(bars[: index + 1])
        if index < len(truncated) and truncated[-1] != baseline[index]:
            differences.append(index)
    return BiasReport(not differences, tuple(differences), "no lookahead detected" if not differences else "signals depend on future data")


def recursive_stability(values_by_warmup: dict[int, Decimal]) -> BiasReport:
    if not values_by_warmup:
        return BiasReport(False, (), "no warmup values supplied")
    values = list(values_by_warmup.values())
    passed = all(value == values[0] for value in values[1:])
    return BiasReport(passed, (), "stable across warmups" if passed else "indicator varies with warmup")
