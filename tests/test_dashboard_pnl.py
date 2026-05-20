from __future__ import annotations

import unittest

from polymarket_python.dashboard import Dashboard
from polymarket_python.models import AppState, SignalDirection, Trade


class DashboardPnlTests(unittest.TestCase):
    def test_total_pnl_includes_open_position_value(self) -> None:
        state = AppState()
        state.initial_balance = 10.0
        state.current_balance = 9.0
        state.wallet_pusd_balance = 9.0
        state.poly_market_slug = "btc-updown-5m-1"
        state.poly_up_odds = 0.6
        state.trade_history = [
            Trade(
                timestamp_ms=1,
                direction=SignalDirection.UP,
                token_id="up",
                token_id_up="up",
                token_id_down="down",
                market_slug="btc-updown-5m-1",
                price=0.5,
                size=1.0,
            )
        ]

        snapshot = Dashboard(state)._state_snapshot()

        self.assertAlmostEqual(snapshot["metrics"]["total_pnl"], 0.2)
        self.assertAlmostEqual(snapshot["trade_history"][0]["pnl"], 0.2)

    def test_total_pnl_includes_resolved_not_yet_redeemed_value(self) -> None:
        state = AppState()
        state.initial_balance = 10.0
        state.current_balance = 9.0
        state.wallet_pusd_balance = 9.0
        state.trade_history = [
            Trade(
                timestamp_ms=1,
                direction=SignalDirection.UP,
                token_id="up",
                price=0.5,
                size=1.0,
                pnl=1.0,
                settled=True,
            )
        ]

        snapshot = Dashboard(state)._state_snapshot()

        self.assertAlmostEqual(snapshot["metrics"]["total_pnl"], 1.0)
        self.assertEqual(snapshot["trade_history"][0]["status"], "Won")


if __name__ == "__main__":
    unittest.main()
