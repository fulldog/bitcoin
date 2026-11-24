import os

from app.store.db import TradingStore


def upgrade(url: str | None = None) -> None:
    TradingStore(url or os.environ.get("DATABASE_URL", "sqlite:///./quant.db"))


if __name__ == "__main__":
    upgrade()
