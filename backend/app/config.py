from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "sqlite+aiosqlite:///./quant.db"
    redis_url: str = "redis://localhost:6379/0"
    binance_base_url: str = "https://api.binance.com"
    binance_futures_base_url: str = "https://fapi.binance.com"
    binance_ws_url: str = "wss://stream.testnet.binance.vision/stream"
    binance_api_key: str = ""
    binance_api_secret: str = ""
    live_trading_enabled: bool = False
    live_build_enabled: bool = False
    live_confirmation_phrase: str = "I_UNDERSTAND_LIVE_RISK"
    max_order_notional: float = 100
    max_daily_loss: float = 25
    market_data_max_age_seconds: int = 120
    auth_username: str = "xiongyk"
    auth_password: str = "qwer.1234"
    jwt_secret: str = "dev-only-change-this-secret-to-32b"
    jwt_ttl_minutes: int = 720
    realtime_enabled: bool = True
    realtime_symbol: str = "BTCUSDT"
    realtime_interval: str = "1m"
    binance_stream_url: str = "wss://stream.binance.com:9443/ws"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
