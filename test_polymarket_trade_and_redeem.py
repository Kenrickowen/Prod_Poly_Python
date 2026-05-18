#!/usr/bin/env python3
"""Submit a guarded $1 Polymarket BTC 5m test trade and optionally wait for redemption."""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
load_dotenv(Path(__file__).parent / ".env")

from polymarket_python.config import FIXED_TRADE_USD, MIN_POLYMARKET_SHARES
from polymarket_python.models import SignalDirection, Trade
from polymarket_python.polymarket_client import PolymarketClient
from polymarket_python.polymarket_public_client import fetch_current_btc_odds
from polymarket_python.redemption import PolymarketRedeemer, now_ms
from polymarket_python.trade_store import append_trade, save_trade_history, load_trade_history
from polymarket_python.wallet_balances import WalletBalanceClient


def choose_side(market, up_odds: float | None, down_odds: float | None, amount_usd: float, direction: str):
    max_eligible_price = amount_usd / MIN_POLYMARKET_SHARES
    choices = []
    if up_odds is not None:
        choices.append(("UP", market.token_id_up, float(up_odds)))
    if down_odds is not None:
        choices.append(("DOWN", market.token_id_down, float(down_odds)))

    if direction != "auto":
        choices = [c for c in choices if c[0].lower() == direction]

    eligible = [c for c in choices if 0 < c[2] <= max_eligible_price]
    if not eligible:
        return None, max_eligible_price

    eligible.sort(key=lambda x: x[2])
    return eligible[0], max_eligible_price


async def wait_for_redemption(trade: Trade, poll_secs: float) -> None:
    redeemer = PolymarketRedeemer()
    print("Waiting for CTF resolution and redemption eligibility...")
    while True:
        result = await asyncio.to_thread(
            redeemer.redeem,
            condition_id=trade.condition_id,
            token_id_up=trade.token_id_up,
            token_id_down=trade.token_id_down,
            neg_risk=trade.neg_risk,
            wait_for_receipt=True,
        )
        trade.redemption_checked_ms = now_ms()
        if result.redeemed:
            trade.redemption_tx = result.tx_hash
            trade.settled = True
            trade.redemption_error = ""
            print(f"Redeemed/burned resolved position: {result.tx_hash}")
            trades = [t for t in load_trade_history() if t.timestamp_ms != trade.timestamp_ms]
            save_trade_history([trade, *trades])
            return

        trade.redemption_error = result.reason
        trades = [t for t in load_trade_history() if t.timestamp_ms != trade.timestamp_ms]
        save_trade_history([trade, *trades])
        print(f"Not redeemable yet: {result.reason}")
        await asyncio.sleep(poll_secs)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--amount", type=float, default=FIXED_TRADE_USD, help="USDC amount to spend")
    parser.add_argument("--direction", choices=["auto", "up", "down"], default="auto")
    parser.add_argument("--execute", action="store_true", help="Actually submit the order")
    parser.add_argument("--wait-eligible", action="store_true", help="Wait until $1 satisfies the active market minimum")
    parser.add_argument("--max-wait-secs", type=float, default=600)
    parser.add_argument("--wait-redemption", action="store_true", help="Wait and redeem/burn after resolution")
    parser.add_argument("--poll-secs", type=float, default=20)
    args = parser.parse_args()

    balances = WalletBalanceClient().fetch()
    started = time.time()

    while True:
        market, up_odds, down_odds = await fetch_current_btc_odds()
        if market is None:
            print("No active BTC 5m market found")
            return 1

        side, max_price = choose_side(market, up_odds, down_odds, args.amount, args.direction)
        if side is not None or not args.wait_eligible:
            break

        if time.time() - started >= args.max_wait_secs:
            break

        print(
            f"No eligible side yet for ${args.amount:.2f}; "
            f"UP={up_odds} DOWN={down_odds}, need price <= {max_price:.4f}. Waiting..."
        )
        await asyncio.sleep(args.poll_secs)

    print(f"Market: {market.question}")
    print(f"Slug: {market.slug}")
    print(f"UP={up_odds} DOWN={down_odds}")
    print(f"Wallet: POL={balances.pol:.6f} USDC={balances.usdc:.2f} USDC.e={balances.usdce:.2f} pUSD={balances.pusd:.2f}")
    print(f"${args.amount:.2f} test can only satisfy {MIN_POLYMARKET_SHARES:g} share min at price <= {max_price:.4f}")

    if side is None:
        print("No eligible side for a strict $1 trade right now. Try again when one outcome is cheap enough.")
        return 2

    direction, token_id, odds = side
    shares = args.amount / odds
    print(f"Selected {direction}: price={odds:.4f}, estimated shares={shares:.2f}")

    if not args.execute:
        print("Dry run only. Add --execute to submit the live $1 market order.")
        return 0

    client = PolymarketClient()
    response = await client.place_market_order(token_id, "BUY", args.amount)
    if not response:
        print("Order failed or was rejected. No trade recorded.")
        return 1

    order_id = ""
    if isinstance(response, dict):
        order_id = str(response.get("orderID") or response.get("orderId") or response.get("id") or "")

    trade = Trade(
        timestamp_ms=int(time.time() * 1000),
        direction=SignalDirection.UP if direction == "UP" else SignalDirection.DOWN,
        token_id=token_id,
        price=odds,
        size=args.amount,
        condition_id=market.condition_id,
        market_slug=market.slug,
        order_id=order_id,
        signal_reason="manual_test_trade",
        signal_trend="manual",
        token_id_up=market.token_id_up,
        token_id_down=market.token_id_down,
        neg_risk=market.neg_risk,
    )
    append_trade(trade)
    print(f"Order submitted and recorded. Response: {response}")

    if args.wait_redemption:
        await wait_for_redemption(trade, args.poll_secs)

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
