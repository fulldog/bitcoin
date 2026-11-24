from decimal import Decimal

from fastapi.testclient import TestClient

from app.accounts.directory import UserDirectory
from app.accounts.registry import AccountRegistry
from app.main import app
from app.security import create_token

client = TestClient(app)


def test_each_user_keeps_an_independent_platform() -> None:
    directory = UserDirectory("sqlite+pysqlite:///:memory:")
    directory.create("alice", "password1")
    directory.create("bob", "password2")
    registry = AccountRegistry(directory)
    alice = registry.platform_for("alice")
    bob = registry.platform_for("bob")
    alice.create_strategy("爱丽丝策略", "ETHUSDT", 2, 3, Decimal(20))
    assert alice.strategy_runs()["running"] == 1
    assert bob.strategy_runs()["runs"] == []
    assert registry.symbols() == ["BTCUSDT", "ETHUSDT"]


def test_admin_can_create_a_user_that_cannot_see_admin_data() -> None:
    admin = {"Authorization": f"Bearer {create_token('xiongyk')}"}
    created = client.post("/api/users", headers={**admin, "Idempotency-Key": "create-carol"}, json={"username": "carol", "password": "password3"})
    assert created.status_code == 200
    admin_strategy = client.post(
        "/api/strategy-runs",
        headers={**admin, "Idempotency-Key": "admin-strategy"},
        json={"name": "管理员策略", "symbol": "BTCUSDT", "fast": 2, "slow": 3, "quote_amount": "10"},
    )
    assert admin_strategy.status_code == 200
    login = client.post("/api/auth/login", json={"username": "carol", "password": "password3"})
    carol = {"Authorization": f"Bearer {login.json()['access_token']}"}
    runs = client.get("/api/strategy-runs", headers=carol)
    assert runs.status_code == 200
    assert runs.json()["runs"] == []
    forbidden = client.get("/api/users", headers=carol)
    assert forbidden.status_code == 403
