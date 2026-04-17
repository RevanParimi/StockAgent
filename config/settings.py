"""
config/settings.py
==================
All static configuration values for the Automobile Agent system.
Edit this file (or set environment variables) to customize:
  - API keys
  - LLM model names and parameters
  - Agent weights
  - Data-source URLs / limits
  - Output paths

Environment variables take precedence over the defaults below.
Load a .env file by running `pip install python-dotenv` and calling
`load_dotenv()` before importing this module, or set vars in your shell.
"""

import os
from dotenv import load_dotenv

load_dotenv()  # reads .env in project root if present

# ---------------------------------------------------------------------------
# LLM  (OpenRouter)
# ---------------------------------------------------------------------------
OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "your-openrouter-api-key-here")

# NOTE: Helicone was removed — they joined Mintlify and disabled new signups.
# Observability is handled locally via tools/run_logger.py (logs/agent_calls.jsonl).
OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

# Available OpenRouter model IDs — change LLM_MODEL in .env to switch:
#   qwen/qwen3.5-flash-02-23       – DEFAULT: fast, cheap ($0.065/$0.26 per M, ~$0.006/run)
#   mistralai/mistral-small-2603   – fallback: strong reasoning ($0.15/$0.60 per M, ~$0.013/run)
#   qwen/qwen-2.5-72b-instruct     – higher quality ($0.35/$0.40 per M, ~$0.017/run)
#   meta-llama/llama-3.3-70b-instruct – Llama alternative
LLM_MODEL: str = os.getenv("LLM_MODEL", "qwen/qwen3.5-flash-02-23")
LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.2"))
LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "2048"))
LLM_TIMEOUT_SECONDS: int = int(os.getenv("LLM_TIMEOUT_SECONDS", "60"))

# Token cost rates (USD per million tokens) — update in .env when switching models:
#   qwen/qwen3.5-flash-02-23:    0.065 / 0.26
#   mistralai/mistral-small-2603: 0.15  / 0.60
#   qwen/qwen-2.5-72b-instruct:  0.35  / 0.40
LLM_INPUT_COST_PER_M: float = float(os.getenv("LLM_INPUT_COST_PER_M", "0.065"))
LLM_OUTPUT_COST_PER_M: float = float(os.getenv("LLM_OUTPUT_COST_PER_M", "0.26"))

# ---------------------------------------------------------------------------
# Data / Search APIs
# ---------------------------------------------------------------------------
SERPER_API_KEY: str = os.getenv("SERPER_API_KEY", "")        # Google search via Serper
TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")        # Full-page extraction (Policy agent)
ALPHA_VANTAGE_API_KEY: str = os.getenv("ALPHA_VANTAGE_API_KEY", "")
NEWSAPI_KEY: str = os.getenv("NEWSAPI_KEY", "")
TWITTER_BEARER_TOKEN: str = os.getenv("TWITTER_BEARER_TOKEN", "")

# ---------------------------------------------------------------------------
# Stock / Market defaults
# ---------------------------------------------------------------------------
DEFAULT_EXCHANGE: str = "NSE"          # NSE | BSE
DEFAULT_CURRENCY: str = "INR"
PRICE_HISTORY_YEARS: int = 10          # years of OHLCV history for pattern analysis
TECHNICAL_REFRESH_INTERVAL_MIN: int = 15  # minutes between RSI/MACD refreshes

# Nifty Auto index ticker used for peer correlation
NIFTY_AUTO_TICKER: str = "^CNXAUTO"

# ---------------------------------------------------------------------------
# Agent execution
# ---------------------------------------------------------------------------
AGENT_TIMEOUT_SECONDS: int = int(os.getenv("AGENT_TIMEOUT_SECONDS", "120"))
MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))
RETRY_DELAY_SECONDS: float = float(os.getenv("RETRY_DELAY_SECONDS", "2.0"))

# ---------------------------------------------------------------------------
# Signal Aggregator – agent weights (must sum to 1.0)
# ---------------------------------------------------------------------------
AGENT_WEIGHTS: dict[str, float] = {
    "sales_demand":      0.18,
    "raw_materials":     0.10,
    "fundamentals":      0.20,
    "pattern_analysis":  0.13,
    "sentiment":         0.04,   # legacy — kept for backward compat
    "policy_regulatory": 0.10,
    "competitive_intel": 0.10,
    "risk_macro":        0.15,
}

# Score thresholds for the final Automobile Stock Score
SCORE_THRESHOLDS: dict[str, tuple[float, float]] = {
    "strong_buy":  (0.75, 1.00),
    "buy":         (0.55, 0.75),
    "neutral":     (0.40, 0.55),
    "sell":        (0.20, 0.40),
    "strong_sell": (0.00, 0.20),
}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE: str = os.getenv("LOG_FILE", "logs/automobile_agent.log")

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
OUTPUT_DIR: str = os.getenv("OUTPUT_DIR", "outputs")
REPORT_FORMAT: str = os.getenv("REPORT_FORMAT", "json")   # json | markdown

# ---------------------------------------------------------------------------
# Data-source URLs (customizable without touching agent code)
# ---------------------------------------------------------------------------
FADA_DATA_URL: str = "https://www.fada.in/news/monthly-reports"
SIAM_DATA_URL: str = "https://www.siam.in/statistics.aspx"
VAHAN_DATA_URL: str = "https://vahan.parivahan.gov.in/vahan4dashboard/"
DGFT_DATA_URL: str = "https://www.dgft.gov.in"
CARS24_PRICE_URL: str = "https://www.cars24.com/buy-used-cars/"
CARDEKHO_PRICE_URL: str = "https://www.cardekho.com/used-cars"

# News sources for NLP
NEWS_SOURCES: list[str] = [
    "reuters.com",
    "economictimes.indiatimes.com",
    "bloomberg.com",
    "moneycontrol.com",
    "livemint.com",
]

# ---------------------------------------------------------------------------
# Phase 2 – Live Data Feed settings
# ---------------------------------------------------------------------------

# yfinance: NSE tickers need ".NS" suffix (e.g. MARUTI → MARUTI.NS)
YFINANCE_SUFFIX: str = ".NS"

# Number of news articles to fetch per Serper/NewsAPI query
NEWS_ARTICLES_PER_QUERY: int = int(os.getenv("NEWS_ARTICLES_PER_QUERY", "5"))

# Max Serper search queries per agent run (to control API cost)
SERPER_MAX_QUERIES: int = int(os.getenv("SERPER_MAX_QUERIES", "3"))

# Quarterly financials: how many quarters to look back
FINANCIALS_LOOKBACK_QUARTERS: int = int(os.getenv("FINANCIALS_LOOKBACK_QUARTERS", "4"))

# Technical indicators
RSI_PERIOD: int = 14
MACD_FAST: int = 12
MACD_SLOW: int = 26
MACD_SIGNAL: int = 9
BB_PERIOD: int = 20
BB_STD: float = 2.0

# yfinance tickers for macro data (no API key needed)
CRUDE_OIL_TICKER: str = "CL=F"          # WTI Crude Oil Futures
INR_USD_TICKER: str = "INR=X"           # INR per USD
STEEL_TICKER: str = "SLX"               # Steel ETF (proxy)
ALUMINIUM_TICKER: str = "AA"            # Alcoa (proxy for aluminium price)
RUBBER_TICKER: str = "^TOCOM_RUBBER"    # Tokyo Commodity Exchange rubber (fallback: scrape)
PLATINUM_TICKER: str = "PPLT"           # Aberdeen Platinum ETF (catalytic converters)
PALLADIUM_TICKER: str = "PALL"          # Aberdeen Palladium ETF (catalytic converters)
BRENT_TICKER: str = "BZ=F"             # Brent Crude Futures (polymer cost proxy)

# Peer OEM tickers for correlation (NSE .NS suffix applied automatically)
PEER_TICKERS: list[str] = [
    "MARUTI", "TATAMOTORS", "M&M", "HEROMOTOCO",
    "BAJAJ-AUTO", "EICHERMOT", "TVSMOTORS",
]

# ---------------------------------------------------------------------------
# Phase 3 – RAG data directories
# ---------------------------------------------------------------------------
RAG_DOCUMENTS_BASE_DIR: str = os.getenv("RAG_DOCUMENTS_BASE_DIR", "data")

# ---------------------------------------------------------------------------
# Micro Search Loop — API efficiency
# ---------------------------------------------------------------------------
# Background loop that pre-fetches automobile sector macro news on a schedule.
# Populates tools/macro_cache.py; consumed by ContextBuilder._build_risk_macro().
#
# Budget (Serper free tier = 2,500 queries/month):
#   micro search:        MICRO_CYCLES_PER_DAY × MICRO_QUERIES_PER_RUN × 30 = 360/month
#   per-stock (5 ticks): 9 calls × 5 × 30 = 1,350/month  (cache HIT steady-state)
#   Total:               1,710/month  (well within free tier)
#
# Cache HIT saves 3 Serper calls per stock analysis (risk_macro agent).
MICRO_CYCLES_PER_DAY: int = int(os.getenv("MICRO_CYCLES_PER_DAY", "6"))   # every 4h
MICRO_QUERIES_PER_RUN: int = int(os.getenv("MICRO_QUERIES_PER_RUN", "2"))  # 2 combined queries
MACRO_CACHE_TTL_HOURS: int = int(os.getenv("MACRO_CACHE_TTL_HOURS", "2"))  # matches interval

# ---------------------------------------------------------------------------
# Phase 4 – Scheduler
# ---------------------------------------------------------------------------

# Master switch — set to true in .env to activate periodic runs
SCHEDULER_ENABLED: bool = os.getenv("SCHEDULER_ENABLED", "false").lower() == "true"

# Cron expression for scheduled runs (default: weekdays at 8:30am IST)
# Format: "minute hour day-of-month month day-of-week"
SCHEDULER_CRON: str = os.getenv("SCHEDULER_CRON", "30 8 * * 1-5")

# Tickers to analyse on each scheduled run
SCHEDULER_TICKERS: list[str] = [
    t.strip() for t in
    os.getenv("SCHEDULER_TICKERS", "MARUTI,TATAMOTORS,M&M,HEROMOTOCO,BAJAJ-AUTO").split(",")
    if t.strip()
]

# SQLite database path for storing historical scores
SCORE_DB_PATH: str = os.getenv("SCORE_DB_PATH", "data/scores.db")

# Alert thresholds — fire an alert when score changes by this much between runs
ALERT_SCORE_CHANGE_THRESHOLD: float = float(os.getenv("ALERT_SCORE_CHANGE_THRESHOLD", "0.10"))

# Alert when verdict changes (e.g. BUY → NEUTRAL)
ALERT_ON_VERDICT_CHANGE: bool = os.getenv("ALERT_ON_VERDICT_CHANGE", "true").lower() == "true"

# Notification channels — comma-separated list: console,file,webhook
ALERT_CHANNELS: list[str] = [
    c.strip() for c in os.getenv("ALERT_CHANNELS", "console,file").split(",") if c.strip()
]

# Webhook URL for alert notifications (Slack, Discord, custom)
ALERT_WEBHOOK_URL: str = os.getenv("ALERT_WEBHOOK_URL", "")

# Path to write alert log file (used when "file" is in ALERT_CHANNELS)
ALERT_LOG_FILE: str = os.getenv("ALERT_LOG_FILE", "outputs/alerts.log")

# How many past run records to retain per ticker in the DB
SCORE_HISTORY_MAX_ROWS: int = int(os.getenv("SCORE_HISTORY_MAX_ROWS", "90"))  # ~3 months daily

# ---------------------------------------------------------------------------
# Phase 5 – RL Feedback / Adaptive Prediction Loop
# ---------------------------------------------------------------------------

# Root directory for all prediction JSON files
PREDICTION_DATA_DIR: str = os.getenv("PREDICTION_DATA_DIR", "data/predictions")

# How many trading days forward to forecast on month-start
FORECAST_HORIZON_DAYS: int = int(os.getenv("FORECAST_HORIZON_DAYS", "30"))

# Maximum weight change applied in a single daily adaptation step (per agent)
WEIGHT_MAX_STEP: float = float(os.getenv("WEIGHT_MAX_STEP", "0.05"))

# Maximum total drift any agent weight is allowed to move from its base value
WEIGHT_MAX_DRIFT: float = float(os.getenv("WEIGHT_MAX_DRIFT", "0.15"))

# Minimum rolling days required before weight adaptation kicks in
WEIGHT_MIN_OBSERVATIONS: int = int(os.getenv("WEIGHT_MIN_OBSERVATIONS", "3"))

# Accuracy window: how many recent days are used to judge agent direction accuracy
WEIGHT_ACCURACY_WINDOW: int = int(os.getenv("WEIGHT_ACCURACY_WINDOW", "7"))

# Thresholds for weight boost / penalty
WEIGHT_BOOST_HIT_RATE: float = float(os.getenv("WEIGHT_BOOST_HIT_RATE", "0.70"))   # ≥70% → +boost
WEIGHT_PENALTY_HIT_RATE: float = float(os.getenv("WEIGHT_PENALTY_HIT_RATE", "0.40"))  # ≤40% → −penalty

# Cron expression for the daily feedback review job (default: weekdays 4:30pm IST = 11:00 UTC)
FEEDBACK_CRON: str = os.getenv("FEEDBACK_CRON", "0 11 * * 1-5")

