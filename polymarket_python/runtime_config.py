"""Runtime dashboard settings persisted outside .env."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from polymarket_python.models import AppState

POSITION_SIZE_CONFIG = Path(__file__).resolve().parent.parent / "data" / "position_size.json"


def load_position_size(state: AppState, path: Path = POSITION_SIZE_CONFIG) -> None:
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return

    mode = str(data.get("mode") or state.position_size_mode).lower()
    if mode in {"fixed", "percent"}:
        state.position_size_mode = mode
    state.position_fixed_usd = _float(data.get("fixed_usd"), state.position_fixed_usd)
    state.position_equity_percent = _float(data.get("equity_percent"), state.position_equity_percent)


def save_position_size(state: AppState, path: Path = POSITION_SIZE_CONFIG) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_position_size_payload(state), indent=2) + "\n")


def _position_size_payload(state: AppState) -> dict[str, Any]:
    return {
        "mode": state.position_size_mode,
        "fixed_usd": state.position_fixed_usd,
        "equity_percent": state.position_equity_percent,
    }


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
