from app.accounts.directory import UserDirectory, get_directory
from app.config import get_settings
from app.services.platform import Platform, build_platform
from app.store.db import TradingStore


class AccountRegistry:
    def __init__(self, users: UserDirectory | None = None) -> None:
        self.users = users or get_directory()
        self.platforms: dict[str, Platform] = {}
        self.ledger = TradingStore(get_settings().database_url)

    def platform_for(self, username: str) -> Platform:
        if self.users.find(username) is None:
            raise KeyError(username)
        platform = self.platforms.get(username)
        if platform is None:
            platform = build_platform()
            platform.attach_ledger(username, self.ledger)
            self.platforms[username] = platform
        return platform

    def symbols(self) -> list[str]:
        symbols: list[str] = []
        for platform in self.platforms.values():
            for symbol in platform.symbols:
                if symbol not in symbols:
                    symbols.append(symbol)
        return symbols or [get_settings().realtime_symbol.upper()]

    def stream_revision(self) -> int:
        return sum(platform.stream_revision for platform in self.platforms.values())


_registry: AccountRegistry | None = None


def get_registry() -> AccountRegistry:
    global _registry
    if _registry is None:
        _registry = AccountRegistry()
    return _registry
