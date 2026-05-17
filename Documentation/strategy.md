# Strategy B — 5m BTC Breakout

## Overview

A 5-minute window breakout trading strategy on Polymarket BTC prediction markets (UP/DOWN). Watches Binance BTC price via WebSocket + Chainlink oracle, detects price breakouts from the window open price (PTB), and places UP/DOWN trades on Polymarket CLOB.

---

## Core Concepts

### 5-Minute Windows
- Windows anchored to Polymarket market timing
- One trade per window maximum

### PTB (Previous Trade Baseline)
- Captured at window open from Binance ticker OR Chainlink (first one wins)
- Acts as the breakout reference price

### Trend Detection
- Uses first 3 candles INSIDE the window (not before)
- Example: window 17:00-17:05 → candles 17:00-17:01, 17:01-17:02, 17:02-17:03
- **Bullish**: last close > 3rd-back open (e.g., close of 17:02-17:03 > open of 17:00-17:01)
- **Bearish**: last close < 3rd-back open
- **Flat**: no trend

<!-- LEGACY (incorrect — pre-window implies before window, but candles are INSIDE) -->
<!-- OLD: Uses last 3 pre-window 1m candles -->
<!-- OLD: Bullish: last close > 3rd-back open -->
<!-- OLD: Bearish: last close < 3rd-back open -->
<!-- OLD: Flat: no trend -->

### Trigger Candle
- The 4th candle inside the window (e.g., 17:03-17:04 for window 17:00-17:05)
- Must match the trend color (green for bullish, red for bearish)
- Must break PTB: close > PTB for UP, close < PTB for DOWN

---

## Signal Logic

Signal fires when ALL of these conditions are true:

1. **Trend**: Bullish or Bearish (not Flat) using first 3 candles of window (17:00-17:03)
2. **Trigger**: 4th candle inside window (17:03-17:04), color matches trend
3. **PTB Side Check**:
   - UP signal: trigger.close > PTB (bullish + price broke above open)
   - DOWN signal: trigger.close < PTB (bearish + price broke below open)
4. **Wick Check**: adverse wick < body × 0.5 OR both wicks < ATR × 0.1
5. **Chainlink Guard**: trigger forms after 60s into window (candle 4+)
6. **Odds Ready**: both `poly_up_odds` and `poly_down_odds` are present
7. **Window State**: not already signaled or traded

---

## Guardrails

- No trades in final 90 seconds of window
- One trade per window (no double-trading)
- First 60 seconds of window: no trades (chainlink guard active)
- Price disagreement between Binance and Chainlink: reject signal

---

## Position Sizing

- 1% of capital per trade

---

## Signal Rejection Types (18 reasons)

| Reason | Description |
|--------|-------------|
| AlreadySignaled | Window already triggered a signal |
| AlreadyTraded | Position already taken this window |
| WindowUnset | No active window |
| TooEarly | Chainlink guard still active (< 60s) |
| PtbNotReady | PTB price not yet captured |
| OddsNotReady | Polymarket odds not available |
| IndicatorsInvalid | ATR or other indicators invalid |
| NotEnoughCandles | First 3 candles of window not yet complete |
| TriggerNotReady | Trigger candle not yet formed |
| TrendFlat | No clear trend direction |
| TriggerDoji | Trigger candle is a doji |
| ColorMismatch | Trigger candle color ≠ trend |
| VolumeLow | Volume below threshold |
| WickFailed | Wick check failed |
| PriceDisagreement | Binance/Chainlink price mismatch |
| PtbSideFailed | Price not on correct side of PTB |
| ChainlinkGuard | In 60s guard window |

---

## Architecture (Python Rewrite)

```
polymarket_python/
├── config.py              # All constants and env var defaults
├── models.py              # Candle, WindowState, Signal, AppState
├── binance_client.py      # Binance WebSocket (kline + ticker), REST seed
├── chainlink_client.py    # Chainlink BTC price feed
├── polymarket_client.py    # Polymarket CLOB API (auth, order placement)
├── polymarket_ws.py       # Polymarket orderbook WebSocket
├── indicators.py          # ATR, volume SMA computation
├── strategy.py            # Strategy B signal evaluation
├── guardrails.py          # Time-based trade restrictions
├── scheduler.py           # 5m window timing calculations
├── trader.py              # Trade execution (live only)
├── state.py               # Window reset, PTB capture, state management
├── dashboard.py           # FastAPI HTTP server + WebSocket streaming
└── main.py                # Main event loop
```

---

## Key Differences from Rust Version

1. No paper mode — live trading only
2. Uses py_order_utils for EIP-712 order signing
3. Signature type POLY_PROXY (1) for Magic Link authentication
4. L2 HMAC: timestamp + method + path + body (full JSON for POST)
5. No raw RPC balance — uses CLOB /balance-allowance endpoint