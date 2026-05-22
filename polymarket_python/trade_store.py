"""Trade history persistence with MySQL primary storage and CSV fallback."""
from __future__ import annotations

import csv
import io
import logging
from pathlib import Path
from typing import Any, Protocol

from polymarket_python.config import (
    MYSQL_DATABASE,
    MYSQL_HOST,
    MYSQL_PASSWORD,
    MYSQL_PORT,
    MYSQL_USER,
    TRADE_HISTORY_CSV,
    TRADE_STORE_BACKEND,
)
from polymarket_python.models import SignalDirection, Trade

logger = logging.getLogger(__name__)

FIELDNAMES = [
    "timestamp_ms",
    "direction",
    "market_slug",
    "condition_id",
    "token_id",
    "token_id_up",
    "token_id_down",
    "neg_risk",
    "paper_trade",
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


class TradeStore(Protocol):
    def load(self, limit: int = 200) -> list[Trade]:
        ...

    def save(self, trades: list[Trade]) -> None:
        ...

    def append(self, trade: Trade) -> None:
        ...

    def export_csv(self, limit: int | None = None) -> str:
        ...


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


def trade_key(trade: Trade) -> str:
    if trade.order_id:
        return f"order:{trade.order_id}"
    return f"trade:{trade.timestamp_ms}:{trade.direction.value}:{trade.token_id}:{trade.market_slug}"


def trade_to_row(trade: Trade) -> dict[str, Any]:
    return {
        "timestamp_ms": trade.timestamp_ms,
        "direction": trade.direction.value,
        "market_slug": trade.market_slug,
        "condition_id": trade.condition_id,
        "token_id": trade.token_id,
        "token_id_up": trade.token_id_up,
        "token_id_down": trade.token_id_down,
        "neg_risk": trade.neg_risk,
        "paper_trade": trade.paper_trade,
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
        paper_trade=_bool(row.get("paper_trade")),
        pnl=_float(row, "pnl"),
        settled=_bool(row.get("settled")),
        redemption_tx=str(row.get("redemption_tx") or ""),
        redemption_error=str(row.get("redemption_error") or ""),
        redemption_checked_ms=_int(row, "redemption_checked_ms"),
    )


def trades_to_csv(trades: list[Trade]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=FIELDNAMES)
    writer.writeheader()
    for trade in trades:
        writer.writerow(trade_to_row(trade))
    return buf.getvalue()


class CSVTradeStore:
    def __init__(self, path: str | Path | None = None):
        self.path = _csv_path(path)

    def load(self, limit: int = 200) -> list[Trade]:
        if not self.path.exists():
            return []

        with self.path.open("r", newline="") as f:
            rows = list(csv.DictReader(f))

        trades = [row_to_trade(row) for row in rows if row.get("timestamp_ms")]
        trades.sort(key=lambda t: t.timestamp_ms, reverse=True)
        return trades[:limit]

    def save(self, trades: list[Trade]) -> None:
        rows = [trade_to_row(t) for t in sorted(trades, key=lambda t: t.timestamp_ms)]
        with self.path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)

    def append(self, trade: Trade) -> None:
        exists = self.path.exists() and self.path.stat().st_size > 0
        with self.path.open("a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            if not exists:
                writer.writeheader()
            writer.writerow(trade_to_row(trade))

    def export_csv(self, limit: int | None = None) -> str:
        trades = self.load(limit or 100_000)
        return trades_to_csv(sorted(trades, key=lambda t: t.timestamp_ms))


class MySQLTradeStore:
    def __init__(
        self,
        host: str = MYSQL_HOST,
        port: int = MYSQL_PORT,
        database: str = MYSQL_DATABASE,
        user: str = MYSQL_USER,
        password: str = MYSQL_PASSWORD,
    ):
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self._pymysql = None
        self._ensure_ready()

    def _ensure_ready(self) -> None:
        if not all([self.host, self.database, self.user]):
            raise RuntimeError("MySQL trade store requires MYSQL_HOST, MYSQL_DATABASE, and MYSQL_USER")
        try:
            import pymysql
        except ImportError as e:
            raise RuntimeError("pymysql is required for TRADE_STORE_BACKEND=mysql") from e
        self._pymysql = pymysql
        self._ensure_schema()

    def _connect(self):
        return self._pymysql.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.database,
            charset="utf8mb4",
            autocommit=True,
            cursorclass=self._pymysql.cursors.DictCursor,
            connect_timeout=5,
            read_timeout=10,
            write_timeout=10,
        )

    def _ensure_schema(self) -> None:
        ddl = """
        CREATE TABLE IF NOT EXISTS trades (
            trade_key VARCHAR(255) NOT NULL PRIMARY KEY,
            timestamp_ms BIGINT NOT NULL,
            direction VARCHAR(8) NOT NULL,
            market_slug VARCHAR(255) NOT NULL DEFAULT '',
            condition_id VARCHAR(255) NOT NULL DEFAULT '',
            token_id VARCHAR(255) NOT NULL DEFAULT '',
            token_id_up VARCHAR(255) NOT NULL DEFAULT '',
            token_id_down VARCHAR(255) NOT NULL DEFAULT '',
            neg_risk BOOLEAN NOT NULL DEFAULT FALSE,
            paper_trade BOOLEAN NOT NULL DEFAULT FALSE,
            order_id VARCHAR(255) NOT NULL DEFAULT '',
            price DOUBLE NOT NULL DEFAULT 0,
            size DOUBLE NOT NULL DEFAULT 0,
            pnl DOUBLE NOT NULL DEFAULT 0,
            settled BOOLEAN NOT NULL DEFAULT FALSE,
            redemption_tx VARCHAR(255) NOT NULL DEFAULT '',
            redemption_error TEXT,
            redemption_checked_ms BIGINT NOT NULL DEFAULT 0,
            signal_reason VARCHAR(255) NOT NULL DEFAULT '',
            signal_trend VARCHAR(255) NOT NULL DEFAULT '',
            signal_ptb DOUBLE NOT NULL DEFAULT 0,
            trigger_open DOUBLE NOT NULL DEFAULT 0,
            trigger_close DOUBLE NOT NULL DEFAULT 0,
            trigger_high DOUBLE NOT NULL DEFAULT 0,
            trigger_low DOUBLE NOT NULL DEFAULT 0,
            trigger_time_ms BIGINT NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            KEY idx_timestamp_ms (timestamp_ms),
            KEY idx_order_id (order_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(ddl)

    def _upsert(self, cur, trade: Trade) -> None:
        row = trade_to_row(trade)
        row["trade_key"] = trade_key(trade)
        columns = ["trade_key", *FIELDNAMES]
        placeholders = ", ".join(["%s"] * len(columns))
        updates = ", ".join(f"{c}=VALUES({c})" for c in FIELDNAMES)
        sql = f"""
            INSERT INTO trades ({", ".join(columns)})
            VALUES ({placeholders})
            ON DUPLICATE KEY UPDATE {updates}
        """
        cur.execute(sql, [row[c] for c in columns])

    def append(self, trade: Trade) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                self._upsert(cur, trade)

    def save(self, trades: list[Trade]) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                for trade in trades:
                    self._upsert(cur, trade)

    def load(self, limit: int = 200) -> list[Trade]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM trades ORDER BY timestamp_ms DESC LIMIT %s", (limit,))
                rows = cur.fetchall()
        return [row_to_trade(row) for row in rows]

    def count(self) -> int:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS n FROM trades")
                row = cur.fetchone() or {"n": 0}
        return int(row.get("n") or 0)

    def import_csv_once(self, csv_store: CSVTradeStore | None = None) -> int:
        csv_store = csv_store or CSVTradeStore()
        if not csv_store.path.exists():
            return 0
        if self.count() > 0:
            return 0
        trades = csv_store.load(limit=100_000)
        if not trades:
            return 0
        self.save(trades)
        return len(trades)

    def export_csv(self, limit: int | None = None) -> str:
        trades = self.load(limit or 100_000)
        return trades_to_csv(sorted(trades, key=lambda t: t.timestamp_ms))


class FallbackTradeStore:
    def __init__(self, primary: TradeStore, fallback: CSVTradeStore):
        self.primary = primary
        self.fallback = fallback

    def load(self, limit: int = 200) -> list[Trade]:
        try:
            return self.primary.load(limit)
        except Exception as e:
            logger.warning("[TRADE_STORE] MySQL load failed, using CSV fallback: %s", e)
            return self.fallback.load(limit)

    def save(self, trades: list[Trade]) -> None:
        try:
            self.primary.save(trades)
        except Exception as e:
            logger.warning("[TRADE_STORE] MySQL save failed, writing CSV fallback: %s", e)
            self.fallback.save(trades)

    def append(self, trade: Trade) -> None:
        try:
            self.primary.append(trade)
        except Exception as e:
            logger.warning("[TRADE_STORE] MySQL append failed, writing CSV fallback: %s", e)
            self.fallback.append(trade)

    def export_csv(self, limit: int | None = None) -> str:
        try:
            return self.primary.export_csv(limit)
        except Exception as e:
            logger.warning("[TRADE_STORE] MySQL CSV export failed, using CSV fallback: %s", e)
            return self.fallback.export_csv(limit)


_default_store: TradeStore | None = None


def get_trade_store() -> TradeStore:
    global _default_store
    if _default_store is not None:
        return _default_store

    csv_store = CSVTradeStore()
    if TRADE_STORE_BACKEND == "mysql":
        try:
            mysql_store = MySQLTradeStore()
            imported = mysql_store.import_csv_once(csv_store)
            if imported:
                logger.info("[TRADE_STORE] Imported %s CSV trade(s) into MySQL", imported)
            _default_store = FallbackTradeStore(mysql_store, csv_store)
        except Exception as e:
            logger.warning("[TRADE_STORE] MySQL unavailable, using CSV fallback: %s", e)
            _default_store = csv_store
    else:
        _default_store = csv_store
    return _default_store


def load_trade_history(path: str | Path | None = None, limit: int = 200) -> list[Trade]:
    if path is not None:
        return CSVTradeStore(path).load(limit)
    return get_trade_store().load(limit)


def save_trade_history(trades: list[Trade], path: str | Path | None = None) -> None:
    if path is not None:
        CSVTradeStore(path).save(trades)
        return
    get_trade_store().save(trades)


def append_trade(trade: Trade, path: str | Path | None = None) -> None:
    if path is not None:
        CSVTradeStore(path).append(trade)
        return
    get_trade_store().append(trade)


def export_trade_history_csv(limit: int | None = None) -> str:
    return get_trade_store().export_csv(limit)
