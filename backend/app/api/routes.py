from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from app.accounts.registry import get_registry
from app.adapters.binance_execution import BinanceExecution
from app.adapters.binance_futures import BinanceFutures
from app.config import get_settings
from app.copytrade.aoying import AoyingMonitor, build_copy_plan
from app.data.binance import BinanceMarketData, previous_utc_day
from app.domain.models import Bar
from app.llm.reference import LlmAdvisor
from app.market.quality import INTERVALS, Dataset
from app.security import authenticate, create_token, live_trading_allowed, read_token
from app.services.platform import Platform, _jsonable, contiguous_closed_bars
from app.strategies.base import SmaCrossStrategy

router = APIRouter()
auth_router = APIRouter()
bearer = HTTPBearer(auto_error=False)


def require_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> str:
    if credentials is None:
        raise HTTPException(status_code=401, detail="login required")
    return read_token(credentials.credentials)


def get_platform(username: str = Depends(require_user)) -> Platform:
    try:
        return get_registry().platform_for(username)
    except KeyError as exc:
        raise HTTPException(status_code=401, detail="login required") from exc


class LoginIn(BaseModel):
    username: str
    password: str


@auth_router.post("/auth/login", tags=["auth"])
async def login(body: LoginIn) -> dict[str, str]:
    if not authenticate(body.username, body.password):
        raise HTTPException(status_code=401, detail="invalid username or password")
    return {"access_token": create_token(body.username), "token_type": "bearer"}


@auth_router.get("/auth/me", tags=["auth"])
async def current_user(username: str = Depends(require_user)) -> dict[str, str]:
    account = get_registry().users.find(username)
    if account is None:
        raise HTTPException(status_code=401, detail="login required")
    return {"username": account.username, "role": account.role}


class UserIn(BaseModel):
    username: str
    password: str


@router.get("/users", tags=["auth"])
async def list_users(username: str = Depends(require_user)) -> dict[str, list[dict[str, str]]]:
    directory = get_registry().users
    if not directory.is_admin(username):
        raise HTTPException(status_code=403, detail="只有管理员可以查看用户")
    return {"users": directory.list_public()}


@router.post("/users", tags=["auth"])
async def create_user(
    body: UserIn,
    username: str = Depends(require_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, str]:
    _require_key(idempotency_key)
    directory = get_registry().users
    if not directory.is_admin(username):
        raise HTTPException(status_code=403, detail="只有管理员可以新增用户")
    try:
        account = directory.create(body.username, body.password)
    except ValueError as exc:
        status = 409 if "已存在" in str(exc) else 422
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    get_registry().platform_for(account.username)
    return {"username": account.username, "role": account.role, "created_at": account.created_at}


class BarIn(BaseModel):
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


class DatasetIn(BaseModel):
    dataset_id: str
    bars: list[BarIn]


class CommandIn(BaseModel):
    type: str = Field(pattern="^(pause|kill|unlock_live)$")
    cash: Decimal = Decimal(1000)


class UnlockIn(BaseModel):
    confirmation: str


class CopyIn(BaseModel):
    quote_amount: Decimal = Decimal(100)
    confirmation: str


class LiveOrderIn(BaseModel):
    symbol: str = Field(pattern=r"^[A-Z0-9]{5,20}$")
    side: str = Field(pattern="^(BUY|SELL)$")
    quantity: Decimal
    confirmation: str


def _require_key(idempotency_key: str | None) -> str:
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required")
    return idempotency_key


@router.get("/realtime/status", tags=["market"])
async def realtime_status(platform: Platform = Depends(get_platform)) -> dict:
    return platform.realtime_status()


@router.get("/system/status", tags=["system"])
async def system_status(platform: Platform = Depends(get_platform)) -> dict:
    settings = get_settings()
    health = platform.data_health()
    return {
        "mode": platform.mode,
        "live_enabled": settings.live_trading_enabled and settings.live_build_enabled,
        "runtime": "ready" if platform.kernel and platform.kernel.ready else "stopped",
        "connector": health["connector"],
        "as_of": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/system/metrics", tags=["system"])
async def system_metrics(platform: Platform = Depends(get_platform)) -> dict:
    return platform.metrics


@router.get("/data/health", tags=["market"])
async def data_health(platform: Platform = Depends(get_platform)) -> dict:
    return platform.data_health()


@router.post("/datasets", tags=["market"])
async def import_dataset(
    body: DatasetIn,
    platform: Platform = Depends(get_platform),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    _require_key(idempotency_key)
    bars = [Bar(**item.model_dump()) for item in body.bars]
    return platform.import_bars(body.dataset_id, bars)


@router.post("/backtests", tags=["research"])
async def create_backtest(
    dataset_id: str,
    platform: Platform = Depends(get_platform),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    key = _require_key(idempotency_key)
    if key in platform.idempotency:
        return platform.idempotency[key]
    if dataset_id not in platform.datasets and len(contiguous_closed_bars(platform.live_bars)) < 4:
        settings = get_settings()
        try:
            history = await BinanceMarketData(settings.binance_base_url).fetch_klines(settings.realtime_symbol, settings.realtime_interval, limit=120)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="无法获取 Binance K 线") from exc
        closed = [bar for bar in history if bar.close_time <= datetime.now(timezone.utc)]
        if len(closed) >= 4:
            platform.datasets[dataset_id] = Dataset.freeze(dataset_id, closed)
    try:
        report = platform.run_backtest(dataset_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    platform.idempotency[key] = report
    return report


@router.get("/backtests/{backtest_id}", tags=["research"])
async def get_backtest(backtest_id: str, platform: Platform = Depends(get_platform)) -> dict:
    try:
        return platform.backtests[backtest_id]
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="backtest not found") from exc


class SymbolIn(BaseModel):
    symbol: str


class T1ResearchIn(BaseModel):
    symbol: str = Field(default="BTCUSDT", pattern=r"^[A-Z0-9]{5,20}$")
    interval: str = "1h"


class StrategyRunIn(BaseModel):
    name: str
    symbol: str
    fast: int = 2
    slow: int = 3
    quote_amount: Decimal = Decimal(90)


@router.get("/symbols", tags=["market"])
async def list_symbols(platform: Platform = Depends(get_platform)) -> dict:
    return {"symbols": platform.symbols}


@router.post("/symbols", tags=["market"])
async def create_symbol(
    body: SymbolIn,
    platform: Platform = Depends(get_platform),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    _require_key(idempotency_key)
    try:
        return platform.add_symbol(body.symbol)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/klines", tags=["market"])
async def klines(symbol: str = "BTCUSDT", platform: Platform = Depends(get_platform)) -> dict:
    normalized = symbol.upper()
    if len(platform.klines(normalized)) < 100 and normalized not in platform.history_loaded:
        settings = get_settings()
        try:
            history = await BinanceMarketData(settings.binance_base_url).fetch_klines(
                normalized,
                settings.realtime_interval,
                limit=180,
            )
        except httpx.HTTPError as exc:
            if not platform.klines(normalized):
                raise HTTPException(status_code=502, detail="无法获取 Binance 历史 K 线") from exc
        else:
            closed = [bar for bar in history if bar.close_time <= datetime.now(timezone.utc)]
            platform.cache_history(normalized, closed)
    return {"symbol": normalized, "bars": platform.klines(normalized)}


@router.get("/strategy-runs", tags=["runtime"])
async def strategy_runs(platform: Platform = Depends(get_platform)) -> dict:
    return platform.strategy_runs()


@router.post("/strategy-runs", tags=["runtime"])
async def start_strategy_run(
    body: StrategyRunIn,
    platform: Platform = Depends(get_platform),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    key = _require_key(idempotency_key)
    if key in platform.idempotency:
        return platform.idempotency[key]
    try:
        result = platform.create_strategy(body.name, body.symbol, body.fast, body.slow, body.quote_amount)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    platform.idempotency[key] = result
    return result


@router.post("/strategy-runs/{strategy_id}/start", tags=["runtime"])
async def resume_strategy_run(
    strategy_id: str,
    platform: Platform = Depends(get_platform),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    key = _require_key(idempotency_key)
    if key in platform.idempotency:
        return platform.idempotency[key]
    try:
        result = platform.start_strategy(strategy_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="策略不存在") from exc
    platform.idempotency[key] = result
    return result


@router.post("/strategy-runs/{strategy_id}/stop", tags=["runtime"])
async def stop_strategy_run(
    strategy_id: str,
    platform: Platform = Depends(get_platform),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    key = _require_key(idempotency_key)
    if key in platform.idempotency:
        return platform.idempotency[key]
    runner = platform.runners.get(strategy_id)
    if runner is None:
        raise HTTPException(status_code=404, detail="策略不存在")
    try:
        result = await platform.stop_strategy(_binance() if runner.position_qty > 0 else None, strategy_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="策略不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (TimeoutError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=502, detail="市价卖出失败") from exc
    platform.idempotency[key] = result
    return result


@router.post("/research/t1", tags=["research"])
async def research_previous_day(
    body: T1ResearchIn,
    platform: Platform = Depends(get_platform),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    key = _require_key(idempotency_key)
    if key in platform.idempotency:
        return platform.idempotency[key]
    if body.interval not in INTERVALS:
        raise HTTPException(status_code=422, detail="不支持的周期")
    start, end = previous_utc_day()
    try:
        bars = await BinanceMarketData(get_settings().binance_base_url).fetch_closed_range(body.symbol, body.interval, start, end)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="无法获取昨日 K 线") from exc
    if len(bars) < 4:
        raise HTTPException(status_code=409, detail="昨日闭合 K 线不足")
    dataset_id = f"{body.symbol}-{body.interval}-{start.date().isoformat()}"
    imported = platform.import_bars(dataset_id, bars)
    if not imported["ready"]:
        raise HTTPException(status_code=409, detail="昨日行情不连续，不能回测")
    try:
        report = platform.run_backtest(dataset_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    result = {
        "dataset_id": dataset_id,
        "day": start.date().isoformat(),
        "bars": len(bars),
        "id": report["id"],
        "fill_hash": report["fill_hash"],
        "metrics": report.get("metrics", {}),
    }
    platform.idempotency[key] = result
    return result


@router.get("/strategies", tags=["research"])
async def strategies() -> dict:
    strategy = SmaCrossStrategy()
    return {"strategies": [{"name": strategy.name, "version": strategy.version, "parameters": strategy.parameters()}]}


@router.post("/commands", tags=["runtime"])
async def enqueue_command(
    body: CommandIn,
    platform: Platform = Depends(get_platform),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    key = _require_key(idempotency_key)
    try:
        return platform.enqueue(body.model_dump(), key)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/orders", tags=["runtime"])
async def reject_direct_order(platform: Platform = Depends(get_platform)) -> dict:
    try:
        return platform.enqueue({"type": "place_order", "source": "api"}, "direct-order")
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/runtime/process", tags=["runtime"])
async def process_runtime(
    platform: Platform = Depends(get_platform),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    _require_key(idempotency_key)
    return {"processed": platform.process_commands()}


def _llm() -> LlmAdvisor:
    settings = get_settings()
    if not settings.llm_api_key:
        raise HTTPException(status_code=409, detail="LLM API key is not configured")
    return LlmAdvisor(settings.llm_base_url, settings.llm_api_key, settings.llm_model)


@router.get("/llm/reference", tags=["research"])
async def llm_reference(platform: Platform = Depends(get_platform)) -> dict:
    return {"configured": bool(get_settings().llm_api_key), "reference": platform.llm_reference}


@router.post("/llm/reference", tags=["research"])
async def refresh_llm_reference(
    platform: Platform = Depends(get_platform),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    key = _require_key(idempotency_key)
    if key in platform.idempotency:
        return platform.idempotency[key]
    try:
        result = await platform.refresh_llm_reference(_llm())
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (TimeoutError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=502, detail="LLM reference request failed") from exc
    platform.idempotency[key] = result
    return result


def _binance() -> BinanceExecution:
    settings = get_settings()
    if not settings.binance_api_key or not settings.binance_api_secret:
        raise HTTPException(status_code=409, detail="Binance API key is not configured")
    return BinanceExecution(settings.binance_base_url, settings.binance_api_key, settings.binance_api_secret)


@router.get("/binance/account", tags=["runtime"])
async def binance_account() -> dict:
    try:
        return await _binance().account()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Binance account request failed") from exc


@router.post("/live/orders", tags=["runtime"])
async def place_live_order(
    body: LiveOrderIn,
    platform: Platform = Depends(get_platform),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    key = _require_key(idempotency_key)
    if key in platform.idempotency:
        return platform.idempotency[key]
    settings = get_settings()
    if not live_trading_allowed(settings, body.confirmation, settings.live_build_enabled):
        raise HTTPException(status_code=403, detail="live trading remains locked")
    try:
        result = await platform.submit_live_order(_binance(), body.symbol, body.side, body.quantity)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (ValueError, TimeoutError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Binance order request failed") from exc
    platform.idempotency[key] = result
    return result


@router.post("/live/unlock", tags=["runtime"])
async def unlock_live(
    body: UnlockIn,
    platform: Platform = Depends(get_platform),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    key = _require_key(idempotency_key)
    settings = get_settings()
    allowed = live_trading_allowed(settings, body.confirmation, settings.live_build_enabled)
    result = platform.enqueue({"type": "unlock_live", "allowed": allowed}, key)
    platform.process_commands()
    if not allowed:
        raise HTTPException(status_code=403, detail="live trading remains locked")
    return result


@router.get("/dashboard/summary", tags=["dashboard"])
async def dashboard_summary(platform: Platform = Depends(get_platform)) -> dict:
    summary = platform.summary()
    summary["market_data_max_age_seconds"] = get_settings().market_data_max_age_seconds
    summary["generated_at"] = datetime.now(timezone.utc).isoformat()
    summary["staleness_budget"] = timedelta(seconds=get_settings().market_data_max_age_seconds).total_seconds()
    return summary


@router.get("/orders", tags=["orders"])
async def list_orders(platform: Platform = Depends(get_platform)) -> dict:
    resting = [_jsonable(item.order) for item in platform.kernel.resting] if platform.kernel else []
    return {"orders": platform.live_orders + resting}


@router.get("/fills", tags=["orders"])
async def list_fills(platform: Platform = Depends(get_platform)) -> dict:
    kernel_fills = [_jsonable(fill) for fill in platform.kernel.fills] if platform.kernel else []
    return {"fills": platform.fills + kernel_fills}


@router.get("/risk", tags=["risk"])
async def risk_status(platform: Platform = Depends(get_platform)) -> dict:
    if not platform.kernel:
        return {"kill_switch": False, "ready": False, "data_gap": False, "exposure_ok": platform.exposure_ok, "alerts": platform.alerts, "decisions": []}
    state = platform.kernel.state
    return {
        "kill_switch": state.kill_switch,
        "ready": platform.kernel.ready,
        "data_gap": state.data_gap,
        "exposure_ok": platform.exposure_ok,
        "alerts": platform.alerts,
        "decisions": [_jsonable(item) for item in platform.kernel.decisions],
    }


@router.get("/copy/aoying", tags=["copy"])
async def aoying_monitor() -> dict:
    try:
        return await AoyingMonitor().snapshot()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="无法获取熬鹰公开带单数据") from exc


@router.post("/copy/aoying", tags=["copy"])
async def copy_aoying(
    body: CopyIn,
    platform: Platform = Depends(get_platform),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    key = _require_key(idempotency_key)
    if key in platform.idempotency:
        return platform.idempotency[key]
    settings = get_settings()
    if not live_trading_allowed(settings, body.confirmation, settings.live_build_enabled):
        raise HTTPException(status_code=403, detail="live trading remains locked")
    if platform.killed:
        raise HTTPException(status_code=403, detail="live trading is locked")
    limit = Decimal(str(settings.max_order_notional))
    if body.quote_amount <= 0 or body.quote_amount > limit:
        raise HTTPException(status_code=422, detail=f"跟单金额需要大于 0 且不超过 {limit} USDT")
    if not settings.binance_api_key or not settings.binance_api_secret:
        raise HTTPException(status_code=409, detail="Binance API key is not configured")
    try:
        snapshot = await AoyingMonitor().snapshot()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="无法获取熬鹰公开带单数据") from exc
    if not snapshot["positions_public"]:
        raise HTTPException(status_code=409, detail="带单员未公开当前持仓，不能跟单")
    positions = snapshot["positions"] if isinstance(snapshot["positions"], list) else []
    try:
        plans = build_copy_plan(positions, body.quote_amount)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    futures = BinanceFutures(settings.binance_futures_base_url, settings.binance_api_key, settings.binance_api_secret)
    orders: list[dict[str, str]] = []
    for plan in plans:
        symbol = str(plan["symbol"])
        side = str(plan["side"])
        try:
            await futures.set_leverage(symbol, int(plan["leverage"]))
            orders.append(await futures.market_order(symbol, side, Decimal(str(plan["quantity"]))))
        except (httpx.HTTPError, TimeoutError, ValueError):
            orders.append({"symbol": symbol, "side": side, "status": "FAILED", "reason": "下单失败"})
    result = {"orders": orders, "leverage": 1, "quote_amount": format(body.quote_amount, "f")}
    platform.idempotency[key] = result
    platform.logs.append({"event": "aoying_copy", "type": "copy", "command_id": key})
    return result


@router.get("/logs", tags=["system"])
async def logs(platform: Platform = Depends(get_platform)) -> dict:
    return {"logs": platform.logs, "alerts": platform.alerts}
