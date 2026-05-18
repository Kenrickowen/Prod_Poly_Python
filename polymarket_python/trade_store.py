"""CSV persistence for trade history."""
from __future__ import annotations

import csv
from pathlib import Path

from polymarket_python.config import TRADE_HISTORY_CSV
from polymarket_python.models import SignalDirection, Trade

FIELDNAMES = [
    "timestamp_ms",
    "direction",
    "market_slug",
    "condition_id",
    "token_id",
    "token_id_up",
    "token_id_down",
    "neg_risk",
    "order_id",
    "price",
    "size",
    "pnl",
    "settled",
    "redemption_tx",
    "redemption_error",
    "redemption_checked_ms",
    "signal_reason",
    "signal_trend",
    "signal_ptb",
    "trigger_open",
    "trigger_close",
    "trigger_high",
    "trigger_low",
    "trigger_time_ms",
]


def _csv_path(path: str | Path | None = None) -> Path:
    p = Path(path or TRADE_HISTORY_CSV)
    if not p.is_absolute():
        p = Path(__file__).resolve().parent.parent / p
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes", "y"}


def _float(row: dict, key: str) -> float:
    try:
        return float(row.get(key) or 0)
    except (TypeError, ValueError):
        return 0.0


def _int(row: dict, key: str) -> int:
    try:
        return int(float(row.get(key) or 0))
    except (TypeError, ValueError):
        return 0


def trade_to_row(trade: Trade) -> dict:
    return {
        "timestamp_ms": trade.timestamp_ms,
        "direction": trade.direction.value,
        "market_slug": trade.market_slug,
        "condition_id": trade.condition_id,
        "token_id": trade.token_id,
        "token_id_up": trade.token_id_up,
        "token_id_down": trade.token_id_down,
        "neg_risk": trade.neg_risk,
        "order_id": trade.order_id,
        "price": trade.price,
        "size": trade.size,
        "pnl": trade.pnl,
        "settled": trade.settled,
        "redemption_tx": trade.redemption_tx,
        "redemption_error": trade.redemption_error,
        "redemption_checked_ms": trade.redemption_checked_ms,
        "signal_reason": trade.signal_reason,
        "signal_trend": trade.signal_trend,
        "signal_ptb": trade.signal_ptb,
        "trigger_open": trade.trigger_open,
        "trigger_close": trade.trigger_close,
        "trigger_high": trade.trigger_high,
        "trigger_low": trade.trigger_low,
        "trigger_time_ms": trade.trigger_time_ms,
    }


def row_to_trade(row: dict) -> Trade:
    direction = str(row.get("direction") or "UP").upper()
    return Trade(
        timestamp_ms=_int(row, "timestamp_ms"),
        direction=SignalDirection.DOWN if direction == "DOWN" else SignalDirection.UP,
        token_id=str(row.get("token_id") or ""),
        price=_float(row, "price"),
        size=_float(row, "size"),
        condition_id=str(row.get("condition_id") or ""),
        market_slug=str(row.get("market_slug") or ""),
        order_id=str(row.get("order_id") or ""),
        signal_reason=str(row.get("signal_reason") or ""),
        signal_trend=str(row.get("signal_trend") or ""),
        signal_ptb=_float(row, "signal_ptb"),
        trigger_open=_float(row, "trigger_open"),
        trigger_close=_float(row, "trigger_close"),
        trigger_high=_float(row, "trigger_high"),
        trigger_low=_float(row, "trigger_low"),
        trigger_time_ms=_int(row, "trigger_time_ms"),
        token_id_up=str(row.get("token_id_up") or ""),
        token_id_down=str(row.get("token_id_down") or ""),
        neg_risk=_bool(row.get("neg_risk")),
        pnl=_float(row, "pnl"),
        settled=_bool(row.get("settled")),
        redemption_tx=str(row.get("redemption_tx") or ""),
        redemption_error=str(row.get("redemption_error") or ""),
        redemption_checked_ms=_int(row, "redemption_checked_ms"),
    )


def load_trade_history(path: str | Path | None = None, limit: int = 200) -> list[Trade]:
    p = _csv_path(path)
    if not p.exists():
        return []

    with p.open("r", newline="") as f:
        rows = list(csv.DictReader(f))

    trades = [row_to_trade(row) for row in rows if row.get("timestamp_ms")]
    trades.sort(key=lambda t: t.timestamp_ms, reverse=True)
    return trades[:limit]


def save_trade_history(trades: list[Trade], path: str | Path | None = None) -> None:
    p = _csv_path(path)
    rows = [trade_to_row(t) for t in sorted(trades, key=lambda t: t.timestamp_ms)]
    with p.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def append_trade(trade: Trade, path: str | Path | None = None) -> None:
    p = _csv_path(path)
    exists = p.exists() and p.stat().st_size > 0
    with p.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if not exists:
            writer.writeheader()
        writer.writerow(trade_to_row(trade))
