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

# Hybrid model tiers — chosen from the 2026-06-03 benchmark (scripts/model_bench.py).
# qwen3-235b RETIRED: qwen3.6-flash beat it on depth, speed AND reliability for ~the same cost.
#   FAST      – chat tool-loop (tools + free text, no json_object): fast, strong tool-use. qwen/qwen3.6-flash
#   REASONING – judgment calls (aggregator verdict, RL feedback/thesis): deepest answers. qwen/qwen3.7-max
#               NB validated for response_format=json_object — thinking models (e.g. qwen3-235b) break it.
#   BULK      – high-volume sector-agent scoring (json_object): the JSON-proven model. qwen-2.5-72b
#               (the .env-tested workhorse; 235b was retired because it broke JSON output).
# Override any tier in .env. Gemini 3.5 Flash rejected (broken output + 64× cost); Kimi too (empty + 68s).
LLM_MODEL_FAST: str      = os.getenv("LLM_MODEL_FAST", "qwen/qwen3.6-flash")
LLM_MODEL_REASONING: str = os.getenv("LLM_MODEL_REASONING", "qwen/qwen3.7-max")
LLM_MODEL_BULK: str      = os.getenv("LLM_MODEL_BULK", "qwen/qwen-2.5-72b-instruct")
# Back-compat catch-all: any call-site still reading LLM_MODEL gets the BULK tier
# (was qwen3-235b-a22b until 2026-06-03).
LLM_MODEL: str = os.getenv("LLM_MODEL", LLM_MODEL_BULK)
LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.2"))
LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "2048"))
LLM_TIMEOUT_SECONDS: int = int(os.getenv("LLM_TIMEOUT_SECONDS", "60"))

# Token cost rates (USD per million tokens) for telemetry — default to the BULK tier
# (qwen3.6-flash). Override in .env if you repoint the tiers.
LLM_INPUT_COST_PER_M: float = float(os.getenv("LLM_INPUT_COST_PER_M", "0.1875"))
LLM_OUTPUT_COST_PER_M: float = float(os.getenv("LLM_OUTPUT_COST_PER_M", "1.125"))


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
FINNHUB_API_KEY: str = os.getenv("FINNHUB_API_KEY", "")
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

# Yahoo symbol overrides — bare NSE ticker → exact yfinance symbol. Used when
# Yahoo lists a name under a different code, or a corporate action (demerger /
# rename) drops the old ticker. SINGLE SOURCE OF TRUTH — every NSE→yfinance
# conversion path consults this (indicators fetcher, chat resolver, ticker
# verification). Add a line here, not in individual modules.
YF_SYMBOL_OVERRIDES: dict[str, str] = {
    "TATAMOTORS": "TMPV.NS",      # Tata Motors demerged 2025 → Passenger Vehicles entity
    "TVSMOTORS":  "TVSMOTOR.NS",  # NSE symbol is TVSMOTOR (no trailing S)
    "CANARABANK": "CANBK.NS",     # NSE/Yahoo symbol is CANBK
    "HEXAWARE":   "HEXT.NS",      # Yahoo lists Hexaware as HEXT
}

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
RUBBER_TICKER: str = "^TOCOM_RUBBER"    # Tokyo Commodity Exchange rubber (may be delisted; macro.py falls back gracefully)
RUBBER_TICKER_FALLBACKS: list[str] = ["RUBR.L", "SGX:SIR1!", "TOCOM:RSS3"]  # alternatives tried in order
PLATINUM_TICKER: str = "PPLT"           # Aberdeen Platinum ETF (catalytic converters)
PALLADIUM_TICKER: str = "PALL"          # Aberdeen Palladium ETF (catalytic converters)
BRENT_TICKER: str = "BZ=F"             # Brent Crude Futures (polymer cost proxy)

# RBI policy rate — algorithm constant (not an API secret, not in .env)
# Update here when RBI changes rates; the live-fetch redesign (dynamic Serper) will replace this.
RBI_REPO_RATE_PCT: str = "5.25"        # Updated: live Serper fetch confirmed 5.25% (2026); fallback if Serper fails
RBI_REPO_RATE_DATE: str = "2026-02-07"
RBI_REPO_RATE_STANCE: str = "neutral"

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
FORECAST_HORIZON_DAYS: int = 30

# Maximum weight change applied in a single daily adaptation step (per agent)
WEIGHT_MAX_STEP: float = 0.05

# Maximum total drift any agent weight is allowed to move from its base value
WEIGHT_MAX_DRIFT: float = 0.15

# Minimum rolling days required before weight adaptation kicks in
WEIGHT_MIN_OBSERVATIONS: int = 3

# Accuracy window: how many recent days are used to judge agent direction accuracy
WEIGHT_ACCURACY_WINDOW: int = 7

# Thresholds for weight boost / penalty
WEIGHT_BOOST_HIT_RATE: float = 0.70    # ≥70% hit rate → apply weight boost
WEIGHT_PENALTY_HIT_RATE: float = 0.40  # ≤40% hit rate → apply weight penalty

# Cron expression for the daily feedback review job (default: weekdays 4:30pm IST = 11:00 UTC)
FEEDBACK_CRON: str = os.getenv("FEEDBACK_CRON", "0 11 * * 1-5")

# ---------------------------------------------------------------------------
# P5 — Regime Detection Thresholds
# ---------------------------------------------------------------------------

# Regime detection thresholds — algorithm constants, not env-configurable
VIX_VOLATILE_THRESHOLD: float  = 22.0   # VIX above this → volatile macro
VIX_LOW_VOL_THRESHOLD: float   = 14.0   # VIX below this → calm/trending
FII_PROXY_THRESHOLD_PCT: float = 1.0    # Nifty 5-day move threshold for FII proxy
RSI_OVERBOUGHT: float          = 70.0   # RSI above this → overbought
RSI_OVERSOLD: float            = 30.0   # RSI below this → oversold

# Direction classification threshold for RL feedback (see STATIC_AUDIT.md #5)
RL_FLAT_THRESHOLD_PCT: float = 0.3     # moves within ±0.3% classified as FLAT

# Early-exit: skip orchestrator re-run when direction correct + error below this %
# Set to 0.0 to disable early exit entirely.
RL_AGENT_RERUN_THRESHOLD_PCT: float = 0.5

# Scheduler parallelism: how many tickers can be reviewed concurrently.
# Default 1 = sequential (safe without file locking).
# Set to 2-4 in .env once shared ledger locking (P1-7) is confirmed stable.
RL_SCHEDULER_MAX_WORKERS: int = int(os.getenv("RL_SCHEDULER_MAX_WORKERS", "1"))

# ---------------------------------------------------------------------------
# Conviction Streak (P3) — tracker.py
# ---------------------------------------------------------------------------

# Streak length at which FeedbackAgent prompt receives a streak warning block
RL_STREAK_WARNING_THRESHOLD: int = 8

# RSI amplifier applied to reversion_prior when sector RSI contradicts verdict
RL_RSI_AMPLIFIER: float = 1.50

# Absolute cap on reversion_prior including any amplification
RL_MAX_REVERSION_PRIOR: float = 0.30

# ---------------------------------------------------------------------------
# ThesisReviewer (Section 21) — thesis_reviewer.py
# ---------------------------------------------------------------------------

# ATR-relative trigger: threshold = max(floor, multiplier × atr_pct)
RL_ATR_THRESHOLD_FLOOR: float = 1.5       # minimum trigger % regardless of ATR
RL_ATR_THRESHOLD_MULTIPLIER: float = 1.5  # multiplier applied to ticker ATR%

# ---------------------------------------------------------------------------
# Lesson Propagation (P2) — ledger_propagator.py
# ---------------------------------------------------------------------------

# Confidence blend weights when merging a repeated lesson pattern
RL_LESSON_BLEND_EXISTING: float = 0.70   # weight given to the accumulated signal
RL_LESSON_BLEND_INCOMING: float = 0.30   # weight given to the new confirmation

# Confidence bonus per new ticker independently confirming a shared lesson
RL_CROSS_TICKER_BOOST: float = 0.05

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
# ---------------------------------------------------------------------------
# P3-12 — Sector-Agent → Regime-Multiplier Role Mapping
#
# REGIME_MULTIPLIERS uses automobile agent names as canonical keys.
# For other sectors, map each agent to the automobile role it most closely
# represents so apply_regime_multipliers() can look up the right multiplier.
#
# If an agent is NOT listed here for its sector, it defaults to multiplier 1.0.
# ---------------------------------------------------------------------------
SECTOR_AGENT_REGIME_ROLE: dict[str, dict[str, str]] = {
    "banking_bfsi": {
        "fundamentals":  "fundamentals",       # earnings quality → fundamentals
        "risk":          "risk_macro",          # credit risk, NPA → risk_macro
        "macro_policy":  "policy_regulatory",  # RBI policy → policy_regulatory
        "institutional": "sentiment",           # FII/DII flows → sentiment
        "technical":     "pattern_analysis",   # chart patterns → pattern_analysis
        "business":      "valuation_catalyst", # loan book growth → valuation_catalyst
    },
    "it_sector": {
        "fundamentals":   "fundamentals",
        "risk_macro":     "risk_macro",
        "global_macro":   "risk_macro",         # US tech spend risk → risk_macro
        "peer_benchmark": "competitive_intel",  # TCS vs Infosys → competitive_intel
        "transcript_nlp": "sentiment",          # earnings call NLP → sentiment
        "technical":      "pattern_analysis",
        "valuation":      "valuation_catalyst",
    },
    "renewable_energy": {
        "fundamentals":     "fundamentals",
        "business":         "sales_demand",      # capacity pipeline → sales_demand
        "valuation":        "valuation_catalyst",
        "sentiment_policy": "policy_regulatory", # MNRE/CERC policy → policy_regulatory
        "technical":        "pattern_analysis",
        "risk":             "risk_macro",         # DISCOM/curtailment risk → risk_macro
    },
    "automobile": {
        # Identity mapping — automobile agents already match the canonical names
        "sales_demand":       "sales_demand",
        "raw_materials":      "raw_materials",
        "fundamentals":       "fundamentals",
        "pattern_analysis":   "pattern_analysis",
        "sentiment":          "sentiment",
        "policy_regulatory":  "policy_regulatory",
        "competitive_intel":  "competitive_intel",
        "risk_macro":         "risk_macro",
        "valuation_catalyst": "valuation_catalyst",
    },
}

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
# These are algorithm parameters — plain constants, not env-configurable.
# ---------------------------------------------------------------------------

RL_BOOST: float               =  0.02   # weight delta when hit_rate ≥ WEIGHT_BOOST_HIT_RATE
RL_PENALTY: float             = -0.03   # weight delta when hit_rate ≤ WEIGHT_PENALTY_HIT_RATE
RL_MISS_STREAK_PENALTY: float = -0.05   # base bias penalty at full bias_score
RL_BIAS_TRIGGER: float        =  0.55   # bias score at which penalty starts scaling
RL_BIAS_FULL: float           =  0.70   # bias score at which full penalty applies
RL_TIMING_FREE_WINDOW: int    =  3      # lag ≤ N trading days → 0× timing penalty
RL_TIMING_PARTIAL_WINDOW: int =  7      # lag ≤ N trading days → 0.20× timing penalty

# Weight drift ceiling escape hatch: agents with ≥ N consecutive correct days
# are allowed to drift up to ESCAPE_MULTIPLIER × WEIGHT_MAX_DRIFT.
# Prevents the 0.15 cap from blocking learning on clearly reliable agents.
RL_WEIGHT_DRIFT_ESCAPE_DAYS: int = int(os.getenv("RL_WEIGHT_DRIFT_ESCAPE_DAYS", "14"))
RL_WEIGHT_DRIFT_ESCAPE_MULTIPLIER: float = float(os.getenv("RL_WEIGHT_DRIFT_ESCAPE_MULTIPLIER", "1.5"))

# ---------------------------------------------------------------------------
# RL Intelligence Phase, Component 2 — Per-Agent Calibration Reward
# An agent earns a "calibration hit" when its own predicted_agent_scores[agent]
# lean (bullish if >= AGENT_BULLISH_THRESHOLD) matches the realized direction,
# independent of whether the ensemble verdict was correct. WeightAdapter blends
# this into the hit_rate that drives boost/penalty deltas. Flag default ON
# (user-confirmed); when False, behavior is byte-identical to pre-Component-2.
# ---------------------------------------------------------------------------
RL_CALIBRATION_REWARD_ENABLED: bool = os.getenv("RL_CALIBRATION_REWARD_ENABLED", "true").lower() == "true"
RL_CALIBRATION_WEIGHT: float = float(os.getenv("RL_CALIBRATION_WEIGHT", "0.5"))

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

SERPER_TIMEOUT_SECONDS: int   = 10    # Serper HTTP timeout in seconds
TAVILY_MAX_CONTENT_CHARS: int = 600  # Truncate Tavily full-page content at this length

# ---------------------------------------------------------------------------
# Chat Reviewer Loop
# Max number of synthesize→review cycles before accepting the answer as-is.
# Set to 0 to disable the reviewer entirely (useful for dev / low-latency mode).
# Reviewer checks: date integrity, price grounding, question relevance.
# Each extra cycle costs ~300 tokens (reviewer) + ~600 tokens (re-synthesis).
# ---------------------------------------------------------------------------
CHAT_MAX_REVIEW_CYCLES: int = 0  # Reviewer loop removed in 3-node pipeline redesign

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

# ---------------------------------------------------------------------------
# RL Intelligence Phase, Component 3 — Forgetting & Recency
#
# (a) Recency-weighted miss ranking (LearningLedger.recency_weighted_miss_scores,
#     PromptEnhancer.enhance): recent misses should outrank old, frequent ones.
#     score(factor) = sum over miss_events of exp(-age_days / HALFLIFE) x
#                      (1.0 if penalizable else PENALIZABLE_DISCOUNT)
#     Falls back to raw miss_counter ranking when miss_events is empty (legacy
#     ledgers) or when RL_FORGETTING_ENABLED is False (byte-identical to prior
#     behavior).
#
# (b) Stale-lesson archival with resurrection (ledger_propagator.archive_stale_lessons):
#     invalidated lessons that are low-confidence, low-effectiveness, and stale
#     are moved to a per-ticker cold-store JSON. Resurrection restores them if a
#     matching pattern/semantic-tag lesson is about to be re-created.
#
# (c) Recency-weighted feedback aggregation (PredictionStore.load_recent_feedback_entries,
#     compute_historical_avg_return): more recent monthly cycles are weighted
#     higher when computing historical average returns.
#     weight = exp(-cycle_age_months / FEEDBACK_HALFLIFE_MONTHS)
# ---------------------------------------------------------------------------
RL_FORGETTING_ENABLED: bool = os.getenv("RL_FORGETTING_ENABLED", "true").lower() == "true"

# Half-life (days) for recency decay of miss events — score halves every N days.
MISS_RECENCY_HALFLIFE_DAYS: float = float(os.getenv("MISS_RECENCY_HALFLIFE_DAYS", "21"))

# Multiplier applied to non-penalizable miss types (e.g. external_shock) when
# computing recency-weighted miss scores.
MISS_PENALIZABLE_DISCOUNT: float = float(os.getenv("MISS_PENALIZABLE_DISCOUNT", "0.3"))

# Archival thresholds — a still_valid=False lesson is archived only when ALL
# three conditions hold: effective confidence at/below floor, effectiveness
# below floor, AND stale for longer than ARCHIVE_STALE_DAYS.
ARCHIVE_CONF_FLOOR: float = float(os.getenv("ARCHIVE_CONF_FLOOR", "0.12"))
ARCHIVE_EFFECTIVENESS_FLOOR: float = float(os.getenv("ARCHIVE_EFFECTIVENESS_FLOOR", "0.25"))
ARCHIVE_STALE_DAYS: int = int(os.getenv("ARCHIVE_STALE_DAYS", "60"))

# Half-life (months) for recency-weighted feedback cycle aggregation.
FEEDBACK_HALFLIFE_MONTHS: float = float(os.getenv("FEEDBACK_HALFLIFE_MONTHS", "3"))

# ── RL Knowledge Layer — Ticker Dossier + executable claims (2026-06) ──────
RL_DOSSIER_ENABLED: bool = os.getenv("RL_DOSSIER_ENABLED", "true").lower() == "true"
DOSSIER_MAX_OBSERVATIONS: int = int(os.getenv("DOSSIER_MAX_OBSERVATIONS", "30"))
DOSSIER_DIGEST_MAX_CHARS: int = int(os.getenv("DOSSIER_DIGEST_MAX_CHARS", "2500"))
DOSSIER_AGENT_DIGEST_CHARS: int = int(os.getenv("DOSSIER_AGENT_DIGEST_CHARS", "1500"))
DOSSIER_MAX_NEW_OBS_PER_DAY: int = int(os.getenv("DOSSIER_MAX_NEW_OBS_PER_DAY", "3"))
# Post-cap dossiers (30 obs/20 guidance/12 questions/10 catalysts) serialize well under this
# limit, so this cut is a safety net only — not expected to bite in normal operation.
DOSSIER_DISTILL_INPUT_MAX_CHARS: int = int(os.getenv("DOSSIER_DISTILL_INPUT_MAX_CHARS", "20000"))
RL_CLAIMS_ENABLED: bool = os.getenv("RL_CLAIMS_ENABLED", "true").lower() == "true"
RL_LESSON_EMPHASIS_DELTA: float = float(os.getenv("RL_LESSON_EMPHASIS_DELTA", "0.03"))
RL_LESSON_EMPHASIS_CAP: float = float(os.getenv("RL_LESSON_EMPHASIS_CAP", "0.06"))
RL_LESSON_MATCH_MIN_CONF: float = float(os.getenv("RL_LESSON_MATCH_MIN_CONF", "0.45"))

# ── RL Phase 3 — Event-driven dossier ingestion (2026-06-12) ───────────────
# Weekly scan + on-demand CLI: digest qualifying NSE corporate events
# (results, concalls, guidance, investor presentations) into the existing
# TickerDossier via the same bounded merge the daily curator uses.
RL_EVENT_INGEST_ENABLED: bool = os.getenv("RL_EVENT_INGEST_ENABLED", "true").lower() == "true"
EVENT_INGEST_LOOKBACK_DAYS: int = int(os.getenv("EVENT_INGEST_LOOKBACK_DAYS", "8"))
EVENT_INGEST_MAX_EVENTS_PER_SCAN: int = int(os.getenv("EVENT_INGEST_MAX_EVENTS_PER_SCAN", "3"))
EVENT_INGEST_TEXT_MAX_CHARS: int = int(os.getenv("EVENT_INGEST_TEXT_MAX_CHARS", "6000"))

# ---------------------------------------------------------------------------
# RL Phase 1 — Monthly Scorecard + Baseline Duel (2026-06-12)
#
# Control lane (the duel): a bare-LLM predictor gets the same close +
# market_context StockAgent has, but none of the architecture (no agents,
# no learned weights, no lessons, no dossier). Scored against StockAgent and
# naive baselines (persistence, always-up, always-down) in the monthly
# scorecard. Everything here is flag-gated — flags off means byte-identical
# behavior (no Step 10, no monthly job, claims_fired stays []).
# ---------------------------------------------------------------------------

# Daily control-lane prediction + scoring (daily_review Step 10).
RL_CONTROL_LANE_ENABLED: bool = os.getenv("RL_CONTROL_LANE_ENABLED", "true").lower() == "true"

# Control-lane model; empty string -> settings.LLM_MODEL_REASONING.
CONTROL_LANE_MODEL: str = os.getenv("CONTROL_LANE_MODEL", "")

# Monthly scorecard scheduler job (CronTrigger day 1, 02:00 IST).
SCORECARD_ENABLED: bool = os.getenv("SCORECARD_ENABLED", "true").lower() == "true"

# Persisted scorecard time series (PERMANENT — improvement history; volume).
SCORECARD_DIR: str = os.getenv("SCORECARD_DIR", "data/eval/scorecards")

# ---------------------------------------------------------------------------
# Unified Sector Analyst (2026-06-12 redesign) — one data bundle + one
# reasoning-model call replaces the per-sector parallel agent fan-out.
# CSV of sector names on the unified path; "" disables it everywhere.
# ---------------------------------------------------------------------------
UNIFIED_ANALYST_SECTORS: str = os.getenv("UNIFIED_ANALYST_SECTORS", "automobile")
UNIFIED_ANALYST_FALLBACK_LEGACY: bool = os.getenv("UNIFIED_ANALYST_FALLBACK_LEGACY", "true").lower() == "true"
UNIFIED_ANALYST_MAX_TOKENS: int = int(os.getenv("UNIFIED_ANALYST_MAX_TOKENS", "3500"))
UNIFIED_SECTION_MAX_CHARS: int = int(os.getenv("UNIFIED_SECTION_MAX_CHARS", "2500"))
UNIFIED_BUNDLE_MAX_CHARS: int = int(os.getenv("UNIFIED_BUNDLE_MAX_CHARS", "18000"))


def unified_analyst_sectors() -> set[str]:
    """Parsed UNIFIED_ANALYST_SECTORS; empty set when disabled."""
    return {s.strip() for s in UNIFIED_ANALYST_SECTORS.split(",") if s.strip()}

