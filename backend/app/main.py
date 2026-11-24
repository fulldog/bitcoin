from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import get_settings

app = FastAPI(title="Personal Crypto Quant", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.include_router(router, prefix="/api")


@app.get("/healthz", tags=["system"])
async def healthz() -> dict[str, str]:
    return {"status": "ok", "mode": get_settings().trading_mode}
