import asyncio
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth_router, get_platform, require_user, router
from app.config import get_settings
from app.market.stream import run_market_stream


@asynccontextmanager
async def lifespan(app: FastAPI):
    del app
    task = None
    if get_settings().realtime_enabled:
        task = asyncio.create_task(run_market_stream(get_platform()))
    yield
    if task is not None:
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
