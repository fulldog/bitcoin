import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.domain.models import Bar
from app.market.stream import handle_stream_message
from app.security import authenticate, create_token, read_token
from app.services.platform import Platform


def closed_message(minute: int) -> str:
    opened = datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=minute)
    closed = opened + timedelta(minutes=1)
    payload = {"e": "kline", "k": {"s": "BTCUSDT", "i": "1m", "t": int(opened.timestamp() * 1000), "T": int(closed.timestamp() * 1000), "o": "100", "h": "101", "l": "99", "c": "100.5", "v": "2", "x": True}}
    return json.dumps(payload)


def test_login_accepts_only_the_configured_account():
    assert authenticate("xiongyk", "qwer.1234") is True
    assert authenticate("xiongyk", "wrong") is False
    token = create_token("xiongyk")
    assert read_token(token) == "xiongyk"
    with pytest.raises(HTTPException):
        read_token("not-a-token")


def test_closed_kline_updates_live_analysis():
    platform = Platform()
    assert handle_stream_message(platform, closed_message(0))["accepted"] is True
    forming = closed_message(1).replace("true", "false")
    assert handle_stream_message(platform, forming)["reason"] == "forming"
    assert platform.realtime_status()["closed_bars"] == 1
    assert platform.mode == "LIVE"
    assert platform.kernel is not None
    assert platform.kernel.fills == []
    assert platform.last_price == Decimal("100.5")


def test_bar_contract_stays_timezone_aware():
    platform = Platform()
    handle_stream_message(platform, closed_message(0))
    bar = platform.live_bars[0]
    assert isinstance(bar, Bar)
    assert bar.open_time.tzinfo is not None
