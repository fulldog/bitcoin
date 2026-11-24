from decimal import Decimal

import httpx

PORTFOLIO_ID = "5075281354358777856"
NICKNAME = "熬鹰资本"
COPY_LEVERAGE = 1


def _decimal(value: object, default: str = "0") -> Decimal:
    if value is None or value == "":
        return Decimal(default)
    return Decimal(str(value))


def _text(value: object) -> str:
    return "" if value is None else str(value)


def normalize_position(raw: dict) -> dict[str, str]:
    amount = _decimal(raw.get("positionAmount", raw.get("positionAmt", raw.get("size", raw.get("amount")))))
    side = _text(raw.get("side") or raw.get("positionSide")).upper()
    if side in {"", "BOTH"}:
        side = "LONG" if amount >= 0 else "SHORT"
    if side == "BUY":
        side = "LONG"
    if side == "SELL":
        side = "SHORT"
    entry = _decimal(raw.get("entryPrice", raw.get("avgCost")))
    mark = _decimal(raw.get("markPrice"))
    if mark <= 0:
        mark = entry
    isolated = raw.get("isolated", raw.get("marginMode"))
    margin_mode = "ISOLATED" if isolated in {True, "true", "Isolated", "ISOLATED"} else "CROSS"
    return {
        "symbol": _text(raw.get("symbol")).upper(),
        "side": side,
        "size": format(abs(amount), "f"),
        "entry_price": format(entry, "f"),
        "mark_price": format(mark, "f"),
        "leverage": _text(raw.get("leverage")),
        "margin_mode": margin_mode,
        "pnl": _text(raw.get("unrealizedProfit", raw.get("unrealizedPnl"))),
        "roi": _text(raw.get("roi", raw.get("roe"))),
    }


def build_copy_plan(positions: list[dict[str, str]], budget: Decimal) -> list[dict[str, Decimal | str | int]]:
    if budget <= 0:
        raise ValueError("跟单金额必须大于 0")
    if not positions:
        raise ValueError("当前没有可跟的持仓")
    priced: list[tuple[dict[str, str], Decimal, Decimal]] = []
    for item in positions:
        price = Decimal(item["mark_price"])
        size = Decimal(item["size"])
        if price <= 0 or size <= 0:
            raise ValueError(f"{item['symbol']} 缺少有效价格或数量")
        priced.append((item, price, size * price))
    total = sum((notional for _, _, notional in priced), Decimal(0))
    plans: list[dict[str, Decimal | str | int]] = []
    for item, price, notional in priced:
        allocation = (budget * notional / total).quantize(Decimal("0.01"))
        plans.append(
            {
                "symbol": item["symbol"],
                "side": "BUY" if item["side"] == "LONG" else "SELL",
                "quantity": allocation / price,
                "price": price,
                "notional": allocation,
                "leverage": COPY_LEVERAGE,
            }
        )
    return plans


class AoyingMonitor:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self.client = client

    async def snapshot(self) -> dict[str, object]:
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=15, headers=self._headers())
        try:
            detail = await self._object(
                client,
                "GET",
                "/bapi/futures/v1/friendly/future/copy-trade/lead-portfolio/detail",
                params={"portfolioId": PORTFOLIO_ID},
            )
            listed = await self._object(
                client,
                "POST",
                "/bapi/futures/v1/friendly/future/copy-trade/home-page/query-list",
                json={
                    "pageNumber": 1,
                    "pageSize": 20,
                    "timeRange": "30D",
                    "dataType": "ROI",
                    "favoriteOnly": False,
                    "hideFull": False,
                    "nickname": NICKNAME,
                    "order": "DESC",
                    "userAsset": 0,
                    "portfolioType": "ALL",
                },
            )
            positions = await self._items(
                client,
                "GET",
                "/bapi/futures/v1/friendly/future/copy-trade/lead-data/positions",
                params={"portfolioId": PORTFOLIO_ID},
            )
            history = await self._object(
                client,
                "POST",
                "/bapi/futures/v1/friendly/future/copy-trade/lead-portfolio/position-history",
                json={"portfolioId": PORTFOLIO_ID, "pageNumber": 1, "pageSize": 20},
            )
        finally:
            if owns_client:
                await client.aclose()
        rows = listed.get("list", [])
        summary = rows[0] if isinstance(rows, list) and rows and isinstance(rows[0], dict) else {}
        visible = bool(detail.get("positionShow"))
        raw_positions = positions
        return {
            "portfolio_id": PORTFOLIO_ID,
            "nickname": detail.get("nickname") or NICKNAME,
            "description": detail.get("description") or "",
            "status": detail.get("status") or "",
            "avatar_url": detail.get("avatarUrl") or "",
            "profile_url": f"https://www.binance.com/zh-CN/copy-trading/lead-details/{PORTFOLIO_ID}",
            "positions_public": visible,
            "aum": _text(detail.get("aumAmount")),
            "margin_balance": _text(detail.get("marginBalance")),
            "copier_pnl": _text(detail.get("copierPnl")),
            "profit_share": _text(detail.get("profitSharingRate")),
            "copy_count": detail.get("currentCopyCount"),
            "max_copy_count": detail.get("maxCopyCount"),
            "total_copy_count": detail.get("totalCopyCount"),
            "min_copy_usd": detail.get("fixedAmountMinCopyUsd"),
            "sharpe": _text(detail.get("sharpRatio")),
            "roi": _text(summary.get("roi")),
            "pnl": _text(summary.get("pnl")),
            "mdd": _text(summary.get("mdd")),
            "win_rate": _text(summary.get("winRate")),
            "tags": [item.get("tagLangKeyMessage") for item in detail.get("tagItemVos", []) if item.get("tagLangKeyMessage")],
            "positions": [normalize_position(item) for item in raw_positions] if visible else [],
            "history": [self._history_row(item) for item in history.get("list", [])],
        }

    @staticmethod
    def _headers() -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "clienttype": "web",
            "Origin": "https://www.binance.com",
            "Referer": "https://www.binance.com/zh-CN/copy-trading",
            "User-Agent": "Mozilla/5.0",
        }

    async def _object(self, client: httpx.AsyncClient, method: str, path: str, params: dict | None = None, json: dict | None = None) -> dict:
        data = await self._data(client, method, path, params, json)
        return data if isinstance(data, dict) else {}

    async def _items(self, client: httpx.AsyncClient, method: str, path: str, params: dict | None = None) -> list[dict]:
        data = await self._data(client, method, path, params)
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []

    @staticmethod
    async def _data(client: httpx.AsyncClient, method: str, path: str, params: dict | None = None, json: dict | None = None) -> dict | list:
        response = await client.request(method, f"https://www.binance.com{path}", params=params, json=json)
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != "000000":
            raise ValueError(payload.get("message") or "币安公开带单数据不可用")
        data = payload.get("data")
        return {} if data is None else data

    @staticmethod
    def _history_row(item: dict) -> dict[str, str | int]:
        return {
            "symbol": _text(item.get("symbol")),
            "side": _text(item.get("side")),
            "leverage": _text(item.get("leverage")),
            "entry_price": _text(item.get("avgCost")),
            "close_price": _text(item.get("avgClosePrice")),
            "pnl": _text(item.get("closingPnl")),
            "roi": _text(item.get("roi")),
            "opened": int(item.get("opened") or 0),
            "closed": int(item.get("closed") or 0),
            "margin_mode": _text(item.get("isolated")),
        }
