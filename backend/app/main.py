from fastapi import FastAPI

from app.api.routes import router

app = FastAPI(title="Personal Crypto Quant", version="0.1.0")
app.include_router(router, prefix="/api")


@app.get("/healthz", tags=["system"])
async def healthz() -> dict[str, str]:
    return {"status": "ok", "mode": "paper"}
