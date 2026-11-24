import json
import logging

SECRET_FIELDS = {"api_key", "secret", "binance_api_key", "binance_api_secret", "authorization"}


def sanitize(payload: dict) -> dict:
    return {key: "***" if key.lower() in SECRET_FIELDS else value for key, value in payload.items()}


def log_event(logger: logging.Logger, event: str, **fields: object) -> None:
    logger.info(json.dumps({"event": event, **sanitize(fields)}, default=str, sort_keys=True))
