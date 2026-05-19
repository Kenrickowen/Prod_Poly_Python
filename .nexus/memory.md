---
name: POLY_HFT
description: "Polymarket BTC 5m Breakout trading bot — Strategy B (current + legacy), live trading via Polymarket CLOB, POLY_1271 deposit wallet (sig type 3), Bybit price feed, auto-redeem"
type: project
originSessionId: 1d075090
---

# POLY_HFT — Polymarket BTC Trading Bot

**Path:** `/Users/kenrickowen/Documents/POLY_HFT`
**Type:** Python trading bot (asyncio)

## Purpose

A live Polymarket trading bot implementing Strategy B (5m BTC Breakout):
- Primary price feed: **Bybit V5 WebSocket** (kline + ticker) — BTCUSDT
- Fallback: CoinGecko REST → Bybit REST → Polymarket market mid
- Detects price breakouts from the 5-minute window open (PTB)
- Places UP/DOWN trades on Polymarket CLOB using py-clob-client-v2
- Auto-fetches active BTC 5m market token IDs from Gamma API on every new window
- **Background auto-redeem** for resolved positions (on-chain CTF redemption)
- Dashboard at http://localhost:8080 (FastAPI + WebSocket)
- Trade history persisted to CSV with redemption status tracking

---

## Architecture

```
polymarket_python/
├── config.py              # All constants, API URLs, contract addresses, timing, position sizing
├── models.py              # Candle, WindowState, Signal, AppState, Trade, enums
├── scheduler.py           # 5m window timing calculations
├── state.py               # Window reset, PTB capture, first-in-window tracking
├── indicators.py           # ATR, volume SMA, wick checks (current strategy)
├── guardrails.py           # Time-based trade restrictions
├── strategy.py             # Dispatcher (current + legacy + t3)
├── strategy_T3.py           # T+3 strategy — fires 5s before Candle 3 closes, homogeneous color check
├── strategy_legacy.py      # Strategy B legacy (from Rust breakout.rs)
├── binance_client.py       # Binance WebSocket kline + ticker, REST seed (fallback)
├── bybit_client.py         # Bybit V5 WebSocket kline + ticker, REST seed + certifi SSL (primary feed)
├── polymarket_client.py    # py-clob-client-v2 with POLY_1271 deposit wallet (sig type 3) + WebSocket feed; all sync SDK calls wrapped in asyncio.to_thread
├── polymarket_public_client.py  # Public Gamma API market discovery + odds fetching
├── trader.py               # Trade execution + Trade record creation
├── trade_store.py          # CSV persistence for trade history (incl. redemption fields)
├── redemption.py           # PolymarketRedeemer — on-chain CTF position redemption
├── wallet_balances.py      # Read POL + USDC.e + pUSD balances via Polygon RPC
├── dashboard.py            # FastAPI + WebSocket HTML dashboard + strategy toggle
├── price_fallback.py       # CoinGecko fallback BTC price
├── main.py                 # Main event loop wiring all components + redemption loop

.env                       # PRIVATE_KEY, FUNDER_ADDRESS, INFURA_URL
run.py                     # Entry point
redeem_polymarket_position.py  # Standalone redemption CLI
check_bybit_price.py       # CLI: check Bybit BTC price
check_poly_odds.py         # CLI: check Polymarket odds
run_bybit_dashboard.py     # Standalone Bybit dashboard
test_polymarket_trade_and_redeem.py  # Manual trade test CLI
tests/
├── test_strategy.py
├── test_strategy_full.py   # Comprehensive signal + rejection tests (8 tests, all passing)
├── test_trade_store.py
└── test_public_clients.py

Documentation/
├── strategy.md
└── Polymarket_official.md
```

---

## Strategy Toggle (T3 vs Legacy)

The bot supports switching between two active strategies at runtime via the dashboard dropdown. The "current" strategy is preserved in code but hidden from the UI.

### T3 Strategy (`strategy_T3.py` / `evaluate_signal_T3`) — DEFAULT
- **Trend candles**: Candles T+1, T+2, T+3 (first 3 inside window)
- **Homogeneity check**: all 3 candles must be same color — mixed = no trade
- **Trigger**: Candle 3 (index 2, T+3)
- **Fire time**: within 5s of Candle 3 close (`is_trigger_ready()`)
- **Fire price**: `state.last_price` if trigger still forming, else `trigger.close`
- **Signal reasons**: `T3_Breakout_UP`, `T3_Breakout_DN`

### Legacy Strategy (`strategy_legacy.py` / `evaluate_signal_legacy`)
- **Trend candles**: Last 3 candles *before* window start (pre-window 1m klines)
- **Trigger**: First candle *inside* the window
- **Wick check**: `wick < body × 2.0 OR wick < ATR × 0.3`
- **Volume check**: Does NOT reject signal — only changes reason code
- **Signal reasons**: `B_VolBreakout_UP_PTB`, `B_Breakout_UP_PTB`, `B_VolBreakout_DN_PTB`, `B_Breakout_DN_PTB`
- **PTB preference**: Prefers `ptb_binance` if available

### Switching
- **Dashboard**: dropdown select — "T3 (Candle 3)" or "Legacy"
- **API**: `POST /config/strategy_mode` with body `t3` or `legacy`
- **API**: `GET /config/strategy_mode` to check current mode
- State field: `AppState.strategy_mode` (default `"t3"`)

---

## Key Decisions

- **POLY_1271 signature type 3** — required for deposit wallets created via Polymarket UI; `funder` must match the address used to derive the API key (BUILDER_ADDRESS); `create_or_derive_api_key()` derives L2 API credentials on init
- **py-clob-client-v2** for Polymarket CLOB — L1→L2 auth via `create_or_derive_api_key()`
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
- **Strategy dispatch** via `evaluate_signal()` in `strategy.py` — routes to t3, legacy, or current based on `state.strategy_mode`
- **Dashboard strategy dropdown** — T3 (Candle 3, default) or Legacy; "current" (Candle 4) preserved in code but hidden from UI
- **PTB captured at window open** from first price update (Bybit ticker — first wins)
- **Guardrails**: no trades in final 90s (60s chainlink guard removed — 2026-05-19)
- **Position sizing**: $1 per trade (configurable via `FIXED_TRADE_USD`)
- **Trade history CSV** at `data/trade_history.csv` — includes redemption fields

---

## Contract Addresses (Polygon mainnet)

| Contract | Address |
|----------|---------|
| Polymarket CTF | `0x4D97DCd97eC945f40cF65F87097ACe5EA0476045` |
| Standard Collateral Adapter | `0xAdA100Db00Ca00073811820692005400218FcE1f` |
| Neg-Risk Collateral Adapter | `0xadA2005600Dec949baf300f4C6120000bDB6eAab` |
| pUSD | `0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB` |
| USDC.e | `0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174` |
| USDC | `0x3c499c542cef5e3811e1192ce70d8cc03d5c3359` |

---

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

---

## Wallet

- **EOA Address:** `0xa910a5042211815f5FC332EA02399426486De58a`
- **FUNDER_ADDRESS (API key address):** `0x8142f52147c840dad2b6dc1e2f3b8aa52b7e234c` — MUST match BUILDER_ADDRESS; POLY_1271 requires funder=API key address
- **Deposit wallet (NOT used):** `0x49Cf5f787f379553c5Eab25c890E0d7e9c80d4D5` — does NOT work as funder
- **Private key** stored in `.env` (never commit)
- **Balance types** (two separate systems):
  - **CLOB balance** (trading account): `client.get_balance_allowance(BalanceAllowanceParams(asset_type=AssetType.COLLATERAL))` — returns USDC deposited in Polymarket CLOB; currently ~5M USDC
  - **On-chain wallet balance** (`wallet_balances.py`): POL, USDC.e, USDC, pUSD via Polygon RPC at wallet address
  - Dashboard `current_balance` = on-chain `pusd` (NOT CLOB balance)
- **Needs**: **POL** (gas) + **USDC** (trading capital, must be deposited to CLOB separately)

---

## Known Issues / Status (2026-05-19)

- All bugs from 2026-05-19 **fixed and verified**: side assignment, balance_allowance params, FUNDER_ADDRESS mismatch
- **Manual test trades placed (2026-05-19)**: $1 UP orders fired via direct script (not via running bot) — confirmed POLY_1271 + BUILDER_ADDRESS as funder works correctly
- Binance WebSocket is geo-blocked — Bybit V5 WebSocket is primary feed
- Chainlink removed (2026-05-19): `chainlink_client.py` deleted, all chainlink references removed from `__init__.py`, `main.py`, `strategy.py`, `state.py`, `dashboard.py`, `models.py`; 60s trigger delay removed from strategy
- **Trade execution speed improvements (2026-05-19)**:
  - Evaluation loop sleep reduced from 5s to 0.5s
  - Duplicate `fetch_current_btc_odds()` call removed (was 6 HTTP calls/cycle, now 3)
  - All sync `py-clob-client-v2` SDK calls wrapped in `asyncio.to_thread()` (non-blocking): `get_spread`, `get_midpoint`, `get_market`, `get_balance`, `get_tick_size`, `get_neg_risk`, `create_and_post_order`, `create_and_post_market_order`
  - No more blocking event loop on Polymarket CLOB API calls

## POLY_HFT purpose and architecture

**Path:** `/Users/kenrickowen/Documents/POLY_HFT`
**Type:** Python trading bot (asyncio)

## Purpose
A live Polymarket trading bot implementing Strategy B (5m BTC Breakout):
- Primary price feed: **Bybit V5 WebSocket** (kline + ticker) — BTCUSDT
- Fallback: CoinGecko REST → Bybit REST → Polymarket market mid
- Detects price breakouts from the 5-minute window open (PTB)
- Places UP/DOWN trades on Polymarket CLOB using py-clob-client-v2
- Auto-fetches active BTC 5m market token IDs from Gamma API on every new window
- **Background auto-redeem** for resolved positions (on-chain CTF redemption)
- Dashboard at http://localhost:8080 (FastAPI + WebSocket)
- Trade history persisted to CSV with redemption status tracking


## POLY_HFT strategy toggle

## Strategy Toggle (Current vs Legacy)

### Current Strategy (`strategy.py` / `evaluate_signal_current`)
- **Trend candles**: First 3 candles *inside* the 5-minute window
- **Trigger**: 4th candle inside window (index 3)
- **Wick check**: `wick < body × 0.5 OR wick < ATR × 0.1`
- **Signal reasons**: `B_Breakout_UP_PTB`, `B_Breakout_DN_PTB`
- **PTB**: Uses `ptb` (any source, first wins)

### Legacy Strategy (`strategy_legacy.py` / `evaluate_signal_legacy`)
- **Trend candles**: Last 3 candles *before* window start (pre-window 1m klines)
- **Trigger**: First candle *inside* the window
- **Wick check**: `wick < body × 2.0 OR wick < ATR × 0.3`
- **Volume check**: Does NOT reject signal — only changes reason code
- **Signal reasons**: `B_VolBreakout_UP_PTB`, `B_Breakout_UP_PTB`, `B_VolBreakout_DN_PTB`, `B_Breakout_DN_PTB`
- **PTB preference**: Prefers `ptb_binance` if available

### Switching
- **Dashboard**: Green/red indicator badge + "Switch to Legacy/Current" button
- **API**: `POST /config/strategy_mode` with body `current` or `legacy`
- **API**: `GET /config/strategy_mode` to check current mode
- State field: `AppState.strategy_mode` (default `"current"`)


## POLY_HFT POLY_1271

**POLY_1271 signature type 3** — required for deposit wallets created via Polymarket UI; `funder` must match address used to derive API key (BUILDER_ADDRESS); `create_or_derive_api_key()` derives L2 API credentials on init


## POLY_HFT bybit feed

**Bybit V5 WebSocket** as primary price feed (replaced Binance after geo-blocking). Subscribes to `tickers.BTCUSDT` + `kline.1.BTCUSDT`. Seeds last 60 klines via Bybit REST on connect.


## POLY_HFT auto redeem loop

**Auto-redeem loop** (in `main.py`, `redemption_loop()`): Polls every `REDEMPTION_POLL_SECS` (default 30s), checks each unsettled trade against CTF `payoutDenominator`, calls `redeemPositions` via collateral adapter when condition resolves, updates `settled`, `redemption_tx`, `redemption_error` on Trade record. Controlled by `REDEMPTION_ENABLED` env var.


## POLY_HFT wallet addresses

**EOA Address:** `0xa910a5042211815f5FC332EA02399426486De58a`
**FUNDER_ADDRESS (API key address):** `0x8142f52147c840dad2b6dc1e2f3b8aa52b7e234c` — MUST match BUILDER_ADDRESS
**Deposit wallet (NOT used):** `0x49Cf5f787f379553c5Eab25c890E0d7e9c80d4D5`
Balance types: CLOB balance (trading account via `get_balance_allowance`) and on-chain wallet balance (POL, USDC.e, USDC, pUSD via Polygon RPC). Dashboard shows on-chain `pusd`.


## POLY_HFT status 2026-05-19

**All bugs from 2026-05-19 fixed and verified**: side assignment, balance_allowance params, FUNDER_ADDRESS mismatch. Manual test trades placed 2026-05-19: $1 UP orders fired via direct script — confirmed POLY_1271 + BUILDER_ADDRESS as funder works correctly. Binance WebSocket geo-blocked — Bybit V5 WebSocket is primary feed. Token IDs refresh every 5min at window boundary.

**Trade execution speed improvements (2026-05-19)**: Evaluation loop now polls every 0.5s (was 5s). Duplicate HTTP call removed. All sync Polymarket SDK calls run in thread pool via `asyncio.to_thread()`.

**T3 strategy added (2026-05-19)**: `strategy_T3.py` — fires on Candle 3, homogeneous color check (all 3 green = UP, all 3 red = DOWN). Fires 5s before Candle 3 closes. Default strategy mode is now `t3`. Dashboard dropdown offers T3 or Legacy only.
