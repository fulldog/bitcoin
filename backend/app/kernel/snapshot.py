from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from app.execution.paper import PaperAccount


def save_snapshot(path: Path, account: PaperAccount, status: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"cash": str(account.cash), "position": str(account.position), "status": status},
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def load_snapshot(path: Path) -> tuple[PaperAccount, str]:
    if not path.exists():
        return PaperAccount(), "CREATED"
    data = json.loads(path.read_text(encoding="utf-8"))
    return PaperAccount(Decimal(data["cash"]), Decimal(data["position"])), data["status"]
