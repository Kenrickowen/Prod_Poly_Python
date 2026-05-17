"""Main event loop — wires together all components."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Load .env file
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()

from polymarket_python.config import (
    DASHBOARD_HOST,
    DASHBOARD_PORT,
    GAMMA_HOST,
    WINDOW_MINUTES,
)
from polymarket_python.models import AppState, Candle
from polymarket_python.binance_client import BinanceClient
from polymarket_python.chainlink_client import fetch_btc_price
from polymarket_python.polymarket_client import PolymarketClient
from polymarket_python.strategy import evaluate_signal
from polymarket_python.state import (
    capture_ptb_from_binance,
    capture_ptb_from_chainlink,
    record_first_in_window,
    reset_window,
)
from polymarket_python.indicators import update_indicators
from polymarket_python.scheduler import (
    calculate_window_start,
    is_window_boundary,
    window_elapsed_ms,
)
from polymarket_python.trader import Trader
from polymarket_python.dashboard import Dashboard

logger = logging.getLogger(__name__)


async def fetch_current_btc_market() -> tuple[str | None, str | None, float | None]:
    """
    Fetch the active BTC 5m market from Gamma API and return (token_id_up, token_id_down, market_mid).
    Returns (None, None, None) if no active market found.
    Also extracts the market mid price as a fallback BTC price indicator.
    """
    import httpx

    now_s = int(time.time())
    window_ts = (now_s // (WINDOW_MINUTES * 60)) * (WINDOW_MINUTES * 60)
    slug = f"btc-updown-5m-{window_ts}"

    url = f"{GAMMA_HOST}/markets"
    params = {"slug": slug, "limit": 1}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

            if not isinstance(data, list) or len(data) == 0:
                logger.warning(f"[GAMMA] No market found for slug={slug}")
                return None, None, None

            m = data[0]
            if m.get("closed") or not m.get("acceptingOrders"):
                logger.warning(f"[GAMMA] Market {slug} is closed or not accepting orders")
                return None, None, None

            token_ids_raw = m.get("clobTokenIds", "[]")
            token_ids = json.loads(token_ids_raw) if isinstance(token_ids_raw, str) else token_ids_raw

            prices_raw = m.get("outcomePrices", "[]")
            prices = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw

            market_mid = None
            if len(prices) >= 2:
                try:
                    market_mid = (float(prices[0]) + float(prices[1])) / 2
                except (ValueError, TypeError):
                    market_mid = None

            if len(token_ids) < 2:
                logger.warning(f"[GAMMA] Market {slug} has fewer than 2 token IDs: {token_ids}")
                return None, None, None

            logger.info(f"[GAMMA] Market {slug} found: UP={token_ids[0]}, DOWN={token_ids[1]}, mid={market_mid}")
            return token_ids[0], token_ids[1], market_mid

    except Exception as e:
        logger.error(f"[GAMMA] Failed to fetch market: {e}")
        return None, None, None


async def poll_price_fallback(state: AppState) -> None:
    """
    Poll fallback price sources when Binance is unavailable.
    Tries: CoinGecko → Binance REST → Polymarket market mid.
    """
    from polymarket_python.price_fallback import fetch_btc_price_coingecko

    price = await fetch_btc_price_coingecko()
    if price and price > 0:
        state.last_price = price
        now_ms = int(time.time() * 1000)
        capture_ptb_from_binance(state, price, now_ms)
        logger.info(f"[FALLBACK] BTC price = ${price:,.2f} (CoinGecko)")


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # Validate required env vars
    required = ["PRIVATE_KEY", "FUNDER_ADDRESS", "INFURA_URL"]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        logger.error(f"[MAIN] Missing env vars: {missing}")
        sys.exit(1)

    # Auto-fetch market token IDs (or use env vars as fallback)
    token_id_up = os.getenv("TOKEN_ID_UP", "")
    token_id_down = os.getenv("TOKEN_ID_DOWN", "")

    if not token_id_up or not token_id_down:
        logger.info("[MAIN] TOKEN_ID not set — fetching active BTC market from Gamma API...")
        token_id_up, token_id_down, market_mid = await fetch_current_btc_market()
        if not token_id_up or not token_id_down:
            logger.error("[MAIN] Could not resolve market token IDs. Set TOKEN_ID_UP and TOKEN_ID_DOWN in .env")
            sys.exit(1)
        # Use market mid as initial BTC price fallback
        if market_mid:
            state = AppState()
            state.last_price = market_mid
    else:
        logger.info(f"[MAIN] Using TOKEN_ID from .env: UP={token_id_up}, DOWN={token_id_down}")
        state = AppState()

    # Initialize shared state
    state = AppState()

    # If we have market mid from auto-fetch, seed last_price
    if market_mid:
        state.last_price = market_mid

    # Initialize Polymarket client
    poly_client = PolymarketClient()

    # Initialize trader
    trader = Trader(poly_client, token_id_up, token_id_down)

    # Start Polymarket WebSocket feed
    poly_client.start_ws_feed([token_id_up, token_id_down])
    logger.info(f"[POLY_WS] Subscribed to {token_id_up}, {token_id_down}")

    # Initialize dashboard
    dashboard = Dashboard(state, host=DASHBOARD_HOST, port=DASHBOARD_PORT)
    dashboard_task = asyncio.create_task(dashboard.start())
    logger.info(f"[DASHBOARD] Started on http://{DASHBOARD_HOST}:{DASHBOARD_PORT}")

    # Binance callbacks
    async def on_candle(candle: Candle) -> None:
        now_ms = candle.open_time_ms + 60_000

        if state.window.ptb == 0.0 and candle.close > 0:
            capture_ptb_from_binance(state, candle.close, now_ms)

        record_first_in_window(state, candle)
        update_indicators(state)

        # Check window boundary
        window_start = calculate_window_start(now_ms)
        if state.window.window_start_ms > 0 and is_window_boundary(now_ms, state.window.window_start_ms):
            logger.info(f"[WINDOW] New window at {window_start} — resetting")
            reset_window(state, window_start)

        dashboard.broadcast(dashboard._state_snapshot())

    async def on_price(price: float) -> None:
        now_ms = int(time.time() * 1000)
        capture_ptb_from_binance(state, price, now_ms)

    # Start Binance WebSocket
    binance = BinanceClient(state=state, on_candle=on_candle, on_price=on_price)
    binance_task = asyncio.create_task(binance.start())
    logger.info("[FEEDS] Binance WebSocket started")

    # Fallback price polling (when Binance is blocked)
    async def poll_fallback_prices() -> None:
        while True:
            await asyncio.sleep(60)
            # Only poll if we don't have a valid BTC price
            if state.last_price <= 0:
                await poll_price_fallback(state)
                dashboard.broadcast(dashboard._state_snapshot())

    fallback_task = asyncio.create_task(poll_fallback_prices())

    # Chainlink poll task
    async def poll_chainlink() -> None:
        while True:
            await asyncio.sleep(30)
            try:
                price = fetch_btc_price()
                if price and price > 0:
                    state.chainlink_price = price
                    now_ms = int(time.time() * 1000)
                    capture_ptb_from_chainlink(state, price, now_ms)
                    logger.info(f"[CHAINLINK] BTC/USD = ${price:,.2f}")
            except Exception as e:
                logger.debug(f"[CHAINLINK] poll error: {e}")

    chainlink_task = asyncio.create_task(poll_chainlink())

    # Main evaluation loop
    logger.info("[MAIN] Entering main loop")

    async def evaluation_loop() -> None:
        nonlocal token_id_up, token_id_down

        while True:
            await asyncio.sleep(5)
            now_ms = int(time.time() * 1000)

            # Initialize window on first run
            if state.window.window_start_ms == 0:
                state.window.window_start_ms = calculate_window_start(now_ms)
                logger.info(f"[WINDOW] Initial window: {state.window.window_start_ms}")

            # Check window boundary
            window_start = calculate_window_start(now_ms)
            if is_window_boundary(now_ms, state.window.window_start_ms):
                logger.info(f"[WINDOW] New window starting at {window_start} — fetching new market")
                reset_window(state, window_start)

                # Refetch market for new window (new slug = new token IDs)
                new_up, new_down, market_mid = await fetch_current_btc_market()
                if new_up and new_down:
                    token_id_up, token_id_down = new_up, new_down
                    trader.token_id_up = token_id_up
                    trader.token_id_down = token_id_down
                    # Resubscribe WebSocket to new token IDs
                    poly_client.stop_ws_feed()
                    poly_client.start_ws_feed([token_id_up, token_id_down])
                    logger.info(f"[WINDOW] New market: UP={token_id_up}, DOWN={token_id_down}")
                    if market_mid:
                        state.last_price = market_mid
                else:
                    logger.warning("[WINDOW] Could not fetch new market — keeping old token IDs")

            # Evaluate signal
            if not state.window.signal_evaluated and not state.window.traded:
                signal, rejection = evaluate_signal(state, now_ms)
                if signal:
                    logger.info(
                        f"[SIGNAL] {signal.direction.value} — {signal.reason} "
                        f"(PTB={signal.ptb_used:.2f}, trend={signal.trend})"
                    )
                    success = await trader.on_signal(state, signal)
                    if success:
                        logger.info(f"[TRADE] Executed {signal.direction.value} trade")
                    else:
                        logger.warning(f"[TRADE] Failed")
                elif rejection:
                    logger.debug(f"[SIGNAL] Rejected: {rejection.reason}")

            # Update Polymarket odds
            odds_up = await poly_client.get_odds(token_id_up)
            if odds_up is not None:
                state.poly_up_odds = float(odds_up)
            odds_down = await poly_client.get_odds(token_id_down)
            if odds_down is not None:
                state.poly_down_odds = float(odds_down)

            dashboard.broadcast(dashboard._state_snapshot())

    eval_task = asyncio.create_task(evaluation_loop())

    # Run until interrupted
    try:
        await asyncio.gather(binance_task, chainlink_task, eval_task, dashboard_task, fallback_task)
    except asyncio.CancelledError:
        logger.info("[MAIN] Shutting down...")
        poly_client.stop_ws_feed()
        await binance.stop()


if __name__ == "__main__":
    asyncio.run(main())