from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from polymarket_python.models import SignalDirection, Trade
from polymarket_python.trade_store import append_trade, load_trade_history, save_trade_history


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
                settled=True,
                signal_reason="B_Breakout_UP_PTB",
            )

            append_trade(trade, path)
            loaded = load_trade_history(path)

            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].redemption_tx, "0xtx")
            self.assertTrue(loaded[0].settled)

            loaded[0].redemption_error = "done"
            save_trade_history(loaded, path)
            reloaded = load_trade_history(path)

            self.assertEqual(reloaded[0].redemption_error, "done")


if __name__ == "__main__":
    unittest.main()
