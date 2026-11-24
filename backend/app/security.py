from app.config import Settings


def live_trading_allowed(settings: Settings, confirmation: str | None, build_enabled: bool) -> bool:
    return bool(
        build_enabled
        and settings.live_trading_enabled
        and settings.trading_mode.lower() == "live"
        and confirmation == settings.live_confirmation_phrase
    )
