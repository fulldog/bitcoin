import re
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import httpx

from app.backtest.engine import BacktestEngine, lookahead_divergence, walk_forward
from app.config import get_settings
from app.domain.filters import SymbolRules
from app.domain.models import Bar, OrderIntent, RunManifest, Side
from app.kernel.runtime import TradingKernel
from app.market.quality import INTERVALS, Dataset, MarketCursor, backoff_seconds
from app.portfolio.accounting import Portfolio
from app.risk.engine import RiskEngine, RiskLimits, RiskState
from app.security import live_trading_allowed
from app.strategies.base import SmaCrossStrategy, StrategyContext


def contiguous_closed_bars(bars: list[Bar]) -> list[Bar]:
    closed = [bar for bar in bars if bar.is_closed]
    if not closed:
        return []
    tail = [closed[-1]]
    for bar in reversed(closed[:-1]):
        step = INTERVALS.get(bar.interval)
        same_series = bar.symbol == tail[0].symbol and bar.interval == tail[0].interval
        if step is None or not same_series or bar.open_time + step != tail[0].open_time:
            break
        tail.insert(0, bar)
    return tail


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


@dataclass
class PendingSignal:
    intent: OrderIntent
    strategy_id: str


def pending_intent(item: PendingSignal | OrderIntent) -> OrderIntent:
    if isinstance(item, PendingSignal):
        return item.intent
    return item


@dataclass
class StrategyRunner:
    id: str
    name: str
    symbol: str
    strategy: SmaCrossStrategy
    position_qty: Decimal = Decimal(0)
    cash: Decimal = Decimal(0)
    entry_price: Decimal | None = None
    history: list[Bar] = field(default_factory=list)
    last_decision: str = ""
    signal_count: int = 0
    status: str = "running"
    created_at: str = ""

    def public(self, price: Decimal) -> dict[str, str | int]:
        return {
            "id": self.id,
            "name": self.name,
            "symbol": self.symbol,
            "status": self.status,
            "last_decision": self.last_decision or "等待信号",
            "signal_count": self.signal_count,
            "position": format(self.position_qty, "f"),
            "price": format(price, "f"),
            "created_at": self.created_at,
            "fast": self.strategy.fast,
            "slow": self.strategy.slow,
            "quote_amount": str(self.strategy.quote_amount),
        }


class Platform:
    def __init__(self) -> None:
        self.datasets: dict[str, Dataset] = {}
        self.backtests: dict[str, dict] = {}
        self.commands: list[dict] = []
        self.idempotency: dict[str, dict] = {}
        self.alerts: list[dict] = []
        self.logs: list[dict] = []
        self.metrics: dict[str, object] = {"reconnects": 0, "rejects": 0, "reconciliation_diffs": 0, "order_ack_ms": 0, "heartbeat": None}
        self.kernel: TradingKernel | None = None
        self.cursor = MarketCursor()
        self.mode = "LIVE"
        self.pending: list[PendingSignal | OrderIntent] = []
        self.symbols = [get_settings().realtime_symbol.upper()]
        self.stream_revision = 0
        self.bars_by_symbol: dict[str, list[Bar]] = {}
        self.history_loaded: set[str] = set()
        self.forming: dict[str, Bar] = {}
        self.prices: dict[str, Decimal] = {}
        self.runners: dict[str, StrategyRunner] = {}
        self.llm_reference: dict[str, str] | None = None
        self.live_unlocked = False
        self.killed = False
        self.live_orders: list[dict] = []
        self.fills: list[dict] = []
        self.owner = ""
        self.ledger = None
        self.exposure_ok = True
        self.rules = SymbolRules("BTCUSDT", Decimal("0.01"), Decimal("0.00001"), Decimal("0.00001"), Decimal(5))
        self.live_bars: list[Bar] = []
        self.last_price = Decimal(0)

    def ensure_live(self) -> None:
        if self.kernel is not None:
            return
        self.kernel = TradingKernel(
            SmaCrossStrategy(),
            Portfolio(Decimal(0)),
            BacktestEngine(self.rules).risk,
            self.rules,
            RunManifest("sma_cross", "1", {}, "live", ("BTCUSDT",), "1m", Decimal("0.001"), Decimal(1)),
        )
        self.kernel.update_readiness(True, True)
        self.mode = "LIVE"

    def ingest_live_bar(self, bar: Bar) -> dict:
        self.last_price = bar.close
        self.prices[bar.symbol] = bar.close
        self.metrics["last_price"] = str(bar.close)
        self.metrics["last_symbol"] = bar.symbol
        if not bar.is_closed:
            self.forming[bar.symbol] = bar
            return {"accepted": False, "reason": "forming"}
        self.forming.pop(bar.symbol, None)
        bucket = self.bars_by_symbol.setdefault(bar.symbol, [])
        bucket.append(bar)
        self.bars_by_symbol[bar.symbol] = bucket[-500:]
        self.cursor.observe(bar)
        self.live_bars.append(bar)
        self.live_bars = self.live_bars[-500:]
        self.ensure_live()
        assert self.kernel is not None
        self.kernel.update_readiness(self.cursor.ready, True, data_gap=not self.cursor.ready)
        intents = [] if self.killed else self._run_strategies(bar)
        decision = pending_intent(self.pending[-1]).client_order_id if self.pending and intents else ""
        self.metrics["closed_bars"] = len(self.live_bars)
        self.metrics["last_decision"] = decision
        self.metrics["pending_orders"] = len(self.pending)
        return {"accepted": self.cursor.ready, "signals": len(intents), "decision": decision}

    def add_symbol(self, symbol: str) -> dict[str, list[str]]:
        normalized = symbol.upper()
        if re.fullmatch(r"[A-Z0-9]{5,20}", normalized) is None:
            raise ValueError("币种格式无效")
        if normalized not in self.symbols:
            self.symbols.append(normalized)
            self.stream_revision += 1
        return {"symbols": self.symbols}

    def cache_history(self, symbol: str, bars: list[Bar]) -> None:
        normalized = symbol.upper()
        if not bars:
            return
        existing = {bar.open_time: bar for bar in self.bars_by_symbol.get(normalized, [])}
        existing.update({bar.open_time: bar for bar in bars if bar.symbol == normalized})
        ordered = sorted(existing.values(), key=lambda bar: bar.open_time)
        self.bars_by_symbol[normalized] = ordered[-500:]
        self.prices[normalized] = self.bars_by_symbol[normalized][-1].close
        self.history_loaded.add(normalized)

    def create_strategy(self, name: str, symbol: str, fast: int, slow: int, quote_amount: Decimal) -> dict[str, str | int]:
        cleaned = name.strip()
        if not cleaned or len(cleaned) > 40:
            raise ValueError("策略名称需要 1 到 40 个字符")
        if fast >= slow or fast < 1 or slow > 200:
            raise ValueError("快线必须短于慢线")
        if quote_amount <= 0:
            raise ValueError("买入金额必须大于 0")
        self.add_symbol(symbol)
        runner = StrategyRunner(
            id=uuid4().hex[:8],
            name=cleaned,
            symbol=symbol.upper(),
            strategy=SmaCrossStrategy(fast, slow, quote_amount),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.runners[runner.id] = runner
        self.logs.append({"event": "strategy_started", "type": runner.symbol, "command_id": runner.id})
        self._persist_runner(runner)
        return runner.public(self.prices.get(runner.symbol, Decimal(0)))

    def strategy_runs(self) -> dict[str, object]:
        runs = [runner.public(self.prices.get(runner.symbol, Decimal(0))) for runner in self.runners.values()]
        running = len([runner for runner in self.runners.values() if runner.status == "running"])
        return {"runs": runs, "symbols": self.symbols, "running": running}

    def start_strategy(self, strategy_id: str) -> dict[str, str | int]:
        runner = self.runners.get(strategy_id)
        if runner is None:
            raise KeyError(strategy_id)
        runner.status = "running"
        runner.last_decision = "已启动"
        self.logs.append({"event": "strategy_started", "type": runner.symbol, "command_id": runner.id})
        self._persist_runner(runner)
        return runner.public(self.prices.get(runner.symbol, Decimal(0)))

    async def stop_strategy(self, broker, strategy_id: str) -> dict[str, object]:
        runner = self.runners.get(strategy_id)
        if runner is None:
            raise KeyError(strategy_id)
        if runner.status != "running":
            raise ValueError("策略已经关闭")
        order = None
        if runner.position_qty > 0:
            if broker is None:
                raise ValueError("缺少交易所连接，不能市价卖出")
            price = self.prices.get(runner.symbol, Decimal(0))
            if price <= 0:
                raise ValueError("缺少当前价格，不能市价卖出")
            order = await self.submit_live_order(broker, runner.symbol, "SELL", runner.position_qty, "strategy_stop", runner.id)
            if runner.position_qty > 0:
                raise ValueError("持仓未全部卖出，策略保持运行")
        self.pending = [item for item in self.pending if not (isinstance(item, PendingSignal) and item.strategy_id == runner.id)]
        runner.status = "stopped"
        runner.last_decision = "已关闭并卖出" if order else "已关闭"
        self.logs.append({"event": "strategy_stopped", "type": runner.symbol, "command_id": runner.id})
        self._persist_runner(runner)
        return {"strategy": runner.public(self.prices.get(runner.symbol, Decimal(0))), "order": order}

    def klines(self, symbol: str) -> list[dict[str, str | int]]:
        normalized = symbol.upper()
        bars = list(self.bars_by_symbol.get(normalized, []))
        forming = self.forming.get(normalized)
        if forming is not None:
            bars.append(forming)
        return [
            {
                "time": int(bar.open_time.timestamp()),
                "open": format(bar.open, "f"),
                "high": format(bar.high, "f"),
                "low": format(bar.low, "f"),
                "close": format(bar.close, "f"),
                "volume": format(bar.volume, "f"),
            }
            for bar in bars[-180:]
        ]

    def _run_strategies(self, bar: Bar) -> list[OrderIntent]:
        produced: list[OrderIntent] = []
        for runner in self.runners.values():
            if runner.symbol != bar.symbol or runner.status != "running":
                continue
            runner.history.append(bar)
            runner.history = runner.history[-500:]
            context = StrategyContext(runner.history, runner.position_qty, runner.cash, runner.entry_price)
            intents = runner.strategy.on_bar(context, bar)
            for intent in intents:
                self.pending.append(PendingSignal(intent, runner.id))
                runner.signal_count += 1
                runner.last_decision = intent.client_order_id or "signal"
            produced.extend(intents)
        self.pending = self.pending[-20:]
        return produced

    def _apply_runner_fill(self, strategy_id: str, side: str, quantity: Decimal, price: Decimal) -> None:
        runner = self.runners.get(strategy_id)
        if runner is None or quantity <= 0:
            return
        fill_price = price if price > 0 else self.prices.get(runner.symbol, self.last_price)
        if side == "BUY":
            runner.position_qty += quantity
            runner.entry_price = fill_price
            runner.cash = max(Decimal(0), runner.cash - quantity * fill_price)
            self._persist_runner(runner)
            return
        runner.position_qty = max(Decimal(0), runner.position_qty - quantity)
        runner.cash += quantity * fill_price
        if runner.position_qty == 0:
            runner.entry_price = None
        self._persist_runner(runner)

    def realtime_status(self) -> dict:
        latest = self.live_bars[-1] if self.live_bars else None
        return {
            "stream": self.metrics.get("stream", "stopped"),
            "symbol": self.metrics.get("last_symbol", "BTCUSDT"),
            "price": str(self.last_price),
            "closed_bars": len(self.live_bars),
            "connector": "READY" if self.cursor.ready else "NOT_READY",
            "reconnects": self.cursor.reconnects,
            "last_open_time": latest.open_time.isoformat() if latest else None,
            "last_decision": self.metrics.get("last_decision", ""),
            "llm_configured": bool(get_settings().llm_api_key),
            "llm_bias": (self.llm_reference or {}).get("bias", ""),
            "llm_confidence": (self.llm_reference or {}).get("confidence", ""),
            "llm_reason": (self.llm_reference or {}).get("reason", ""),
            "llm_model": (self.llm_reference or {}).get("model", ""),
        }

    async def refresh_llm_reference(self, advisor) -> dict[str, str]:
        closed = [bar for bar in self.live_bars if bar.is_closed]
        if not closed:
            raise ValueError("llm reference requires closed bars")
        latest = closed[-1]
        position = self.kernel.portfolio.position(latest.symbol) if self.kernel else Decimal(0)
        cash = self.kernel.portfolio.cash if self.kernel else Decimal(0)
        reference = await advisor.advise(latest.symbol, closed[-30:], position, cash)
        stored = {"bias": reference.bias, "confidence": reference.confidence, "reason": reference.reason, "model": reference.model}
        self.llm_reference = stored
        self.metrics["llm_bias"] = reference.bias
        return stored

    def data_health(self) -> dict:
        datasets = [
            {"id": item.dataset_id, "digest": item.digest, "ready": item.quality.ready, "issues": item.quality.issues}
            for item in self.datasets.values()
        ]
        return {"connector": "READY" if self.cursor.ready else "NOT_READY", "datasets": datasets, "reconnects": self.cursor.reconnects}

    def attach_ledger(self, username: str, store) -> None:
        self.owner = username
        self.ledger = store
        for row in store.strategies(username):
            runner = StrategyRunner(
                id=row.strategy_id,
                name=row.name,
                symbol=row.symbol,
                strategy=SmaCrossStrategy(row.fast, row.slow, Decimal(row.quote_amount)),
                position_qty=Decimal(row.position_qty),
                cash=Decimal(row.cash or "0"),
                entry_price=Decimal(row.entry_price) if row.entry_price else None,
                last_decision=row.last_decision,
                signal_count=row.signal_count,
                status=row.status,
                created_at=row.created_at,
            )
            self.runners[runner.id] = runner
            if runner.symbol not in self.symbols:
                self.symbols.append(runner.symbol)
        self.live_orders = store.orders(username)
        self.fills = store.fills(username)
        if len(self.symbols) > 1:
            self.stream_revision += 1

    def _runner_payload(self, runner: StrategyRunner) -> dict[str, str | int]:
        return {
            "id": runner.id,
            "name": runner.name,
            "symbol": runner.symbol,
            "fast": runner.strategy.fast,
            "slow": runner.strategy.slow,
            "quote_amount": str(runner.strategy.quote_amount),
            "status": runner.status,
            "position_qty": format(runner.position_qty, "f"),
            "cash": format(runner.cash, "f"),
            "entry_price": "" if runner.entry_price is None else format(runner.entry_price, "f"),
            "last_decision": runner.last_decision,
            "signal_count": runner.signal_count,
            "created_at": runner.created_at,
        }

    def _persist_runner(self, runner: StrategyRunner) -> None:
        if self.ledger is None or not self.owner:
            return
        self.ledger.save_strategy(self.owner, self._runner_payload(runner))

    def _persist_order(self, payload: dict) -> None:
        if self.ledger is None or not self.owner:
            return
        self.ledger.save_order(self.owner, payload)

    def _persist_fill(self, payload: dict) -> None:
        if self.ledger is None or not self.owner:
            return
        self.ledger.save_fill(self.owner, payload)
        self.fills.append(payload)

    def _alert(self, code: str, message: str) -> None:
        if any(item.get("code") == code for item in self.alerts):
            return
        self.alerts.append({"code": code, "severity": "warning", "message": message})

    async def reconcile_balances(self, broker) -> dict:
        account = await broker.account()
        balances = {
            item["asset"]: Decimal(item["free"]) + Decimal(item["locked"])
            for item in account["balances"]
        }
        held: dict[str, Decimal] = {}
        for runner in self.runners.values():
            held[runner.symbol] = held.get(runner.symbol, Decimal(0)) + runner.position_qty
        diffs = []
        for symbol, quantity in held.items():
            if quantity <= 0:
                continue
            base = symbol.removesuffix("USDT").removesuffix("USDC").removesuffix("FDUSD")
            exchange = balances.get(base, Decimal(0))
            if quantity > exchange:
                diffs.append({"symbol": symbol, "local": format(quantity, "f"), "exchange": format(exchange, "f")})
        self.exposure_ok = not diffs
        self.metrics["reconciliation_diffs"] = len(diffs)
        if diffs:
            self._alert("position_mismatch", "本地持仓多于交易所余额，已禁止开仓")
        else:
            self.alerts = [item for item in self.alerts if item.get("code") != "position_mismatch"]
        return {"ok": self.exposure_ok, "diffs": diffs, "balances": _jsonable(balances)}

    def import_bars(self, dataset_id: str, bars: list[Bar]) -> dict:
        dataset = Dataset.freeze(dataset_id, bars)
        self.datasets[dataset_id] = dataset
        if dataset.quality.ready and dataset.bars:
            self.cursor.observe(dataset.bars[-1])
        return {"id": dataset.dataset_id, "digest": dataset.digest, "ready": dataset.quality.ready, "issues": dataset.quality.issues}

    def dataset_for_backtest(self, dataset_id: str) -> Dataset:
        existing = self.datasets.get(dataset_id)
        if existing is not None:
            return existing
        bars = contiguous_closed_bars(self.live_bars)
        if len(bars) < 4:
            raise ValueError("至少需要 4 根连续闭合 K 线才能回测")
        dataset = Dataset.freeze(dataset_id, bars)
        self.datasets[dataset_id] = dataset
        return dataset

    def run_backtest(self, dataset_id: str, cash: Decimal = Decimal(1000)) -> dict:
        dataset = self.dataset_for_backtest(dataset_id)
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

    async def submit_live_order(self, broker, symbol: str, side: str, quantity: Decimal, reason: str = "", strategy_id: str = "") -> dict:
        if self.killed or not self.live_unlocked:
            raise PermissionError("live trading is locked")
        if side.upper() == "BUY" and not self.exposure_ok:
            raise PermissionError("持仓与交易所不一致，已禁止开仓")
        price = self.prices.get(symbol.upper(), self.last_price)
        if price <= 0:
            raise ValueError("live order requires a current market price")
        intent = OrderIntent(symbol.upper(), Side(side.upper()), quantity, client_order_id=f"live{uuid4().hex[:20]}")
        if self.kernel is not None:
            account = await broker.account()
            quote = sum(
                (Decimal(item["free"]) for item in account["balances"] if item["asset"] in {"USDT", "USDC", "FDUSD"}),
                Decimal(0),
            )
            self.kernel.portfolio.cash = quote
            base = symbol.upper().removesuffix("USDT").removesuffix("USDC").removesuffix("FDUSD")
            for item in account["balances"]:
                if item["asset"] == base:
                    self.kernel.portfolio.positions[symbol.upper()] = Decimal(item["free"])
            equity = self.kernel.portfolio.equity({symbol.upper(): price})
            self.kernel.state.day_start_equity = equity
            self.kernel.state.peak_equity = max(self.kernel.state.peak_equity, equity)
            self.kernel.update_readiness(True, True)
        portfolio = self.kernel.portfolio if self.kernel else Portfolio(price * quantity * 2)
        equity = portfolio.equity({symbol.upper(): price})
        state = self.kernel.state if self.kernel else RiskState(connector_ready=True, reconciled=True, day_start_equity=equity, peak_equity=equity)
        decision = RiskEngine(RiskLimits()).evaluate(
            intent, portfolio, self.rules, state, datetime.now(timezone.utc), datetime.now(timezone.utc), price, equity
        )
        if not decision.allowed:
            raise PermissionError(decision.message)
        stored = {
            "symbol": intent.symbol,
            "order_id": "",
            "client_order_id": intent.client_order_id,
            "status": "CREATED",
            "executed_quantity": "0",
            "average_price": "0",
            "reason": reason,
            "side": intent.side.value,
            "quantity": format(intent.quantity, "f"),
            "strategy_id": strategy_id,
        }
        self.live_orders.append(stored)
        self._persist_order(stored)
        try:
            report = await broker.place_order(intent.symbol, intent.side.value, intent.quantity, intent.client_order_id or "")
        except TimeoutError:
            stored["status"] = "UNKNOWN"
            self._persist_order(stored)
            report = await broker.query_order(intent.symbol, intent.client_order_id or "")
        except (httpx.HTTPError, OSError):
            stored["status"] = "FAILED"
            self._persist_order(stored)
            raise
        stored.update(
            {
                "symbol": report.symbol,
                "order_id": report.order_id,
                "client_order_id": report.client_order_id,
                "status": report.status,
                "executed_quantity": format(report.executed_quantity, "f"),
                "average_price": format(report.average_price, "f"),
            }
        )
        self._apply_live_fill(intent.symbol, intent.side.value, report.executed_quantity, report.average_price)
        self._apply_runner_fill(strategy_id, intent.side.value, report.executed_quantity, report.average_price)
        self._persist_order(stored)
        if report.executed_quantity > 0:
            self._persist_fill(
                {
                    "strategy_id": strategy_id,
                    "symbol": intent.symbol,
                    "side": intent.side.value,
                    "quantity": format(report.executed_quantity, "f"),
                    "price": format(report.average_price, "f"),
                    "client_order_id": stored["client_order_id"],
                }
            )
        self.mode = "LIVE"
        return stored

    def _apply_live_fill(self, symbol: str, side: str, quantity: Decimal, price: Decimal) -> None:
        if self.kernel is None or quantity <= 0:
            return
        fill_price = price if price > 0 else self.last_price
        portfolio = self.kernel.portfolio
        if side == "BUY":
            portfolio.positions[symbol] = portfolio.position(symbol) + quantity
            portfolio.average_prices[symbol] = fill_price
            portfolio.cash = max(Decimal(0), portfolio.cash - quantity * fill_price)
            return
        portfolio.positions[symbol] = max(Decimal(0), portfolio.position(symbol) - quantity)
        portfolio.cash += quantity * fill_price
        if portfolio.position(symbol) == 0:
            portfolio.average_prices.pop(symbol, None)

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
                self.killed = True
                if self.kernel:
                    self.kernel.kill()
                self.alerts.append({"severity": "critical", "code": "kill_switch"})
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
