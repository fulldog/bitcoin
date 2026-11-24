import hmac
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException

from app.config import Settings, get_settings


def live_trading_allowed(settings: Settings, confirmation: str | None, build_enabled: bool) -> bool:
    return bool(
        build_enabled
        and settings.live_trading_enabled
        and confirmation == settings.live_confirmation_phrase
    )


def _same(left: str, right: str) -> bool:
    raw_left, raw_right = left.encode(), right.encode()
    if len(raw_left) != len(raw_right):
        return False
    return hmac.compare_digest(raw_left, raw_right)


def authenticate(username: str, password: str) -> bool:
    settings = get_settings()
    return _same(username, settings.auth_username) and _same(password, settings.auth_password)


def create_token(username: str) -> str:
    settings = get_settings()
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_ttl_minutes)
    return jwt.encode({"sub": username, "exp": expires}, settings.jwt_secret, algorithm="HS256")


def read_token(token: str) -> str:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="login required") from exc
    subject = payload.get("sub")
    if subject != settings.auth_username:
        raise HTTPException(status_code=401, detail="login required")
    return str(subject)
