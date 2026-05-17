---
name: POLY_HFT
description: "Polymarket BTC 5m Breakout trading bot — Strategy B, live trading via Polymarket CLOB, EOA wallet (sig type 0)"
type: project
originSessionId: 1d075090
---

# POLY_HFT — Polymarket BTC Trading Bot

**Path:** `/Users/kenrickowen/Documents/POLY_HFT`
**Type:** Python trading bot

## Purpose

A live Polymarket trading bot implementing Strategy B (5m BTC Breakout):
- Watches Binance BTC price via WebSocket + Chainlink oracle (REST API)
- Detects price breakouts from the 5-minute window open (PTB)
- Places UP/DOWN trades on Polymarket CLOB using py-clob-client-v2
- Auto-fetches active BTC 5m market token IDs from Gamma API on every new window
- Dashboard at http://localhost:8080 (FastAPI + WebSocket)

## Architecture

```
polymarket_python/
├── config.py              # All constants, API URLs, timing, position sizing
├── models.py              # Candle, WindowState, Signal, AppState, Trade, enums
├── scheduler.py           # 5m window timing calculations
├── state.py               # Window reset, PTB capture, first-in-window tracking
├── indicators.py          # ATR, volume SMA, wick checks
├── guardrails.py          # Time-based trade restrictions
├── strategy.py            # Strategy B signal evaluation
├── binance_client.py      # Binance WebSocket kline + ticker, REST seed
├── chainlink_client.py    # Chainlink Data Engine REST API (not web3/Infura)
├── polymarket_client.py   # py-clob-client-v2 with EOA (sig type 0) + WebSocket feed
├── trader.py              # Trade execution + Trade record creation
├── dashboard.py           # FastAPI + WebSocket HTML dashboard (Trade History included)
├── main.py                # Main event loop wiring all components
└── price_fallback.py      # CoinGecko fallback BTC price

.env                       # PRIVATE_KEY, FUNDER_ADDRESS, INFURA_URL, TOKEN_ID_UP/DOWN
run.py                     # Entry point
requirements.txt           # Dependencies
```

## Key Decisions

- **EOA signature type 0** — wallet pays its own gas, no Magic Link
- **py-clob-client-v2** for Polymarket CLOB — L1→L2 auth via `create_or_derive_api_creds()`
- **Auto-fetch market** from Gamma API on startup AND on every new 5m window (token IDs change per window)
- **Polymarket WebSocket** — subscribes to `book` channel for real-time bid/ask via `wss://ws-subscriptions-clob.polymarket.com/ws/market`, with REST fallback. Auto-reconnects.
- **Trend from first 3 candles INSIDE window**, 4th candle as trigger
- **PTB captured at window open** from Binance ticker OR Chainlink (first wins)
- **Guardrails**: no trades first 60s, no trades in final 90s
- **Position sizing**: 1% of capital per trade
- **Chainlink**: uses Data Engine REST API (`data.chain.link/api/live-data-engine-stream-data`) NOT web3/Infura. Stale check on `validAfterTs` (60s threshold).
- **Dashboard**: dark theme, vanilla JS, WebSocket 1s updates, Trade History table, no external deps

## Wallet

- **Address:** `0xa910a5042211815f5FC332EA02399426486De58a`
- **Private key** stored in `.env` (never commit)
- Needs: **POL** (gas) + **pUSD** (trading capital)

## Known Issues / Status (2026-05-17)

- Binance WebSocket is geo-blocked in current network — Binance fallback (CoinGecko) not yet fully wired
- Chainlink feed address updated to Data Engine REST API (feed ID: `0x00039d9e45394f473ab1f050a1b963e6b05351e52d71e507509ada0c95ed75b8`)
- Polymarket WebSocket now auto-reconnects with certifi SSL context
- Token IDs now refresh every 5min at window boundary (was a 404 bug — stale token IDs)
- Dashboard shows Trade History table at bottom

## Files

- `.env` — wallet and API credentials
- `.gitignore` — excludes `.env`
- `Documentation/strategy.md` — Strategy B spec
- `Documentation/Polymarket_official.md` — Polymarket API docs