"""Trading runtime entry point with a safe paper-mode default."""

import asyncio

from app.config import get_settings


async def main() -> None:
    settings = get_settings()
    if settings.trading_mode.lower() == "live" and not settings.live_trading_enabled:
        raise RuntimeError("Live trading is disabled by configuration")
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
