from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from polymarket_python.models import SignalDirection, Trade
from polymarket_python.trade_store import (
    CSVTradeStore,
    FallbackTradeStore,
    append_trade,
    load_trade_history,
    save_trade_history,
    trade_key,
)


class TradeStoreTests(unittest.TestCase):
    def test_csv_round_trip_preserves_redemption_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trades.csv"
            trade = Trade(
                timestamp_ms=123,
                direction=SignalDirection.UP,
                token_id="token",
                price=0.42,
                size=10,
                market_slug="btc-updown-5m-123",
                condition_id="0xabc",
                redemption_tx="0xtx",
                paper_trade=True,
                settled=True,
                signal_reason="B_Breakout_UP_PTB",
            )

            append_trade(trade, path)
            loaded = load_trade_history(path)

            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].redemption_tx, "0xtx")
            self.assertTrue(loaded[0].paper_trade)
            self.assertTrue(loaded[0].settled)

            loaded[0].redemption_error = "done"
            save_trade_history(loaded, path)
            reloaded = load_trade_history(path)

            self.assertEqual(reloaded[0].redemption_error, "done")

    def test_trade_key_prefers_order_id(self) -> None:
        trade = Trade(timestamp_ms=1, direction=SignalDirection.DOWN, token_id="down", price=0.4, size=1, order_id="abc")

        self.assertEqual(trade_key(trade), "order:abc")

    def test_fallback_store_writes_csv_when_primary_fails(self) -> None:
        class BrokenStore:
            def load(self, limit: int = 200):
                raise RuntimeError("db down")

            def save(self, trades):
                raise RuntimeError("db down")

            def append(self, trade):
                raise RuntimeError("db down")

            def export_csv(self, limit=None):
                raise RuntimeError("db down")

        with tempfile.TemporaryDirectory() as tmp:
            csv_store = CSVTradeStore(Path(tmp) / "fallback.csv")
            store = FallbackTradeStore(BrokenStore(), csv_store)
            trade = Trade(timestamp_ms=123, direction=SignalDirection.UP, token_id="up", price=0.5, size=2)

            store.append(trade)

            loaded = store.load()
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].token_id, "up")


if __name__ == "__main__":
    unittest.main()
