import asyncio
import json

import httpx
import websockets

from app.adapters.binance_execution import BinanceExecution
from app.config import get_settings
from app.llm.reference import LlmAdvisor, aligned_intents
from app.market.quality import backoff_seconds
from app.services.platform import PendingSignal, Platform, parse_kline, pending_intent


def stream_url(symbols: list[str] | None = None) -> str:
    settings = get_settings()
    interval = settings.realtime_interval
    chosen = symbols or [settings.realtime_symbol.upper()]
    base = settings.binance_stream_url.rstrip("/")
    if len(chosen) == 1:
        return f"{base}/{chosen[0].lower()}@kline_{interval}"
    combined = base[:-3] + "/stream" if base.endswith("/ws") else base
    query = "/".join(f"{symbol.lower()}@kline_{interval}" for symbol in chosen)
    return f"{combined}?streams={query}"


def handle_stream_message(platform: Platform, raw: str) -> dict | None:
    message = json.loads(raw)
    if "data" in message:
        message = message["data"]
    if message.get("e") != "kline":
        return None
    return platform.ingest_live_bar(parse_kline(message))


async def review_with_llm(platform: Platform, advisor: LlmAdvisor | None = None) -> bool:
    settings = get_settings()
    active = advisor
    if active is None:
        if not settings.llm_api_key:
            return True
        active = LlmAdvisor(settings.llm_base_url, settings.llm_api_key, settings.llm_model)
    if not platform.pending:
        return False
    try:
        reference = await platform.refresh_llm_reference(active)
    except (ValueError, TypeError, TimeoutError, OSError, httpx.HTTPError, KeyError) as exc:
        platform.metrics["last_decision"] = "llm_reference_unavailable"
        platform.logs.append({"event": "llm_reference", "error": str(exc)[:200]})
        return False
    intents = [pending_intent(item) for item in platform.pending]
    kept = aligned_intents(intents, reference["bias"])
    if not kept:
        platform.pending.clear()
        platform.metrics["last_decision"] = "llm_reference_blocked"
        return False
    kept_ids = {id(item) for item in kept}
    platform.pending = [item for item in platform.pending if id(pending_intent(item)) in kept_ids]
    return True


async def flush_pending(platform: Platform) -> None:
    settings = get_settings()
    if not platform.live_unlocked or not platform.pending or not settings.binance_api_key or not settings.binance_api_secret:
        return
    if not await review_with_llm(platform):
        return
    broker = BinanceExecution(settings.binance_base_url, settings.binance_api_key, settings.binance_api_secret)
    pending = list(platform.pending)
    platform.pending.clear()
    for item in pending:
        intent = pending_intent(item)
        strategy_id = item.strategy_id if isinstance(item, PendingSignal) else ""
        try:
            await platform.submit_live_order(broker, intent.symbol, intent.side.value, intent.quantity, intent.client_order_id or "", strategy_id)
        except (PermissionError, ValueError, TimeoutError, OSError, httpx.HTTPError) as exc:
            platform.pending.append(item)
            platform.metrics["last_decision"] = str(exc)
            rejects = platform.metrics.get("rejects", 0)
            platform.metrics["rejects"] = rejects + 1 if isinstance(rejects, int) else 1


async def run_market_stream(platform: Platform) -> None:
    attempt = 0
    while True:
        try:
            revision = platform.stream_revision
            async with websockets.connect(stream_url(platform.symbols), ping_interval=20, ping_timeout=20) as socket:
                attempt = 0
                platform.metrics["stream"] = "connected"
                async for raw in socket:
                    if platform.stream_revision != revision:
                        break
                    text = raw.decode() if isinstance(raw, bytes) else raw
                    handle_stream_message(platform, text)
                    await flush_pending(platform)
        except asyncio.CancelledError:
            platform.metrics["stream"] = "stopped"
            raise
        except (OSError, TimeoutError, websockets.WebSocketException):  # network failures reconnect
            attempt += 1
            platform.cursor.disconnect()
            platform.metrics["stream"] = "reconnecting"
            platform.metrics["reconnects"] = platform.cursor.reconnects
            await asyncio.sleep(backoff_seconds(attempt))
