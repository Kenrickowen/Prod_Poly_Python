#!/usr/bin/env python3
"""Run a no-trading simulation dashboard for UI and PnL testing."""
from __future__ import annotations

import asyncio
import logging
import math
import os
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from polymarket_python.dashboard import Dashboard
from polymarket_python.models import AppState, Candle, SignalDirection, Trade
from polymarket_python.runtime_config import load_position_size
from polymarket_python.settlement import recompute_trade_metrics

logger = logging.getLogger(__name__)


def _make_trade(
    *,
    timestamp_ms: int,
    direction: SignalDirection,
    token_id: str,
    price: float,
    size: float,
    pnl: float = 0.0,
    settled: bool = False,
    redemption_tx: str = "",
) -> Trade:
    return Trade(
        timestamp_ms=timestamp_ms,
        direction=direction,
        token_id=token_id,
        token_id_up="sim-up-token",
        token_id_down="sim-down-token",
        condition_id="0x" + "11" * 32,
        market_slug="btc-updown-5m-sim",
        price=price,
        size=size,
        pnl=pnl,
        settled=settled,
        redemption_tx=redemption_tx,
        signal_reason="simulation",
        signal_trend="demo",
    )


def seed_state() -> AppState:
    now = int(time.time() * 1000)
    state = AppState(price_source="Simulation")
    load_position_size(state)

    state.wallet_address = "0xSIM000000000000000000000000000000000000"
    state.wallet_pol_balance = 5.0
    state.wallet_usdc_balance = 0.0
    state.wallet_usdce_balance = 0.0
    state.wallet_pusd_balance = 100.0
    state.initial_balance = 100.0
    state.current_balance = 97.0
    state.last_wallet_balance_time_ms = now

    state.poly_market_slug = "btc-updown-5m-sim"
    state.poly_market_question = "Simulation: Bitcoin Up or Down"
    state.poly_market_condition_id = "0x" + "11" * 32
    state.poly_market_neg_risk = False
    state.poly_up_odds = 0.58
    state.poly_down_odds = 0.42
    state.last_poly_odds_time_ms = now

    state.trade_history = [
        _make_trade(
            timestamp_ms=now - 12 * 60_000,
            direction=SignalDirection.UP,
            token_id="sim-up-token",
            price=0.50,
            size=2.00,
            pnl=2.00,
            settled=True,
        ),
        _make_trade(
            timestamp_ms=now - 8 * 60_000,
            direction=SignalDirection.DOWN,
            token_id="sim-down-token",
            price=0.60,
            size=3.00,
            pnl=-3.00,
            settled=True,
        ),
        _make_trade(
            timestamp_ms=now - 90_000,
            direction=SignalDirection.UP,
            token_id="sim-up-token",
            price=0.50,
            size=2.00,
        ),
    ]
    state.trades_placed = len(state.trade_history)
    recompute_trade_metrics(state)
    return state


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    host = os.getenv("DASHBOARD_HOST", "0.0.0.0")
    port = int(os.getenv("SIM_DASHBOARD_PORT", "8082"))
    state = seed_state()

    async def redeem_simulated_trades() -> dict[str, int]:
        redeemed = 0
        for trade in state.trade_history:
            if trade.settled and not trade.redemption_tx:
                trade.redemption_tx = f"0xsim{trade.timestamp_ms:x}"
                redeemed += 1
        recompute_trade_metrics(state)
        return {"attempted": len(state.trade_history), "redeemed": redeemed, "settled": 0, "errors": 0}

    dashboard = Dashboard(state, host=host, port=port, redeem_callback=redeem_simulated_trades)

    async def tick_simulation() -> None:
        base_price = 100_000.0
        while True:
            now = int(time.time() * 1000)
            wave = math.sin(now / 18_000)
            state.last_price = base_price + wave * 420
            state.last_ticker_time_ms = now
            state.last_kline_time_ms = now
            state.last_poly_odds_time_ms = now
            state.poly_up_odds = max(0.02, min(0.98, 0.58 + wave * 0.16))
            state.poly_down_odds = 1.0 - state.poly_up_odds

            open_price = state.last_price - 35
            close_price = state.last_price
            state.push_kline(
                Candle(
                    open=open_price,
                    close=close_price,
                    high=max(open_price, close_price) + 80,
                    low=min(open_price, close_price) - 80,
                    volume=12.0 + abs(wave) * 8,
                    open_time_ms=now - (now % 60_000),
                )
            )
            dashboard.broadcast(dashboard._state_snapshot())
            await asyncio.sleep(2)

    sim_task = asyncio.create_task(tick_simulation())
    logger.info("[SIM] Dashboard started on http://%s:%s with no trading enabled", host, port)
    try:
        await dashboard.start()
    finally:
        sim_task.cancel()
        try:
            await sim_task
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    asyncio.run(main())
