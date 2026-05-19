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
├── strategy.py             # Strategy B signal evaluation (current) + dispatcher
├── strategy_legacy.py      # Strategy B legacy (from Rust breakout.rs) — NEW
├── binance_client.py       # Binance WebSocket kline + ticker, REST seed (fallback)
├── bybit_client.py         # Bybit V5 WebSocket kline + ticker, REST seed + certifi SSL (primary feed)
├── chainlink_client.py     # Chainlink Data Engine REST API (live BTC/USD)
├── polymarket_client.py    # py-clob-client-v2 with POLY_1271 deposit wallet (sig type 3) + WebSocket feed
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

## Strategy Toggle (Current vs Legacy)

The bot supports switching between two Strategy B implementations at runtime via the dashboard.

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
- **Strategy dispatch** via `evaluate_signal()` in `strategy.py` — routes to current or legacy based on `state.strategy_mode`
- **Dashboard strategy toggle** — `POST /config/strategy_mode`, indicator badge + button in UI
- **PTB captured at window open** from first price update (Bybit ticker or chainlink — first wins)
- **Guardrails**: no trades first 60s, no trades in final 90s
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
- Chainlink uses Data Engine REST API (`data.chain.link/api/live-data-engine-stream-data`)
- Token IDs refresh every 5min at window boundary (new slug = new token IDs)
- Dashboard shows Trade History table with redemption status (settled, tx, error)
- Redemption loop runs in background, updates CSV on each check
- Standalone `redeem_polymarket_position.py` for manual redemption with `--execute --wait`
- **Tests**: `test_strategy.py` and `test_strategy_full.py` cover signal triggering + all rejection paths.
- **Strategy toggle added (2026-05-19):** `strategy_legacy.py` new file, `strategy.py` dispatcher, dashboard toggle button + indicator badge
- **Dashboard POST fix (2026-05-19):** `/config/strategy_mode` endpoint now accepts raw `Body(...)` bytes to handle `text/plain` POST from dashboard toggle button
- **CSV pre-created (2026-05-19):** `data/trade_history.csv` initialized with header row so it's always available for download, even before any trades

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
