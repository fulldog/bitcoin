import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest

from app.domain.models import Bar, OrderIntent, Side
from app.llm.reference import LlmAdvisor, MarketReference, aligned_intents, parse_reference
from app.market.stream import review_with_llm
from app.services.platform import Platform


def test_parse_reference_accepts_fenced_json() -> None:
    reference = parse_reference('```json\n{"bias":"hold","confidence":0.4,"reason":"区间震荡"}\n```', "demo")
    assert reference == MarketReference("HOLD", "0.4", "区间震荡", "demo")


def test_parse_reference_rejects_unknown_bias() -> None:
    with pytest.raises(ValueError, match="bias"):
        parse_reference('{"bias":"LONG","confidence":0.4,"reason":"无效"}', "demo")


def test_aligned_intents_keep_only_matching_side() -> None:
    buy = OrderIntent("BTCUSDT", Side.BUY, Decimal("0.001"))
    sell = OrderIntent("BTCUSDT", Side.SELL, Decimal("0.001"))
    assert aligned_intents([buy, sell], "BUY") == [buy]


def bar() -> Bar:
    opened = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return Bar("BTCUSDT", "1m", opened, opened + timedelta(minutes=1), Decimal(100), Decimal(101), Decimal(99), Decimal(100), Decimal(1))


class FakeAdvisor:
    def __init__(self, bias: str) -> None:
        self.bias = bias

    async def advise(self, symbol: str, bars: list[Bar], position: Decimal, cash: Decimal) -> MarketReference:
        assert symbol == "BTCUSDT"
        assert bars
        return MarketReference(self.bias, "0.8", "测试参考", "fake")


@pytest.mark.asyncio
async def test_reference_blocks_automatic_order_when_direction_differs() -> None:
    platform = Platform()
    platform.live_bars = [bar()]
    platform.pending = [OrderIntent("BTCUSDT", Side.BUY, Decimal("0.001"))]
    allowed = await review_with_llm(platform, FakeAdvisor("HOLD"))
    assert allowed is False
    assert platform.pending == []
    assert platform.llm_reference is not None
    assert platform.llm_reference["bias"] == "HOLD"
    assert platform.metrics["last_decision"] == "llm_reference_blocked"


@pytest.mark.asyncio
async def test_advisor_posts_market_summary_without_secrets() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer secret"
        assert request.url.path == "/v1/chat/completions"
        payload = json.loads(request.content)
        assert payload["model"] == "demo"
        assert "secret" not in payload["messages"][1]["content"]
        content = '{"bias":"BUY","confidence":0.7,"reason":"短线偏多"}'
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    advisor = LlmAdvisor("https://example.test/v1", "secret", "demo", client)
    reference = await advisor.advise("BTCUSDT", [bar()], Decimal(0), Decimal(0))
    assert reference.bias == "BUY"
    assert reference.confidence == "0.7"
    await client.aclose()
