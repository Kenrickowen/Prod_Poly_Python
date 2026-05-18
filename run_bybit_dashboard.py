#!/usr/bin/env python3
"""Run the dashboard with Bybit BTCUSDT WebSocket prices only."""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
load_dotenv(Path(__file__).parent / ".env")

from polymarket_python.bybit_client import BybitClient
from polymarket_python.config import BYBIT_SYMBOL, POLY_ODDS_POLL_SECS, WALLET_BALANCE_POLL_SECS
from polymarket_python.dashboard import Dashboard
from polymarket_python.models import AppState
from polymarket_python.indicators import update_indicators
from polymarket_python.polymarket_public_client import fetch_current_btc_odds
from polymarket_python.trade_store import load_trade_history
from polymarket_python.wallet_balances import WalletBalanceClient


def apply_wallet_balances(state: AppState, balances) -> None:
    state.wallet_address = balances.address
    state.wallet_pol_balance = balances.pol
    state.wallet_usdc_balance = balances.usdc
    state.wallet_usdce_balance = balances.usdce
    state.wallet_pusd_balance = balances.pusd
    state.current_balance = balances.pusd
    state.last_wallet_balance_time_ms = balances.timestamp_ms
    state.wallet_balance_error = ""


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    host = os.getenv("DASHBOARD_HOST", "0.0.0.0")
    port = int(os.getenv("BYBIT_DASHBOARD_PORT", os.getenv("DASHBOARD_PORT", "8081")))

    state = AppState(price_source="Bybit WebSocket")
    state.trade_history = load_trade_history()
    state.trades_placed = len(state.trade_history)
    dashboard = Dashboard(state, host=host, port=port)

    async def on_price(price: float) -> None:
        dashboard.broadcast(dashboard._state_snapshot())

    async def on_candle(candle) -> None:
        update_indicators(state)
        dashboard.broadcast(dashboard._state_snapshot())

    async def poll_polymarket_odds() -> None:
        while True:
            try:
                market, up_odds, down_odds = await fetch_current_btc_odds()
                if market:
                    state.poly_up_odds = up_odds
                    state.poly_down_odds = down_odds
                    state.poly_market_slug = market.slug
                    state.poly_market_question = market.question
                    state.poly_market_condition_id = market.condition_id
                    state.poly_market_neg_risk = market.neg_risk
                    state.last_poly_odds_time_ms = int(time.time() * 1000)
                    dashboard.broadcast(dashboard._state_snapshot())
                    logger.info(
                        "[POLY_PUBLIC] %s odds: UP=%s DOWN=%s",
                        market.slug,
                        up_odds,
                        down_odds,
                    )
            except Exception as e:
                logger.warning("[POLY_PUBLIC] odds poll failed: %s", e)
            await asyncio.sleep(POLY_ODDS_POLL_SECS)

    async def poll_wallet_balances() -> None:
        try:
            balance_client = WalletBalanceClient()
        except Exception as e:
            state.wallet_balance_error = str(e)
            logger.warning("[WALLET] balance poll disabled: %s", e)
            dashboard.broadcast(dashboard._state_snapshot())
            return

        while True:
            try:
                balances = await asyncio.to_thread(balance_client.fetch)
                apply_wallet_balances(state, balances)
                dashboard.broadcast(dashboard._state_snapshot())
                logger.info(
                    "[WALLET] POL=%.6f USDC=%.2f USDC.e=%.2f pUSD=%.2f",
                    balances.pol,
                    balances.usdc,
                    balances.usdce,
                    balances.pusd,
                )
            except Exception as e:
                state.wallet_balance_error = str(e)
                dashboard.broadcast(dashboard._state_snapshot())
                logger.warning("[WALLET] balance poll failed: %s", e)
            await asyncio.sleep(WALLET_BALANCE_POLL_SECS)

    bybit = BybitClient(state=state, symbol=BYBIT_SYMBOL, on_price=on_price, on_candle=on_candle)

    await bybit.start()
    logger = logging.getLogger(__name__)
    odds_task = asyncio.create_task(poll_polymarket_odds())
    wallet_task = asyncio.create_task(poll_wallet_balances())
    logger.info("[DASHBOARD] Bybit dashboard: http://%s:%s", host, port)

    try:
        await dashboard.start()
    finally:
        for task in (odds_task, wallet_task):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        await bybit.stop()


if __name__ == "__main__":
    asyncio.run(main())
