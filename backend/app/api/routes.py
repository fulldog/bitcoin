from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app.config import get_settings
from app.domain.models import Bar
from app.security import live_trading_allowed
from app.services.platform import Platform, _jsonable, build_platform

router = APIRouter()
_platform = build_platform()


def get_platform() -> Platform:
    return _platform


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
    type: str = Field(pattern="^(start_paper|pause|kill|unlock_live)$")
    cash: Decimal = Decimal(1000)


class UnlockIn(BaseModel):
    confirmation: str


def _require_key(idempotency_key: str | None) -> str:
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required")
    return idempotency_key


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
    try:
        report = platform.run_backtest(dataset_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="dataset not found") from exc
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


@router.get("/strategies", tags=["research"])
async def strategies() -> dict:
    return {"strategies": [{"name": "sma_cross", "version": "1", "parameters": {"fast": 2, "slow": 3, "quote_amount": "100"}}]}


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
    if not platform.kernel:
        return {"orders": []}
    return {"orders": [_jsonable(item.order) for item in platform.kernel.resting]}


@router.get("/fills", tags=["orders"])
async def list_fills(platform: Platform = Depends(get_platform)) -> dict:
    if not platform.kernel:
        return {"fills": []}
    return {"fills": [_jsonable(fill) for fill in platform.kernel.fills]}


@router.get("/risk", tags=["risk"])
async def risk_status(platform: Platform = Depends(get_platform)) -> dict:
    if not platform.kernel:
        return {"kill_switch": False, "ready": False, "decisions": []}
    state = platform.kernel.state
    return {"kill_switch": state.kill_switch, "ready": platform.kernel.ready, "data_gap": state.data_gap, "decisions": [_jsonable(item) for item in platform.kernel.decisions]}


@router.get("/logs", tags=["system"])
async def logs(platform: Platform = Depends(get_platform)) -> dict:
    return {"logs": platform.logs, "alerts": platform.alerts}
