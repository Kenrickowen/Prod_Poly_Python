---
name: POLY_HFT
description: "Polymarket BTC 5m Breakout trading bot — Strategy B, live trading via Polymarket CLOB, EOA wallet (sig type 0), Bybit price feed, auto-redeem"
type: project
originSessionId: 1d075090
---

# POLY_HFT — Polymarket BTC Trading Bot

**Path:** `/Users/kenrickowen/Documents/POLY_HFT`
**Type:** Python trading bot (asyncio)

## Purpose

A live Polymarket trading bot implementing Strategy B (5m BTC Breakout):
- Primary price feed: **Bybit V5 WebSocket** (kline + ticker) — BTCUSDT
- Fallback: CoinGecko REST → Binance REST → Polymarket market mid
- Detects price breakouts from the 5-minute window open (PTB)
- Places UP/DOWN trades on Polymarket CLOB using py-clob-client-v2
- Auto-fetches active BTC 5m market token IDs from Gamma API on every new window
- **Background auto-redeem** for resolved positions (on-chain CTF redemption)
- Dashboard at http://localhost:8080 (FastAPI + WebSocket)
- Trade history persisted to CSV with redemption status tracking

## Architecture

```
polymarket_python/
├── config.py              # All constants, API URLs, contract addresses, timing, position sizing
├── models.py              # Candle, WindowState, Signal, AppState, Trade, enums
├── scheduler.py           # 5m window timing calculations
├── state.py               # Window reset, PTB capture, first-in-window tracking
├── indicators.py          # ATR, volume SMA, wick checks
├── guardrails.py          # Time-based trade restrictions
├── strategy.py            # Strategy B signal evaluation
├── binance_client.py       # Binance WebSocket kline + ticker, REST seed (fallback)
├── bybit_client.py         # Bybit V5 WebSocket kline + ticker, REST seed + certifi SSL (primary feed)
├── chainlink_client.py     # Chainlink Data Engine REST API (live BTC/USD)
├── polymarket_client.py    # py-clob-client-v2 with EOA (sig type 0) + WebSocket feed
├── polymarket_public_client.py  # Public Gamma API market discovery + odds fetching
├── trader.py              # Trade execution + Trade record creation
├── trade_store.py         # CSV persistence for trade history (incl. redemption fields)
├── redemption.py          # PolymarketRedeemer — on-chain CTF position redemption
├── wallet_balances.py      # Read POL + USDC.e + pUSD balances via Polygon RPC
├── dashboard.py           # FastAPI + WebSocket HTML dashboard
├── price_fallback.py      # CoinGecko fallback BTC price
├── main.py                # Main event loop wiring all components + redemption loop

.env                       # PRIVATE_KEY, FUNDER_ADDRESS, INFURA_URL
run.py                     # Entry point
redeem_polymarket_position.py  # Standalone redemption CLI
check_bybit_price.py        # CLI: check Bybit BTC price
check_poly_odds.py         # CLI: check Polymarket odds
run_bybit_dashboard.py     # Standalone Bybit dashboard
tests/
├── test_strategy.py
├── test_strategy_full.py  # Comprehensive signal + rejection tests (8 tests, all passing)
├── test_trade_store.py
└── test_public_clients.py

Documentation/
├── strategy.md
└── Polymarket_official.md
```

## Key Decisions

- **EOA signature type 0** — wallet pays its own gas, no Magic Link
- **py-clob-client-v2** for Polymarket CLOB — L1→L2 auth via `create_or_derive_api_creds()`
- **Bybit V5 WebSocket** as primary price feed (replaced Binance after geo-blocking)
  - Subscribes to `tickers.BTCUSDT` + `kline.1.BTCUSDT`
  - Seeds last 60 klines via Bybit REST on connect
- **Auto-redeem loop** (in `main.py`, `redemption_loop()`):
  - Polls every `REDEMPTION_POLL_SECS` (default 30s)
  - Checks each unsettled trade against CTF `payoutDenominator`
  - Calls `redeemPositions` via collateral adapter when condition resolves
  - Updates `settled`, `redemption_tx`, `redemption_error` on Trade record
  - Controlled by `REDEMPTION_ENABLED` env var
- **Auto-fetch market** from Gamma API on startup AND on every new 5m window (token IDs change per window)
- **Polymarket WebSocket** — subscribes to `book` channel for real-time bid/ask
- **Trend from first 3 candles INSIDE window**, 4th candle as trigger
- **PTB captured at window open** from first price update (Bybit ticker or chainlink — first wins)
- **Guardrails**: no trades first 60s, no trades in final 90s
- **Position sizing**: 1% of capital per trade
- **Trade history CSV** at `data/trade_history.csv` — includes redemption fields
- **Dashboard**: dark theme, vanilla JS, WebSocket 1s updates, Trade History table, redemption status shown

## Contract Addresses (Polygon mainnet)

| Contract | Address |
|----------|---------|
| Polymarket CTF | `0x4D97DCd97eC945f40cF65F87097ACe5EA0476045` |
| Standard Collateral Adapter | `0xAdA100Db00Ca00073811820692005400218FcE1f` |
| Neg-Risk Collateral Adapter | `0xadA2005600Dec949baf300f4C6120000bDB6eAab` |
| pUSD | `0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB` |
| USDC.e | `0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174` |
| USDC | `0x3c499c542cef5e3811e1192ce70d8cc03d5c3359` |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PRIVATE_KEY` | — | Wallet private key |
| `FUNDER_ADDRESS` | — | Wallet address |
| `INFURA_URL` | — | Polygon RPC URL |
| `TOKEN_ID_UP/DOWN` | auto | Token IDs (auto-fetched if unset) |
| `REDEMPTION_ENABLED` | `true` | Enable auto-redeem |
| `REDEMPTION_POLL_SECS` | `30` | Redemption poll interval |
| `REDEMPTION_MAX_GAS_GWEI` | `250` | Max gas price for redemption |
| `REDEMPTION_GAS_LIMIT` | `350000` | Gas limit for redemption tx |
| `BYBIT_WS_URL` | `wss://stream.bybit.com/v5/public/linear` | Bybit WebSocket |
| `BYBIT_REST_URL` | `https://api.bybit.com` | Bybit REST |
| `BYBIT_SYMBOL` | `BTCUSDT` | Bybit symbol |
| `POLY_ODDS_POLL_SECS` | `5` | Polymarket odds poll interval |
| `WALLET_BALANCE_POLL_SECS` | `60` | Wallet balance poll interval |
| `DASHBOARD_HOST` | `0.0.0.0` | Dashboard bind host |
| `DASHBOARD_PORT` | `8080` | Dashboard port |

## Wallet

- **Address:** `0xa910a5042211815f5FC332EA02399426486De58a`
- **Private key** stored in `.env` (never commit)
- Needs: **POL** (gas) + **pUSD** (trading capital)

## Known Issues / Status (2026-05-18)

- Binance WebSocket is geo-blocked — Bybit V5 WebSocket is primary feed
- Chainlink uses Data Engine REST API (`data.chain.link/api/live-data-engine-stream-data`)
- Token IDs refresh every 5min at window boundary (new slug = new token IDs)
- Dashboard shows Trade History table with redemption status (settled, tx, error)
- Redemption loop runs in background, updates CSV on each check
- Standalone `redeem_polymarket_position.py` for manual redemption with `--execute --wait`
- **Bug fixed (2026-05-18):** `find_trigger_candle()` in `strategy.py` was off-by-one — returned `inside[2]` (3rd candle) instead of `inside[3]` (4th candle, the actual trigger). Fixed to return `inside[3]`.
- **Bug fixed (2026-05-18):** Bybit WebSocket SSL verification now uses `certifi.where()` cert bundle (macOS SSL cert issue).
- **Tests updated (2026-05-18):** `test_strategy.py` and new `test_strategy_full.py` cover signal triggering + all rejection paths.