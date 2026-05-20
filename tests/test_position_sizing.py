from __future__ import annotations

import unittest

from polymarket_python.models import AppState, SignalDirection, Trade
from polymarket_python.trader import calculate_position_size_usd


class PositionSizingTests(unittest.TestCase):
    def test_fixed_position_size_uses_configured_dollars(self) -> None:
        state = AppState()
        state.position_size_mode = "fixed"
        state.position_fixed_usd = 2.5

        self.assertEqual(calculate_position_size_usd(state), 2.5)

    def test_percent_position_size_uses_cash_plus_open_cost_basis(self) -> None:
        state = AppState()
        state.position_size_mode = "percent"
        state.position_equity_percent = 10
        state.current_balance = 90
        state.wallet_pusd_balance = 90
        state.trade_history = [
            Trade(
                timestamp_ms=1,
                direction=SignalDirection.UP,
                token_id="up",
                price=0.5,
                size=10,
            )
        ]

        self.assertEqual(calculate_position_size_usd(state), 10)

    def test_position_size_is_capped_to_available_pusd(self) -> None:
        state = AppState()
        state.position_size_mode = "percent"
        state.position_equity_percent = 50
        state.current_balance = 4
        state.wallet_pusd_balance = 4
        state.trade_history = [
            Trade(
                timestamp_ms=1,
                direction=SignalDirection.UP,
                token_id="up",
                price=0.5,
                size=10,
            )
        ]

        self.assertEqual(calculate_position_size_usd(state), 4)


if __name__ == "__main__":
    unittest.main()
