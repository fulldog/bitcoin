from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path


@dataclass
class AccountSnapshot:
    cash: Decimal = Decimal(0)
    position: Decimal = Decimal(0)


def save_snapshot(path: Path, account: AccountSnapshot, status: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"cash": str(account.cash), "position": str(account.position), "status": status},
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def load_snapshot(path: Path) -> tuple[AccountSnapshot, str]:
    if not path.exists():
        return AccountSnapshot(), "CREATED"
    data = json.loads(path.read_text(encoding="utf-8"))
    return AccountSnapshot(Decimal(data["cash"]), Decimal(data["position"])), data["status"]
