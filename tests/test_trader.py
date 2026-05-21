from __future__ import annotations

import unittest

import polymarket_python.trader as trader_module
from polymarket_python.models import AppState, Candle, CandleColor, Signal, SignalDirection
from polymarket_python.strategy_legacy import evaluate_signal_legacy
from polymarket_python.trader import Trader


class FakePolymarketClient:
    def __init__(self) -> None:
        self.orders: list[tuple[str, str, float]] = []

    async def get_odds(self, token_id: str) -> float:
        return 0.5

    async def place_market_order(self, token_id: str, side: str, amount_usd: float) -> dict[str, str]:
        self.orders.append((token_id, side, amount_usd))
        return {"orderID": "test-order"}


class TraderTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.original_append_trade = trader_module.append_trade
        trader_module.append_trade = lambda trade: None

    async def asyncTearDown(self) -> None:
        trader_module.append_trade = self.original_append_trade

    async def test_down_signal_buys_down_token(self) -> None:
        state = AppState()
        state.position_size_mode = "fixed"
        state.position_fixed_usd = 7.0
        client = FakePolymarketClient()
        trader = Trader(client, token_id_up="up-token", token_id_down="down-token")

        success = await trader.on_signal(
            state,
            Signal(direction=SignalDirection.DOWN, reason="test"),
        )

        self.assertTrue(success)
        self.assertEqual(client.orders, [("down-token", "BUY", 7.0)])
        self.assertEqual(state.trade_history[0].direction, SignalDirection.DOWN)
        self.assertEqual(state.trade_history[0].token_id, "down-token")

    async def test_up_signal_buys_up_token(self) -> None:
        state = AppState()
        state.position_size_mode = "fixed"
        state.position_fixed_usd = 3.0
        client = FakePolymarketClient()
        trader = Trader(client, token_id_up="up-token", token_id_down="down-token")

        success = await trader.on_signal(
            state,
            Signal(direction=SignalDirection.UP, reason="test"),
        )

        self.assertTrue(success)
        self.assertEqual(client.orders, [("up-token", "BUY", 3.0)])


def make_candle(start_ms: int, open_: float, close: float) -> Candle:
    candle = Candle(
        open=open_,
        close=close,
        high=max(open_, close) + 1,
        low=min(open_, close) - 1,
        volume=10,
        open_time_ms=start_ms,
    )
    candle.color = CandleColor.GREEN if close > open_ else CandleColor.RED if close < open_ else CandleColor.DOJI
    return candle


class LegacyStrategyTests(unittest.TestCase):
    def test_legacy_bearish_breakout_emits_down_signal(self) -> None:
        window_start = 1_779_085_200_000
        state = AppState()
        state.strategy_mode = "legacy"
        state.window.window_start_ms = window_start
        state.window.ptb = 100_000.0
        state.indicators.valid = True
        state.indicators.atr = 100.0
        state.indicators.vol_sma = 1.0
        state.klines = [
            make_candle(window_start - 180_000, 100_500.0, 100_300.0),
            make_candle(window_start - 120_000, 100_300.0, 100_100.0),
            make_candle(window_start - 60_000, 100_100.0, 99_900.0),
            make_candle(window_start, 99_900.0, 99_800.0),
        ]

        signal, rejection = evaluate_signal_legacy(state, window_start + 61_000)

        self.assertIsNone(rejection)
        self.assertIsNotNone(signal)
        self.assertEqual(signal.direction, SignalDirection.DOWN)


if __name__ == "__main__":
    unittest.main()
