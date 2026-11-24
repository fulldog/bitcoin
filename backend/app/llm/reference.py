from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal

import httpx

from app.domain.models import Bar, OrderIntent


@dataclass(frozen=True, slots=True)
class MarketReference:
    bias: str
    confidence: str
    reason: str
    model: str


def parse_reference(content: str, model: str) -> MarketReference:
    text = content.strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("llm reference is not json") from exc
    bias = str(payload.get("bias", "")).upper()
    if bias not in {"BUY", "SELL", "HOLD"}:
        raise ValueError("llm bias is invalid")
    try:
        confidence = Decimal(str(payload["confidence"]))
    except (KeyError, ArithmeticError, ValueError) as exc:
        raise ValueError("llm confidence is invalid") from exc
    if confidence < 0 or confidence > 1:
        raise ValueError("llm confidence is out of range")
    reason = str(payload.get("reason", "")).strip()[:300]
    if not reason:
        raise ValueError("llm reason is empty")
    return MarketReference(bias, format(confidence, "f"), reason, model)


def aligned_intents(intents: list[OrderIntent], bias: str) -> list[OrderIntent]:
    return [item for item in intents if item.side.value == bias]


class LlmAdvisor:
    def __init__(self, base_url: str, api_key: str, model: str, client: httpx.AsyncClient | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.client = client

    def endpoint(self) -> str:
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        return f"{self.base_url}/chat/completions"

    async def advise(self, symbol: str, bars: list[Bar], position: Decimal, cash: Decimal) -> MarketReference:
        closes = [{"time": bar.open_time.isoformat(), "close": format(bar.close, "f")} for bar in bars[-30:]]
        prompt = {
            "symbol": symbol,
            "position": format(position, "f"),
            "cash": format(cash, "f"),
            "closes": closes,
        }
        body = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": "你是加密货币现货研究员。只输出 JSON，bias 只能是 BUY、SELL 或 HOLD，confidence 是 0 到 1 的小数，reason 是一句中文。这是交易参考，不是下单指令。",
                },
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ],
        }
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=20)
        try:
            response = await client.post(self.endpoint(), json=body, headers={"Authorization": f"Bearer {self.api_key}"})
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        except httpx.TimeoutException as exc:
            raise TimeoutError("llm reference timed out") from exc
        finally:
            if owns_client:
                await client.aclose()
        if not isinstance(content, str):
            raise TypeError("llm reference content is invalid")
        return parse_reference(content, self.model)
