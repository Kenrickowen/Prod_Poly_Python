# Strategy B — 5m BTC Breakout

## Overview

A 5-minute window breakout trading strategy on Polymarket BTC prediction markets (UP/DOWN). Primary price feed is **Bybit V5 WebSocket** (BTCUSDT kline + ticker), with Chainlink BTC/USD oracle as secondary reference. Detects price breakouts from the window open price (PTB) and places UP/DOWN trades on Polymarket CLOB.

---

## Core Concepts

### 5-Minute Windows
- Windows anchored to Polymarket market timing
- One trade per window maximum

### PTB (Previous Trade Baseline)
- Captured at window open from Bybit ticker OR Chainlink (first one wins)
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
├── bybit_client.py         # Bybit V5 WebSocket (kline + ticker), REST seed (primary feed)
├── binance_client.py       # Binance WebSocket (kline + ticker) — fallback
├── chainlink_client.py    # Chainlink BTC price feed (Data Engine REST API)
├── polymarket_client.py    # Polymarket CLOB API (auth, order placement) + WebSocket book feed
├── polymarket_public_client.py  # Public Gamma API market discovery + odds
├── indicators.py          # ATR, volume SMA computation
├── strategy.py            # Strategy B signal evaluation
├── guardrails.py          # Time-based trade restrictions
├── scheduler.py           # 5m window timing calculations
├── trader.py              # Trade execution
├── trade_store.py         # CSV trade history persistence (with redemption fields)
├── redemption.py          # On-chain CTF position redemption (PolymarketRedeemer)
├── wallet_balances.py      # POL + USDC.e + pUSD balance reader
├── dashboard.py           # FastAPI HTTP server + WebSocket streaming
├── main.py                # Main event loop + background redemption loop
└── price_fallback.py      # CoinGecko fallback BTC price
```

---

## Key Differences from Rust Version

1. No paper mode — live trading only
2. Uses py-clob-client-v2 for EIP-712 order signing
3. Signature type **EOA (0)** for direct wallet signing (not Magic Link)