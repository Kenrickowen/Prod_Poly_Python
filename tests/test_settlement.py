from __future__ import annotations

import unittest

from polymarket_python.models import AppState, SignalDirection, Trade
from polymarket_python.polymarket_public_client import BtcMarket
from polymarket_python.settlement import recompute_trade_metrics, update_trade_from_resolved_market


class SettlementTests(unittest.TestCase):
    def test_resolved_win_sets_realized_pnl(self) -> None:
        trade = Trade(
            timestamp_ms=1,
            direction=SignalDirection.UP,
            token_id="up",
            token_id_up="up",
            token_id_down="down",
            market_slug="btc-updown-5m-1",
            price=0.5,
            size=1.0,
        )
        market = BtcMarket(
            slug="btc-updown-5m-1",
            question="",
            token_id_up="up",
            token_id_down="down",
            closed=True,
            resolved=True,
            gamma_up_odds=1.0,
            gamma_down_odds=0.0,
        )

        changed = update_trade_from_resolved_market(trade, market)

        self.assertTrue(changed)
        self.assertTrue(trade.settled)
        self.assertAlmostEqual(trade.pnl, 1.0)

    def test_resolved_loss_sets_realized_pnl(self) -> None:
        trade = Trade(
            timestamp_ms=1,
            direction=SignalDirection.DOWN,
            token_id="down",
            token_id_up="up",
            token_id_down="down",
            market_slug="btc-updown-5m-1",
            price=0.4,
            size=2.0,
        )
        market = BtcMarket(
            slug="btc-updown-5m-1",
            question="",
            token_id_up="up",
            token_id_down="down",
            closed=True,
            resolved=True,
            gamma_up_odds=1.0,
            gamma_down_odds=0.0,
        )

        changed = update_trade_from_resolved_market(trade, market)

        self.assertTrue(changed)
        self.assertTrue(trade.settled)
        self.assertAlmostEqual(trade.pnl, -2.0)

    def test_recompute_trade_metrics_uses_settled_trades(self) -> None:
        state = AppState()
        state.trade_history = [
            Trade(timestamp_ms=1, direction=SignalDirection.UP, token_id="up", price=0.5, size=1.0, pnl=1.0, settled=True),
            Trade(timestamp_ms=2, direction=SignalDirection.DOWN, token_id="down", price=0.5, size=1.0, pnl=-1.0, settled=True),
            Trade(timestamp_ms=3, direction=SignalDirection.UP, token_id="up", price=0.5, size=1.0, pnl=0.4, settled=False),
        ]

        recompute_trade_metrics(state)

        self.assertEqual(state.win_count, 1)
        self.assertEqual(state.loss_count, 1)
        self.assertAlmostEqual(state.total_pnl, 0.0)


if __name__ == "__main__":
    unittest.main()
