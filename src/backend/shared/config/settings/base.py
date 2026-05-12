"""
config/settings/base.py
========================
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
# LLM  (OpenRouter — observability via tools/run_logger.py logs/agent_calls.jsonl)
# ---------------------------------------------------------------------------
OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "your-openrouter-api-key-here")
OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

# Available OpenRouter model IDs — change LLM_MODEL in .env to switch:
#   qwen/qwen3-235b-a22b           – DEFAULT: accuracy-first, large MoE (~$0.017/run)
#   qwen/qwen3.5-flash-02-23       – fast, cheap ($0.065/$0.26 per M, ~$0.006/run)
#   mistralai/mistral-small-2603   – strong reasoning ($0.15/$0.60 per M, ~$0.013/run)
#   qwen/qwen-2.5-72b-instruct     – higher quality ($0.35/$0.40 per M, ~$0.017/run)
#   meta-llama/llama-3.3-70b-instruct – Llama alternative
LLM_MODEL: str = os.getenv("LLM_MODEL", "qwen/qwen3-235b-a22b")
LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.2"))
LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "2048"))
LLM_TIMEOUT_SECONDS: int = int(os.getenv("LLM_TIMEOUT_SECONDS", "60"))

# Token cost rates (USD per million tokens) — update in .env when switching models:
#   qwen/qwen3-235b-a22b:        input TBD / output TBD
#   qwen/qwen3.5-flash-02-23:    0.065 / 0.26
#   mistralai/mistral-small-2603: 0.15  / 0.60
LLM_INPUT_COST_PER_M: float = float(os.getenv("LLM_INPUT_COST_PER_M", "0.065"))
LLM_OUTPUT_COST_PER_M: float = float(os.getenv("LLM_OUTPUT_COST_PER_M", "0.26"))


# ---------------------------------------------------------------------------
# Data / Search APIs
# ---------------------------------------------------------------------------
SERPER_API_KEY: str = os.getenv("SERPER_API_KEY", "")        # Google search via Serper — automobile + renewable
SERPER_API_KEY_2: str = os.getenv("SERPER_API_KEY_2", "")    # Google search via Serper — bfsi + it
TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")        # Full-page extraction (Policy agent)


def get_serper_key(sector: str) -> str:
    """
    Return the Serper API key assigned to the given sector.

    Key 1 (SERPER_API_KEY):   automobile, renewable  (~2,450 calls/month at default load)
    Key 2 (SERPER_API_KEY_2): bfsi, it               (~1,490 calls/month at default load)

    Falls back to Key 1 if Key 2 is not configured.
    """
    if sector in {"bfsi", "it"} and SERPER_API_KEY_2:
        return SERPER_API_KEY_2
    return SERPER_API_KEY
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
    "sales_demand":       0.15,
    "raw_materials":      0.09,
    "fundamentals":       0.18,
    "pattern_analysis":   0.11,
    "sentiment":          0.04,
    "policy_regulatory":  0.09,
    "competitive_intel":  0.09,
    "risk_macro":         0.13,
    "valuation_catalyst": 0.12,
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
# Background loop that pre-fetches sector-level macro news on a schedule.
# Covers: automobile, bfsi, it  (RE excluded — its signals are per-company).
# Populates tools/macro_cache.py; consumed by:
#   ContextBuilder._build_risk_macro()    → cache key "automobile"
#   ContextBuilder._build_macro_policy()  → cache key "bfsi"
#   ContextBuilder._build_it_risk_macro() → cache key "it"
#
# Budget (Serper free tier = 2,500 queries/month):
#   micro loop:          3 sectors × MICRO_QUERIES_PER_RUN × MICRO_CYCLES_PER_DAY × 30
#                        = 3 × 2 × 6 × 30 = 1,080/month
#   per-stock savings:   3 calls saved × 5 tickers × 3 sectors × 22 days = 990/month saved
#
# Cache HIT saves 3 Serper calls per stock analysis per sector.
MICRO_CYCLES_PER_DAY: int = int(os.getenv("MICRO_CYCLES_PER_DAY", "6"))   # every 4h
MICRO_QUERIES_PER_RUN: int = int(os.getenv("MICRO_QUERIES_PER_RUN", "2"))  # 2 queries per sector per run
# STATIC_AUDIT #13: derive TTL from loop interval so they stay in sync automatically
MACRO_CACHE_TTL_HOURS: int = int(os.getenv("MACRO_CACHE_TTL_HOURS", str(24 // MICRO_CYCLES_PER_DAY)))

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
# C# Scheduler integration (Phase 4 — opt-in)
# ---------------------------------------------------------------------------

# Set to true in .env to route score_store.save() through the C# API
CSHARP_SCHEDULER_ENABLED: bool = os.getenv("CSHARP_SCHEDULER_ENABLED", "false").lower() == "true"

# Base URL of the C# scheduler service (port 5000)
CSHARP_API_URL: str = os.getenv("CSHARP_API_URL", "http://localhost:5000")

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

# ---------------------------------------------------------------------------
# P5 — Regime Detection Thresholds
# ---------------------------------------------------------------------------

# Regime thresholds — overridable via env vars (see STATIC_AUDIT.md #3)
VIX_VOLATILE_THRESHOLD: float  = float(os.getenv("VIX_VOLATILE_THRESHOLD", "22.0"))
VIX_LOW_VOL_THRESHOLD: float   = float(os.getenv("VIX_LOW_VOL_THRESHOLD",  "14.0"))
FII_PROXY_THRESHOLD_PCT: float = float(os.getenv("FII_PROXY_THRESHOLD_PCT", "1.0"))
RSI_OVERBOUGHT: float          = float(os.getenv("RSI_OVERBOUGHT",          "70.0"))
RSI_OVERSOLD: float            = float(os.getenv("RSI_OVERSOLD",            "30.0"))

# Direction classification threshold for RL feedback (see STATIC_AUDIT.md #5)
RL_FLAT_THRESHOLD_PCT: float = float(os.getenv("RL_FLAT_THRESHOLD_PCT", "0.3"))

VIX_FALLBACK: float = 17.0              # NORMAL regime midpoint; used on yfinance error
FII_PROXY_FALLBACK: float = 0.0         # Neutral; used on yfinance error
RSI_FALLBACK: float = 50.0              # Neutral; used on computation error

# Sector index tickers for RSI computation (yfinance symbols)
REGIME_SECTOR_TICKERS: dict[str, str] = {
    "automobile":      "^CNXAUTO",
    "banking_bfsi":    "^NSEBANK",
    "it_sector":       "^CNXIT",
    "renewable_energy": "^CNXENERGY",
}
REGIME_SECTOR_FALLBACK_TICKER: str = "^NSEI"    # Nifty 50 fallback
REGIME_VIX_TICKER: str = "^INDIAVIX"
REGIME_FII_PROXY_TICKER: str = "^NSEI"          # Nifty 50 for 5-day momentum proxy

# P5 — Regime Multiplier Table
# Applied on top of learned WeightMemory weights (not stored, daily-only modifier).
# Agents not listed default to 1.0 (passthrough).
# Columns: MACRO_CRISIS, RISK_OFF, NORMAL, RISK_ON, MOMENTUM_EXTENDED, OVERSOLD
REGIME_MULTIPLIERS: dict[str, dict[str, float]] = {
    "MACRO_CRISIS": {
        "risk_macro":         1.40,
        "fundamentals":       0.80,
        "sales_demand":       0.70,
        "sentiment":          0.80,
        "pattern_analysis":   0.90,
        "competitive_intel":  1.00,
        "valuation_catalyst": 0.90,
        "raw_materials":      1.00,
        "policy_regulatory":  1.00,
    },
    "RISK_OFF": {
        "risk_macro":         1.20,
        "fundamentals":       0.90,
        "sales_demand":       0.85,
        "sentiment":          0.90,
        "pattern_analysis":   0.95,
        "competitive_intel":  1.00,
        "valuation_catalyst": 0.95,
        "raw_materials":      1.00,
        "policy_regulatory":  1.00,
    },
    "NORMAL": {
        "risk_macro":         1.00,
        "fundamentals":       1.00,
        "sales_demand":       1.00,
        "sentiment":          1.00,
        "pattern_analysis":   1.00,
        "competitive_intel":  1.00,
        "valuation_catalyst": 1.00,
        "raw_materials":      1.00,
        "policy_regulatory":  1.00,
    },
    "RISK_ON": {
        "risk_macro":         0.90,
        "fundamentals":       1.10,
        "sales_demand":       1.10,
        "sentiment":          1.15,
        "pattern_analysis":   0.95,
        "competitive_intel":  1.00,
        "valuation_catalyst": 1.10,
        "raw_materials":      1.00,
        "policy_regulatory":  1.00,
    },
    "MOMENTUM_EXTENDED": {
        "risk_macro":         0.85,
        "fundamentals":       1.05,
        "sales_demand":       0.95,
        "sentiment":          0.80,
        "pattern_analysis":   1.20,
        "competitive_intel":  1.00,
        "valuation_catalyst": 1.10,
        "raw_materials":      1.00,
        "policy_regulatory":  1.00,
    },
    "OVERSOLD": {
        "risk_macro":         1.10,
        "fundamentals":       1.00,
        "sales_demand":       1.00,
        "sentiment":          0.90,
        "pattern_analysis":   1.30,
        "competitive_intel":  1.00,
        "valuation_catalyst": 1.05,
        "raw_materials":      1.00,
        "policy_regulatory":  1.00,
    },
}

# ---------------------------------------------------------------------------
# STATIC_AUDIT #4 — RL weight delta constants (moved from weight_adapter.py)
# All 7 constants are now env-overridable instead of hardcoded module globals.
# ---------------------------------------------------------------------------

RL_BOOST: float               = float(os.getenv("RL_BOOST",               "+0.02"))
RL_PENALTY: float             = float(os.getenv("RL_PENALTY",             "-0.03"))
RL_MISS_STREAK_PENALTY: float = float(os.getenv("RL_MISS_STREAK_PENALTY", "-0.05"))
RL_BIAS_TRIGGER: float        = float(os.getenv("RL_BIAS_TRIGGER",        "0.55"))
RL_BIAS_FULL: float           = float(os.getenv("RL_BIAS_FULL",           "0.70"))
RL_TIMING_FREE_WINDOW: int    = int(os.getenv("RL_TIMING_FREE_WINDOW",    "3"))
RL_TIMING_PARTIAL_WINDOW: int = int(os.getenv("RL_TIMING_PARTIAL_WINDOW", "7"))

# ---------------------------------------------------------------------------
# STATIC_AUDIT #9 — News geo: removed country filter entirely
# Serper query now omits "gl" — Google surfaces globally relevant results
# based on query specificity. A query like "TCS Q4 2026 deal wins" returns
# Indian + US + global sources ranked by relevance without geo restriction.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# STATIC_AUDIT #15 — Serper timeout (moved from news.py _TIMEOUT = 10)
# STATIC_AUDIT #16 — Tavily content truncation (moved from tavily_fetcher.py)
# ---------------------------------------------------------------------------

SERPER_TIMEOUT_SECONDS: int    = int(os.getenv("SERPER_TIMEOUT_SECONDS",    "10"))
TAVILY_MAX_CONTENT_CHARS: int  = int(os.getenv("TAVILY_MAX_CONTENT_CHARS",  "600"))

# ---------------------------------------------------------------------------
# Chat Reviewer Loop
# Max number of synthesize→review cycles before accepting the answer as-is.
# Set to 0 to disable the reviewer entirely (useful for dev / low-latency mode).
# Reviewer checks: date integrity, price grounding, question relevance.
# Each extra cycle costs ~300 tokens (reviewer) + ~600 tokens (re-synthesis).
# ---------------------------------------------------------------------------
CHAT_MAX_REVIEW_CYCLES: int = int(os.getenv("CHAT_MAX_REVIEW_CYCLES", "3"))

# ---------------------------------------------------------------------------
# Macro News Background Feed
# Two APScheduler jobs: market-hours (3×/day) + daily policy (1×/day)
# ---------------------------------------------------------------------------

# Retain daily JSON feed files for this many days before deleting
MACRO_NEWS_RETAIN_DAYS: int = int(os.getenv("MACRO_NEWS_RETAIN_DAYS", "90"))

# Max HIGH-severity items injected into the chat context per synthesize call
MACRO_NEWS_CONTEXT_MAX_ITEMS: int = int(os.getenv("MACRO_NEWS_CONTEXT_MAX_ITEMS", "3"))

# Max HIGH-severity items passed to the reviewer criterion-4 check
MACRO_NEWS_REVIEWER_MAX_ITEMS: int = int(os.getenv("MACRO_NEWS_REVIEWER_MAX_ITEMS", "5"))

# Set to "false" to disable the macro news scheduler jobs without removing them
MACRO_NEWS_ENABLED: bool = os.getenv("MACRO_NEWS_ENABLED", "true").lower() == "true"

