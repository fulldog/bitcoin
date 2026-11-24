from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.backtest.engine import BacktestEngine, lookahead_divergence, walk_forward
from app.domain.filters import SymbolRules
from app.domain.models import Bar, RunManifest, Side
from app.kernel.runtime import TradingKernel
from app.market.quality import Dataset, MarketCursor, backoff_seconds
from app.portfolio.accounting import Portfolio
from app.risk.engine import RiskLimits
from app.security import live_trading_allowed
from app.strategies.base import SmaCrossStrategy


def parse_kline(message: dict) -> Bar:
    candle = message["k"]
    return Bar(
        symbol=candle["s"],
        interval=candle["i"],
        open_time=datetime.fromtimestamp(candle["t"] / 1000, timezone.utc),
        close_time=datetime.fromtimestamp(candle["T"] / 1000, timezone.utc),
        open=Decimal(candle["o"]),
        high=Decimal(candle["h"]),
        low=Decimal(candle["l"]),
        close=Decimal(candle["c"]),
        volume=Decimal(candle["v"]),
        is_closed=bool(candle["x"]),
        source="binance_ws",
    )


class RateLimiter:
    def __init__(self, limit: int, window: timedelta) -> None:
        self.limit = limit
        self.window = window
        self.events: list[datetime] = []

    def allow(self, now: datetime) -> bool:
        self.events = [item for item in self.events if now - item < self.window]
        if len(self.events) >= self.limit:
            return False
        self.events.append(now)
        return True


class Platform:
    def __init__(self) -> None:
        self.datasets: dict[str, Dataset] = {}
        self.backtests: dict[str, dict] = {}
        self.commands: list[dict] = []
        self.idempotency: dict[str, dict] = {}
        self.alerts: list[dict] = []
        self.logs: list[dict] = []
        self.metrics = {"reconnects": 0, "rejects": 0, "reconciliation_diffs": 0, "order_ack_ms": 0, "heartbeat": None}
        self.kernel: TradingKernel | None = None
        self.cursor = MarketCursor()
        self.mode = "PAPER"
        self.live_unlocked = False
        self.rules = SymbolRules("BTCUSDT", Decimal("0.01"), Decimal("0.00001"), Decimal("0.00001"), Decimal(5))

    def data_health(self) -> dict:
        datasets = [
            {"id": item.dataset_id, "digest": item.digest, "ready": item.quality.ready, "issues": item.quality.issues}
            for item in self.datasets.values()
        ]
        return {"connector": "READY" if self.cursor.ready else "NOT_READY", "datasets": datasets, "reconnects": self.cursor.reconnects}

    def import_bars(self, dataset_id: str, bars: list[Bar]) -> dict:
        dataset = Dataset.freeze(dataset_id, bars)
        self.datasets[dataset_id] = dataset
        if dataset.quality.ready and dataset.bars:
            self.cursor.observe(dataset.bars[-1])
        return {"id": dataset.dataset_id, "digest": dataset.digest, "ready": dataset.quality.ready, "issues": dataset.quality.issues}

    def run_backtest(self, dataset_id: str, cash: Decimal = Decimal(1000)) -> dict:
        dataset = self.datasets[dataset_id]
        if not dataset.quality.ready:
            raise ValueError("dataset is not tradable")
        strategy = SmaCrossStrategy()
        manifest = RunManifest(
            strategy.name,
            strategy.version,
            strategy.parameters(),
            f"{dataset.dataset_id}:{dataset.digest}",
            ("BTCUSDT",),
            dataset.bars[0].interval,
            Decimal("0.001"),
            Decimal(1),
        )
        result = BacktestEngine(self.rules, RiskLimits(max_order_notional=Decimal(1000), max_symbol_notional=Decimal(1000), max_gross_notional=Decimal(1000))).run(
            strategy, list(dataset.bars), manifest, cash
        )
        report = _jsonable(
            {
                "id": manifest.fingerprint(),
                "assumptions": result.assumptions,
                "fill_hash": result.fill_hash,
                "metrics": _jsonable(result.metrics),
                "fills": [_jsonable(fill) for fill in result.fills],
                "lookahead_biased": lookahead_divergence(SmaCrossStrategy, list(dataset.bars)),
                "walk_forward": walk_forward(BacktestEngine(self.rules), SmaCrossStrategy, list(dataset.bars), manifest, cash, folds=1) if len(dataset.bars) >= 4 else [],
            }
        )
        self.backtests[report["id"]] = report
        return report

    def enqueue(self, command: dict, idempotency_key: str) -> dict:
        if command.get("type") == "place_order":
            raise PermissionError("control plane cannot place orders directly")
        if idempotency_key in self.idempotency:
            return self.idempotency[idempotency_key]
        self.commands.append(command)
        result = {"accepted": True, "command_id": len(self.commands), "type": command["type"]}
        self.idempotency[idempotency_key] = result
        self.logs.append({"event": "command", **result})
        return result

    def process_commands(self) -> int:
        processed = 0
        while self.commands:
            command = self.commands.pop(0)
            processed += 1
            if command["type"] == "kill":
                if self.kernel:
                    self.kernel.kill()
                self.alerts.append({"severity": "critical", "code": "kill_switch"})
            elif command["type"] == "start_paper":
                self.kernel = TradingKernel(
                    SmaCrossStrategy(),
                    Portfolio(Decimal(command.get("cash", "1000"))),
                    BacktestEngine(self.rules).risk,
                    self.rules,
                    RunManifest("sma_cross", "1", {}, "live-paper", ("BTCUSDT",), "1h", Decimal("0.001"), Decimal(1)),
                )
                self.kernel.update_readiness(True, True)
                self.mode = "PAPER"
            elif command["type"] == "unlock_live":
                self.live_unlocked = bool(command["allowed"])
                self.mode = "LIVE" if self.live_unlocked else self.mode
        self.metrics["heartbeat"] = datetime.now(timezone.utc).isoformat()
        return processed

    def summary(self) -> dict:
        equity = "0.00"
        positions = []
        open_orders = 0
        if self.kernel:
            symbol = "BTCUSDT"
            price = self.kernel.history[-1].close if self.kernel.history else Decimal(0)
            equity = f"{self.kernel.portfolio.equity({symbol: price}):.2f}"
            positions = [_jsonable(position) for position in self.kernel.portfolio.snapshot()]
            open_orders = len([item for item in self.kernel.resting if item.order.status.value not in {"FILLED", "CANCELED", "REJECTED"}])
        return {
            "mode": self.mode,
            "equity": equity,
            "daily_pnl": "0.00",
            "drawdown": "0.00",
            "open_orders": open_orders,
            "positions": _jsonable(positions),
            "alerts": self.alerts,
            "live_unlocked": self.live_unlocked,
            "metrics": self.metrics,
        }


def _jsonable(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Side):
        return value.value
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if hasattr(value, "__dict__") and not isinstance(value, type):
        return {key: _jsonable(item) for key, item in value.__dict__.items()}
    return value


def build_platform() -> Platform:
    return Platform()


__all__ = ["Platform", "RateLimiter", "backoff_seconds", "build_platform", "live_trading_allowed", "parse_kline"]
