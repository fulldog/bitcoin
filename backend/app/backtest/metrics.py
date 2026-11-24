from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from math import sqrt

from app.domain.models import EquityPoint, Fill

INTERVAL_PERIODS = {"1m": 60 * 24 * 365, "5m": 12 * 24 * 365, "15m": 4 * 24 * 365, "1h": 24 * 365, "4h": 6 * 365, "1d": 365}


@dataclass(frozen=True, slots=True)
class Performance:
    total_return: Decimal
    annualized_return: Decimal
    max_drawdown: Decimal
    sharpe: Decimal
    sortino: Decimal
    calmar: Decimal
    win_rate: Decimal
    profit_factor: Decimal
    turnover: Decimal
    exposure: Decimal
    trade_count: int


def _returns(equity: list[Decimal]) -> list[Decimal]:
    values = []
    for previous, current in zip(equity, equity[1:]):
        if previous == 0:
            values.append(Decimal(0))
        else:
            values.append((current - previous) / previous)
    return values


def max_drawdown(equity: list[Decimal]) -> Decimal:
    peak = equity[0]
    worst = Decimal(0)
    for value in equity:
        peak = max(peak, value)
        if peak > 0:
            worst = max(worst, (peak - value) / peak)
    return worst


def _std(values: list[Decimal], downside: bool = False) -> Decimal:
    if len(values) < 2:
        return Decimal(0)
    population = [min(value, Decimal(0)) for value in values] if downside else values
    mean = sum(population, Decimal(0)) / Decimal(len(population))
    variance = sum((value - mean) ** 2 for value in population) / Decimal(len(population) - 1)
    return Decimal(sqrt(variance))


def trade_pnls(fills: list[Fill]) -> list[Decimal]:
    lots: list[list[Decimal]] = []
    pnls: list[Decimal] = []
    for fill in fills:
        if fill.side.value == "BUY":
            lots.append([fill.quantity, fill.price, fill.fee])
            continue
        remaining = fill.quantity
        cost = Decimal(0)
        while remaining > 0 and lots:
            take = min(remaining, lots[0][0])
            cost += take * lots[0][1] + lots[0][2] * (take / lots[0][0])
            lots[0][0] -= take
            remaining -= take
            if lots[0][0] == 0:
                lots.pop(0)
        pnls.append(fill.quantity * fill.price - fill.fee - cost)
    return pnls


def performance(equity: list[EquityPoint], fills: list[Fill], interval: str, exposure_bars: int) -> Performance:
    values = [point.equity for point in equity]
    if not values:
        zero = Decimal(0)
        return Performance(zero, zero, zero, zero, zero, zero, zero, zero, zero, zero, 0)
    returns = _returns(values)
    total = (values[-1] - values[0]) / values[0] if values[0] else Decimal(0)
    periods = INTERVAL_PERIODS[interval]
    years = (len(values) - 1) / periods
    annualized = Decimal(0)
    if years > 0 and total > -1:
        annualized = Decimal(str(round((float(total) + 1) ** (1 / years) - 1, 8)))
    drawdown = max_drawdown(values)
    volatility = _std(returns)
    downside = _std(returns, downside=True)
    sharpe = Decimal(0) if volatility == 0 else (sum(returns, Decimal(0)) / Decimal(len(returns))) / volatility * Decimal(sqrt(float(periods)))
    sortino = Decimal(0) if downside == 0 else (sum(returns, Decimal(0)) / Decimal(max(len(returns), 1))) / downside * Decimal(sqrt(float(periods)))
    calmar = Decimal(0) if drawdown == 0 else annualized / drawdown
    pnls = trade_pnls(fills)
    wins = [item for item in pnls if item > 0]
    losses = [item for item in pnls if item < 0]
    win_rate = Decimal(len(wins)) / Decimal(len(pnls)) if pnls else Decimal(0)
    gross_loss = abs(sum(losses, Decimal(0)))
    profit_factor = (sum(wins, Decimal(0)) / gross_loss) if gross_loss else Decimal(0)
    traded = sum((fill.quantity * fill.price for fill in fills), Decimal(0))
    average_equity = sum(values, Decimal(0)) / Decimal(len(values))
    turnover = traded / average_equity if average_equity else Decimal(0)
    exposure = Decimal(exposure_bars) / Decimal(len(values)) if values else Decimal(0)
    return Performance(total, annualized, drawdown, sharpe, sortino, calmar, win_rate, profit_factor, turnover, exposure, len(pnls))


def indicator_stability(calculator, values: list[Decimal], lengths: list[int]) -> list[Decimal]:
    benchmark = calculator(values)[-1]
    result = []
    for length in lengths:
        sample = calculator(values[-length:])[-1]
        if benchmark == 0:
            result.append(abs(sample))
        else:
            result.append(abs(sample - benchmark) / abs(benchmark))
    return result


def step_indicator(values: list[Decimal]) -> list[Decimal]:
    return [Decimal(index) for index, _ in enumerate(values)]


def elapsed_bars(start: datetime, end: datetime, interval: str) -> timedelta:
    periods = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}
    return timedelta(minutes=(end - start).total_seconds() / 60 / periods[interval])
