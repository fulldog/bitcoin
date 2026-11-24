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


def authenticate(username: str, password: str) -> bool:
    from app.accounts.directory import get_directory

    return get_directory().verify(username, password)


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
    if not isinstance(subject, str):
        raise HTTPException(status_code=401, detail="login required")
    from app.accounts.directory import get_directory

    if get_directory().find(subject) is None:
        raise HTTPException(status_code=401, detail="login required")
    return subject
