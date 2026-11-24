import asyncio
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.accounts.registry import AccountRegistry, get_registry
from app.adapters.binance_execution import BinanceExecution
from app.api.routes import auth_router, require_user, router
from app.config import get_settings
from app.market.stream import run_user_streams


async def reconcile_accounts(registry: AccountRegistry) -> None:
    settings = get_settings()
    if not settings.binance_api_key or not settings.binance_api_secret:
        return
    broker = BinanceExecution(settings.binance_base_url, settings.binance_api_key, settings.binance_api_secret)
    for platform in list(registry.platforms.values()):
        try:
            await platform.reconcile_balances(broker)
        except (OSError, TimeoutError, httpx.HTTPError, ValueError):
            platform._alert("reconcile_failed", "无法连接 Binance 完成对账")


async def reconcile_loop(registry: AccountRegistry) -> None:
    while True:
        await reconcile_accounts(registry)
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    del app
    tasks = []
    if get_settings().realtime_enabled:
        registry = get_registry()
        tasks.append(asyncio.create_task(run_user_streams(registry)))
        tasks.append(asyncio.create_task(reconcile_loop(registry)))
    yield
    for task in tasks:
        task.cancel()


app = FastAPI(title="Personal Crypto Quant", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.include_router(auth_router, prefix="/api")
app.include_router(router, prefix="/api", dependencies=[Depends(require_user)])


@app.get("/healthz", tags=["system"])
async def healthz() -> dict[str, str]:
    return {"status": "ok", "mode": "live"}
