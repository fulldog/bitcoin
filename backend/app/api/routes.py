from datetime import UTC, datetime

from fastapi import APIRouter

from app.config import get_settings

router = APIRouter()


@router.get("/system/status", tags=["system"])
async def system_status() -> dict[str, object]:
    settings = get_settings()
    return {
        "mode": settings.trading_mode.upper(),
        "live_enabled": settings.live_trading_enabled,
        "runtime": "stopped",
        "connector": "NOT_READY",
        "as_of": datetime.now(UTC).isoformat(),
    }


@router.get("/dashboard/summary", tags=["dashboard"])
async def dashboard_summary() -> dict[str, object]:
    return {
        "mode": get_settings().trading_mode.upper(),
        "equity": "0.00",
        "daily_pnl": "0.00",
        "drawdown": "0.00",
        "open_orders": 0,
        "positions": [],
        "alerts": [],
    }
