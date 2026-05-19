# Strategy B — 5m BTC Breakout

## Overview

A 5-minute window breakout trading strategy on Polymarket BTC prediction markets (UP/DOWN). Primary price feed is **Bybit V5 WebSocket** (BTCUSDT kline + ticker). Detects price breakouts from the window open price (PTB) and places UP/DOWN trades on Polymarket CLOB.

Two active strategies are available: **T3** (default) and **Legacy**. A third "current" strategy is preserved in code but hidden from the UI.

---

## Core Concepts

### 5-Minute Windows
- Windows anchored to Polymarket market timing (every 5 minutes)
- One trade per window maximum

### PTB (Previous Trade Baseline)
- Captured at window open (T+0) from Bybit ticker
- Acts as the breakout reference price for both UP and DOWN signals

### Active Strategies

#### T3 Strategy (`strategy_T3.py`) — DEFAULT

- **Trend candles**: T+1, T+2, T+3 (first 3 candles inside window)
- **Homogeneity check**: all 3 candles must be the same color
  - 🟢🟢🟢 → Bullish
  - 🔴🔴🔴 → Bearish
  - Mixed colors → no trade (rejected as `MixedColors`)
- **Trigger**: Candle 3 (T+3, index 2)
- **Fire time**: when current time >= (Candle 3 close time − 5 seconds)
- **Fire price**: `state.last_price` (streaming Bybit ticker) if Candle 3 still forming, else `trigger.close`
- **Signal reasons**: `T3_Breakout_UP`, `T3_Breakout_DN`

**Example timing (window 17:00–17:05):**
| Time | Event |
|------|-------|
| 17:00 | Window opens, PTB captured |
| 17:01 | Candle 1 (T+1) opens |
| 17:02 | Candle 2 (T+2) opens |
| 17:03 | Candle 3 (T+3) opens — trend determined |
| 17:03:55 | Fire window opens (5s before Candle 3 closes) |
| 17:04 | Candle 4 (T+4) opens — signal fires if conditions met |

#### Legacy Strategy (`strategy_legacy.py`)

- **Trend candles**: Last 3 pre-window 1m klines (before T+0)
- **Trigger**: First candle inside the window (T+1)
- **Wick check**: `wick < body × 2.0 OR wick < ATR × 0.3`
- **Signal reasons**: `B_VolBreakout_UP_PTB`, `B_Breakout_UP_PTB`, `B_VolBreakout_DN_PTB`, `B_Breakout_DN_PTB`

#### Current Strategy (`strategy.py` / `evaluate_signal_current`) — CODE ONLY

- **Trend candles**: First 3 candles inside window
- **Trigger**: 4th candle inside window (index 3)
- **Wick check**: `wick < body × 0.5 OR wick < ATR × 0.1`
- **Signal reasons**: `B_Breakout_UP_PTB`, `B_Breakout_DN_PTB`
- Preserved in code but not exposed in the UI dashboard dropdown

---

## Signal Logic — T3 Strategy

Signal fires when ALL of these conditions are true:

1. **Homogeneous color**: Candles T+1, T+2, T+3 are all the same color → `MixedColors` if not
2. **Trigger ready**: current time >= (Candle 3 close time − 5 seconds)
3. **Trigger color matches trend**: green for bullish, red for bearish
4. **Not a doji**: trigger body > 0
5. **Wick check**: adverse wick < body × 0.5 OR both wicks < ATR × 0.1
6. **PTB breakout**:
   - UP signal: fire price > PTB (bullish trend + price above open)
   - DOWN signal: fire price < PTB (bearish trend + price below open)
7. **Odds ready**: both `poly_up_odds` and `poly_down_odds` present
8. **Window state**: not already signaled or traded

---

## Guardrails

- No trades in final 90 seconds of window (T+210s)
- One trade per window (no double-trading)
- Indicators must be valid (ATR > 0, vol_sma > 0)

---

## Position Sizing

- $1 per trade (configurable via `FIXED_TRADE_USD`)

---

## Signal Rejection Types

| Reason | Description |
|--------|-------------|
| WindowUnset | No active window |
| AlreadyTraded | Position already taken this window |
| AlreadySignaled | Window already triggered a signal |
| PtbNotReady | PTB price not yet captured |
| CutoffGuard | Window time > 210s elapsed |
| NotEnoughCandles | Fewer than 3 candles inside window |
| MixedColors | T+1/T+2/T+3 are not all the same color (T3 only) |
| TooEarly | Fire window not yet open (< 5s before Candle 3 close) |
| IndicatorsInvalid | ATR or other indicators invalid |
| ColorMismatch | Trigger candle color ≠ trend direction |
| TriggerDoji | Trigger candle is a doji (body = 0) |
| WickFailed | Wick check failed |
| PtbSideFailed | Price not on correct side of PTB for signal direction |

---

## Architecture

```
polymarket_python/
├── config.py              # All constants and env var defaults
├── models.py              # Candle, WindowState, Signal, AppState, Trade
├── scheduler.py           # 5m window timing calculations
├── state.py               # Window reset, PTB capture, first-in-window tracking
├── indicators.py          # ATR, volume SMA, wick checks
├── guardrails.py          # Time-based trade restrictions
├── strategy.py            # Dispatcher (t3 / legacy / current)
├── strategy_T3.py        # T3 strategy — Candle 3 trigger, homogeneous color
├── strategy_legacy.py     # Legacy strategy — pre-window trend, Candle 1 trigger
├── bybit_client.py        # Bybit V5 WebSocket (kline + ticker), REST seed (primary feed)
├── binance_client.py      # Binance WebSocket (kline + ticker) — fallback
├── polymarket_client.py   # Polymarket CLOB API + WebSocket book feed; all SDK calls in asyncio.to_thread
├── polymarket_public_client.py  # Public Gamma API market discovery + odds
├── trader.py              # Trade execution
├── trade_store.py         # CSV trade history persistence
├── redemption.py          # On-chain CTF position redemption (PolymarketRedeemer)
├── wallet_balances.py     # POL + USDC.e + pUSD balance reader
├── dashboard.py           # FastAPI HTTP + WebSocket streaming, strategy dropdown
├── main.py                # Main event loop + background redemption loop
└── price_fallback.py      # CoinGecko fallback BTC price
```

---

## Strategy Switching

- **Dashboard**: dropdown select — "T3 (Candle 3)" or "Legacy"
- **API**: `POST /config/strategy_mode` with body `t3` or `legacy`
- **Default**: `t3` (set in `models.py`)

---

## Key Differences from Legacy

| | T3 | Legacy |
|---|---|---|
| Trend candles | T+1, T+2, T+3 (inside window) | Pre-window last 3 klines |
| Trigger | Candle 3 (T+3) | Candle 1 (T+1) |
| Fire time | 5s before Candle 3 closes | When trigger candle closes |
| Color check | Homogeneous (all same color) | Trigger must match trend |
| Wick threshold | body × 0.5 | body × 2.0 |