# Polymarket BTC 5m Breakout Trading Bot - Configuration
import os

# ─── API URLs ────────────────────────────────────────────────────────────────
POLYMARKET_HOST = "https://clob.polymarket.com"
GAMMA_HOST = "https://gamma-api.polymarket.com"

# ─── Binance WebSocket ───────────────────────────────────────────────────────
BINANCE_WS_URL = "wss://stream.binance.com:9443/stream?streams=btcusdt@kline_1m/btcusdt@ticker"
BINANCE_REST_URL = "https://api.binance.com/api/v3"

# ─── Bybit WebSocket ─────────────────────────────────────────────────────────
BYBIT_WS_URL = os.getenv("BYBIT_WS_URL", "wss://stream.bybit.com/v5/public/linear")
BYBIT_REST_URL = os.getenv("BYBIT_REST_URL", "https://api.bybit.com")
BYBIT_SYMBOL = os.getenv("BYBIT_SYMBOL", "BTCUSDT")
BYBIT_SSL_VERIFY = os.getenv("BYBIT_SSL_VERIFY", "true").lower() in {"1", "true", "yes", "on"}

# ─── Polymarket public odds polling ──────────────────────────────────────────
POLY_ODDS_POLL_SECS = float(os.getenv("POLY_ODDS_POLL_SECS", "5"))

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
FIXED_TRADE_USD = float(os.getenv("FIXED_TRADE_USD", "1"))
MIN_POLYMARKET_SHARES = float(os.getenv("MIN_POLYMARKET_SHARES", "5"))

# ─── Binance REST seed ────────────────────────────────────────────────────────
BINANCE_SEED_CANDLES = 15

# ─── RPC ─────────────────────────────────────────────────────────────────────
INFURA_URL = os.getenv("INFURA_URL", "")
WALLET_BALANCE_POLL_SECS = float(os.getenv("WALLET_BALANCE_POLL_SECS", "60"))

# ─── Polymarket CTF redemption ───────────────────────────────────────────────
POLYMARKET_PUSD = os.getenv("POLYMARKET_PUSD", "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB")
POLYMARKET_USDCE = os.getenv("POLYMARKET_USDCE", "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174")
POLYMARKET_USDC = os.getenv("POLYMARKET_USDC", "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359")
POLYMARKET_CTF = os.getenv("POLYMARKET_CTF", "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045")
POLYMARKET_CTF_COLLATERAL_ADAPTER = os.getenv(
    "POLYMARKET_CTF_COLLATERAL_ADAPTER",
    "0xAdA100Db00Ca00073811820692005400218FcE1f",
)
POLYMARKET_NEG_RISK_CTF_COLLATERAL_ADAPTER = os.getenv(
    "POLYMARKET_NEG_RISK_CTF_COLLATERAL_ADAPTER",
    "0xadA2005600Dec949baf300f4C6120000bDB6eAab",
)
REDEMPTION_ENABLED = os.getenv("REDEMPTION_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
REDEMPTION_POLL_SECS = float(os.getenv("REDEMPTION_POLL_SECS", "30"))
REDEMPTION_MAX_GAS_GWEI = float(os.getenv("REDEMPTION_MAX_GAS_GWEI", "250"))
REDEMPTION_GAS_LIMIT = int(os.getenv("REDEMPTION_GAS_LIMIT", "350000"))

# ─── Dashboard ────────────────────────────────────────────────────────────────
DASHBOARD_HOST = os.getenv("DASHBOARD_HOST", "0.0.0.0")
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "8080"))

# ─── Persistence ─────────────────────────────────────────────────────────────
TRADE_HISTORY_CSV = os.getenv("TRADE_HISTORY_CSV", "data/trade_history.csv")
TRADE_STORE_BACKEND = os.getenv("TRADE_STORE_BACKEND", "csv").lower()
MYSQL_HOST = os.getenv("MYSQL_HOST", "")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "")
MYSQL_USER = os.getenv("MYSQL_USER", "")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")

# ─── Momentum mispricing strategy ───────────────────────────────────────────
MOMENTUM_EDGE_THRESHOLD = float(os.getenv("MOMENTUM_EDGE_THRESHOLD", "0.05"))
MOMENTUM_MAX_SPREAD = float(os.getenv("MOMENTUM_MAX_SPREAD", "0.01"))
MOMENTUM_MIN_ELAPSED_SECS = int(os.getenv("MOMENTUM_MIN_ELAPSED_SECS", "60"))
MOMENTUM_EXIT_BEFORE_CLOSE_SECS = int(os.getenv("MOMENTUM_EXIT_BEFORE_CLOSE_SECS", "30"))
MOMENTUM_CHAINLINK_MAX_DEVIATION = float(os.getenv("MOMENTUM_CHAINLINK_MAX_DEVIATION", "0.002"))
MOMENTUM_PAPER_ONLY = os.getenv("MOMENTUM_PAPER_ONLY", "true").lower() in {"1", "true", "yes", "on"}
