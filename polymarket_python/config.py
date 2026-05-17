# Polymarket BTC 5m Breakout Trading Bot - Configuration
import os

# ─── API URLs ────────────────────────────────────────────────────────────────
POLYMARKET_HOST = "https://clob.polymarket.com"
GAMMA_HOST = "https://gamma-api.polymarket.com"

# ─── Binance WebSocket ───────────────────────────────────────────────────────
BINANCE_WS_URL = "wss://stream.binance.com:9443/stream?streams=btcusdt@kline_1m/btcusdt@ticker"
BINANCE_REST_URL = "https://api.binance.com/api/v3"

# ─── Chainlink BTC/USD on Polygon ────────────────────────────────────────────
CHAINLINK_BTC_FEED = "0x1B44F3514812d835EB1BDB0acB33d3fA3351Ee43"
CHAINLINK_ABI = [
    {
        "inputs": [],
        "name": "latestRoundData",
        "outputs": [
            {"name": "roundId", "type": "uint80"},
            {"name": "answer", "type": "int256"},
            {"name": "startedAt", "type": "uint256"},
            {"name": "updatedAt", "type": "uint256"},
            {"name": "answeredInRound", "type": "uint80"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function",
    },
]

# ─── Polygon ─────────────────────────────────────────────────────────────────
CHAIN_ID = 137

# ─── Timing ───────────────────────────────────────────────────────────────────
WINDOW_MINUTES = 5
WINDOW_MS = WINDOW_MINUTES * 60 * 1000

# Trend: first 3 candles INSIDE window
STRATEGY_CANDLE_COUNT = 3
# Guard: no trades first 60s, no trades final 90s
CHAINLINK_GUARD_SECS = 60
NO_TRADE_CUTOFF_SECS = 90
FIRST_TRIGGER_DELAY_MS = 60_000

# ─── Indicators ───────────────────────────────────────────────────────────────
ATR_PERIOD = 5
VOL_SMA_PERIOD = 5
WICK_BODY_MAX_RATIO = 0.5
ATR_WICK_FACTOR = 0.1
VOLUME_FACTOR = 1.0

# ─── Position sizing ──────────────────────────────────────────────────────────
CAPITAL = 10_000.0
POSITION_FRACTION = 0.01  # 1% per trade

# ─── Binance REST seed ────────────────────────────────────────────────────────
BINANCE_SEED_CANDLES = 15

# ─── RPC ─────────────────────────────────────────────────────────────────────
INFURA_URL = os.getenv("INFURA_URL", "")

# ─── Dashboard ────────────────────────────────────────────────────────────────
DASHBOARD_HOST = os.getenv("DASHBOARD_HOST", "0.0.0.0")
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "8080"))