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

from .loader import cfg  # env > config.yaml > fallback (loader.py)  # noqa: E402

# ---------------------------------------------------------------------------
# LLM  (OpenRouter — observability via tools/run_logger.py logs/agent_calls.jsonl)
# ---------------------------------------------------------------------------
OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "your-openrouter-api-key-here")
OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

# Hybrid model tiers — rationale + retirement history documented in config.yaml.
LLM_MODEL_FAST: str      = cfg("llm.model_fast",      env="LLM_MODEL_FAST",      fallback="qwen/qwen3.6-flash")
LLM_MODEL_REASONING: str = cfg("llm.model_reasoning", env="LLM_MODEL_REASONING", fallback="qwen/qwen3.7-max")
LLM_MODEL_BULK: str      = cfg("llm.model_bulk",      env="LLM_MODEL_BULK",      fallback="deepseek/deepseek-v4-flash")
# Back-compat catch-all: any call-site still reading LLM_MODEL gets the BULK tier.
LLM_MODEL: str = os.getenv("LLM_MODEL", LLM_MODEL_BULK)
LLM_TEMPERATURE: float = cfg("llm.temperature", env="LLM_TEMPERATURE", fallback=0.2)
LLM_MAX_TOKENS: int = cfg("llm.max_tokens", env="LLM_MAX_TOKENS", fallback=2048)
LLM_TIMEOUT_SECONDS: int = cfg("llm.timeout_seconds", env="LLM_TIMEOUT_SECONDS", fallback=60)

# Token cost rates (USD per million tokens) for telemetry — BULK tier defaults
# (deepseek-v4-flash, OpenRouter 2026-07-02). Override if you repoint the tiers.
LLM_INPUT_COST_PER_M: float = cfg("llm.input_cost_per_m", env="LLM_INPUT_COST_PER_M", fallback=0.09)
LLM_OUTPUT_COST_PER_M: float = cfg("llm.output_cost_per_m", env="LLM_OUTPUT_COST_PER_M", fallback=0.18)


# ---------------------------------------------------------------------------
# Data / Search APIs
# ---------------------------------------------------------------------------
SERPER_API_KEY: str = os.getenv("SERPER_API_KEY", "")        # Google search via Serper — single paid key, all sectors
TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")        # Full-page extraction (Policy agent)


def get_serper_key(sector: str) -> str:
    """
    Return the Serper API key for the given sector.

    Single paid key now serves all sectors — `sector` is kept for call-site
    compatibility (bundle_builder, ContextBuilder both pass it) but no longer
    affects which key is returned.
    """
    return SERPER_API_KEY
NEWSAPI_KEY: str = os.getenv("NEWSAPI_KEY", "")

# ---------------------------------------------------------------------------
# Stock / Market defaults
# ---------------------------------------------------------------------------
DEFAULT_EXCHANGE: str = "NSE"          # NSE | BSE
DEFAULT_CURRENCY: str = "INR"
PRICE_HISTORY_YEARS: int = cfg("data_fetch.price_history_years", fallback=10)          # years of OHLCV history
TECHNICAL_REFRESH_INTERVAL_MIN: int = cfg("data_fetch.technical_refresh_interval_min", fallback=15)

# Nifty Auto index ticker used for peer correlation
NIFTY_AUTO_TICKER: str = "^CNXAUTO"

# ---------------------------------------------------------------------------
# Agent execution
# ---------------------------------------------------------------------------
AGENT_TIMEOUT_SECONDS: int = cfg("agent_execution.timeout_seconds", env="AGENT_TIMEOUT_SECONDS", fallback=120)
MAX_RETRIES: int = cfg("agent_execution.max_retries", env="MAX_RETRIES", fallback=3)
RETRY_DELAY_SECONDS: float = cfg("agent_execution.retry_delay_seconds", env="RETRY_DELAY_SECONDS", fallback=2.0)

# ---------------------------------------------------------------------------
# Signal Aggregator – agent weights (must sum to 1.0)
# ---------------------------------------------------------------------------
_DEFAULT_AGENT_WEIGHTS: dict[str, float] = {
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
AGENT_WEIGHTS: dict[str, float] = cfg("agent_weights", fallback=_DEFAULT_AGENT_WEIGHTS)

# Score thresholds for the final Automobile Stock Score
_DEFAULT_SCORE_THRESHOLDS: dict[str, tuple[float, float]] = {
    "strong_buy":  (0.75, 1.00),
    "buy":         (0.55, 0.75),
    "neutral":     (0.40, 0.55),
    "sell":        (0.20, 0.40),
    "strong_sell": (0.00, 0.20),
}
SCORE_THRESHOLDS: dict[str, tuple[float, float]] = {
    k: tuple(v) for k, v in cfg("score_thresholds", fallback=_DEFAULT_SCORE_THRESHOLDS).items()
}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE: str = os.getenv("LOG_FILE", "logs/automobile_agent.log")

# Permanent log/telemetry archive (services/data/stores/log_store.py).
# Lives under data/ so it sits on the Railway volume and SURVIVES DEPLOYS —
# Railway console logs rotate per-deployment and are lost otherwise.
TELEMETRY_DB_PATH: str = cfg("logging.telemetry_db_path", env="TELEMETRY_DB_PATH", fallback="data/telemetry.db")

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
NEWS_ARTICLES_PER_QUERY: int = cfg("data_fetch.news_articles_per_query", env="NEWS_ARTICLES_PER_QUERY", fallback=5)

# Max Serper search queries per agent run (to control API cost)
SERPER_MAX_QUERIES: int = cfg("data_fetch.serper_max_queries", env="SERPER_MAX_QUERIES", fallback=3)

# Quarterly financials: how many quarters to look back
FINANCIALS_LOOKBACK_QUARTERS: int = cfg("data_fetch.financials_lookback_quarters", env="FINANCIALS_LOOKBACK_QUARTERS", fallback=4)

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
# Macro Cache — API efficiency
# ---------------------------------------------------------------------------
# Populates services/data/cache/macro_cache.py; consumed by:
#   ContextBuilder._build_risk_macro()    → cache key "automobile"
#   ContextBuilder._build_macro_policy()  → cache key "bfsi"
#   ContextBuilder._build_it_risk_macro() → cache key "it"
#
# Populated on-miss by bundle_builder._fetch_macro_context() (and the legacy
# context builders, which also fetch-on-miss). Cache HIT saves Serper calls
# for every subsequent stock analysis in the same sector within the TTL.
MACRO_CACHE_TTL_HOURS: float = cfg("data_fetch.macro_cache_ttl_hours", env="MACRO_CACHE_TTL_HOURS", fallback=4.0)

# ---------------------------------------------------------------------------
# Phase 4 – Scheduler
# ---------------------------------------------------------------------------

# Master switch — set to true in .env to activate periodic runs
SCHEDULER_ENABLED: bool = cfg("scheduler.enabled", env="SCHEDULER_ENABLED", fallback=False)

# Cron expression for scheduled runs (default: weekdays at 8:30am IST)
# Format: "minute hour day-of-month month day-of-week"
SCHEDULER_CRON: str = cfg("scheduler.cron", env="SCHEDULER_CRON", fallback="30 8 * * 1-5")

# Tickers to analyse on each scheduled run
SCHEDULER_TICKERS: list[str] = list(cfg(
    "scheduler.tickers", env="SCHEDULER_TICKERS",
    fallback=["MARUTI", "TATAMOTORS", "M&M", "HEROMOTOCO", "BAJAJ-AUTO"],
))

# SQLite database path for storing historical scores
SCORE_DB_PATH: str = os.getenv("SCORE_DB_PATH", "data/scores.db")

# Alert thresholds — fire an alert when score changes by this much between runs
ALERT_SCORE_CHANGE_THRESHOLD: float = cfg("scheduler.alert_score_change_threshold", env="ALERT_SCORE_CHANGE_THRESHOLD", fallback=0.10)

# Alert when verdict changes (e.g. BUY → NEUTRAL)
ALERT_ON_VERDICT_CHANGE: bool = cfg("scheduler.alert_on_verdict_change", env="ALERT_ON_VERDICT_CHANGE", fallback=True)

# Notification channels — comma-separated list: console,file,webhook
ALERT_CHANNELS: list[str] = list(cfg("scheduler.alert_channels", env="ALERT_CHANNELS", fallback=["console", "file"]))

# Webhook URL for alert notifications (Slack, Discord, custom)
ALERT_WEBHOOK_URL: str = os.getenv("ALERT_WEBHOOK_URL", "")

# Path to write alert log file (used when "file" is in ALERT_CHANNELS)
ALERT_LOG_FILE: str = os.getenv("ALERT_LOG_FILE", "outputs/alerts.log")

# How many past run records to retain per ticker in the DB
SCORE_HISTORY_MAX_ROWS: int = cfg("scheduler.score_history_max_rows", env="SCORE_HISTORY_MAX_ROWS", fallback=90)  # ~3 months daily

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
FORECAST_HORIZON_DAYS: int = cfg("rl.forecast_horizon_days", fallback=30)

# Maximum weight change applied in a single daily adaptation step (per agent)
WEIGHT_MAX_STEP: float = cfg("rl.weight_max_step", fallback=0.05)

# Maximum total drift any agent weight is allowed to move from its base value
WEIGHT_MAX_DRIFT: float = cfg("rl.weight_max_drift", fallback=0.15)

# Minimum rolling days required before weight adaptation kicks in
WEIGHT_MIN_OBSERVATIONS: int = cfg("rl.weight_min_observations", fallback=3)

# Accuracy window: how many recent days are used to judge agent direction accuracy
WEIGHT_ACCURACY_WINDOW: int = cfg("rl.weight_accuracy_window", fallback=7)

# Thresholds for weight boost / penalty
WEIGHT_BOOST_HIT_RATE: float = cfg("rl.weight_boost_hit_rate", fallback=0.70)    # ≥70% hit rate → apply weight boost
WEIGHT_PENALTY_HIT_RATE: float = cfg("rl.weight_penalty_hit_rate", fallback=0.40)  # ≤40% hit rate → apply weight penalty

# Cron expression for the daily feedback review job (default: weekdays 4:30pm IST = 11:00 UTC)
FEEDBACK_CRON: str = cfg("scheduler.feedback_cron", env="FEEDBACK_CRON", fallback="0 11 * * 1-5")

# ---------------------------------------------------------------------------
# P5 — Regime Detection Thresholds
# ---------------------------------------------------------------------------

# Regime detection thresholds — algorithm constants, not env-configurable
VIX_VOLATILE_THRESHOLD: float  = cfg("regime.vix_volatile_threshold", fallback=22.0)   # VIX above this → volatile macro
VIX_LOW_VOL_THRESHOLD: float   = cfg("regime.vix_low_vol_threshold", fallback=14.0)   # VIX below this → calm/trending
FII_PROXY_THRESHOLD_PCT: float = cfg("regime.fii_proxy_threshold_pct", fallback=1.0)    # Nifty 5-day move threshold for FII proxy
RSI_OVERBOUGHT: float          = cfg("regime.rsi_overbought", fallback=70.0)   # RSI above this → overbought
RSI_OVERSOLD: float            = cfg("regime.rsi_oversold", fallback=30.0)   # RSI below this → oversold

# Direction classification threshold for RL feedback (see STATIC_AUDIT.md #5)
RL_FLAT_THRESHOLD_PCT: float = cfg("rl.flat_threshold_pct", fallback=0.3)     # moves within ±0.3% classified as FLAT

# Early-exit: skip orchestrator re-run when direction correct + error below this %
# Set to 0.0 to disable early exit entirely.
RL_AGENT_RERUN_THRESHOLD_PCT: float = cfg("rl.agent_rerun_threshold_pct", fallback=0.5)

# Scheduler parallelism: how many tickers can be reviewed concurrently.
# Default 1 = sequential (safe without file locking).
# Set to 2-4 in .env once shared ledger locking (P1-7) is confirmed stable.
RL_SCHEDULER_MAX_WORKERS: int = cfg("rl.scheduler_max_workers", env="RL_SCHEDULER_MAX_WORKERS", fallback=1)

# ---------------------------------------------------------------------------
# Conviction Streak (P3) — tracker.py
# ---------------------------------------------------------------------------

# Streak length at which FeedbackAgent prompt receives a streak warning block
RL_STREAK_WARNING_THRESHOLD: int = cfg("rl.streak_warning_threshold", fallback=8)

# RSI amplifier applied to reversion_prior when sector RSI contradicts verdict
RL_RSI_AMPLIFIER: float = cfg("rl.rsi_amplifier", fallback=1.50)

# Absolute cap on reversion_prior including any amplification
RL_MAX_REVERSION_PRIOR: float = cfg("rl.max_reversion_prior", fallback=0.30)

# ---------------------------------------------------------------------------
# ThesisReviewer (Section 21) — thesis_reviewer.py
# ---------------------------------------------------------------------------

# ATR-relative trigger: threshold = max(floor, multiplier × atr_pct)
RL_ATR_THRESHOLD_FLOOR: float = cfg("rl.atr_threshold_floor", fallback=1.5)       # minimum trigger % regardless of ATR
RL_ATR_THRESHOLD_MULTIPLIER: float = cfg("rl.atr_threshold_multiplier", fallback=1.5)  # multiplier applied to ticker ATR%

# ---------------------------------------------------------------------------
# Lesson Propagation (P2) — ledger_propagator.py
# ---------------------------------------------------------------------------

# Confidence blend weights when merging a repeated lesson pattern
RL_LESSON_BLEND_EXISTING: float = cfg("rl.lesson_blend_existing", fallback=0.70)   # weight given to the accumulated signal
RL_LESSON_BLEND_INCOMING: float = cfg("rl.lesson_blend_incoming", fallback=0.30)   # weight given to the new confirmation

# Confidence bonus per new ticker independently confirming a shared lesson
RL_CROSS_TICKER_BOOST: float = cfg("rl.cross_ticker_boost", fallback=0.05)

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
_DEFAULT_SECTOR_AGENT_REGIME_ROLE: dict[str, dict[str, str]] = {
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
    "generic": {
        "business": "sales_demand", "fundamentals": "fundamentals",
        "valuation": "valuation_catalyst", "technical": "pattern_analysis",
        "macro": "risk_macro", "risk": "risk_macro",
        "management": "competitive_intel", "earnings": "fundamentals",
    },
}

SECTOR_AGENT_REGIME_ROLE: dict[str, dict[str, str]] = cfg(
    "sector_agent_regime_role", fallback=_DEFAULT_SECTOR_AGENT_REGIME_ROLE,
)

_DEFAULT_REGIME_MULTIPLIERS: dict[str, dict[str, float]] = {
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
REGIME_MULTIPLIERS: dict[str, dict[str, float]] = cfg(
    "regime_multipliers", fallback=_DEFAULT_REGIME_MULTIPLIERS,
)

# ---------------------------------------------------------------------------
# STATIC_AUDIT #4 — RL weight delta constants (moved from weight_adapter.py)
# These are algorithm parameters — plain constants, not env-configurable.
# ---------------------------------------------------------------------------

RL_BOOST: float               =  cfg("rl.boost", fallback=0.02)   # weight delta when hit_rate ≥ WEIGHT_BOOST_HIT_RATE
RL_PENALTY: float             = cfg("rl.penalty", fallback=-0.03)   # weight delta when hit_rate ≤ WEIGHT_PENALTY_HIT_RATE
RL_MISS_STREAK_PENALTY: float = cfg("rl.miss_streak_penalty", fallback=-0.05)   # base bias penalty at full bias_score
RL_BIAS_TRIGGER: float        =  cfg("rl.bias_trigger", fallback=0.55)   # bias score at which penalty starts scaling
RL_BIAS_FULL: float           =  cfg("rl.bias_full", fallback=0.70)   # bias score at which full penalty applies
RL_TIMING_FREE_WINDOW: int    =  cfg("rl.timing_free_window", fallback=3)      # lag ≤ N trading days → 0× timing penalty
RL_TIMING_PARTIAL_WINDOW: int =  cfg("rl.timing_partial_window", fallback=7)      # lag ≤ N trading days → 0.20× timing penalty

# Weight drift ceiling escape hatch: agents with ≥ N consecutive correct days
# are allowed to drift up to ESCAPE_MULTIPLIER × WEIGHT_MAX_DRIFT.
# Prevents the 0.15 cap from blocking learning on clearly reliable agents.
RL_WEIGHT_DRIFT_ESCAPE_DAYS: int = cfg("rl.weight_drift_escape_days", env="RL_WEIGHT_DRIFT_ESCAPE_DAYS", fallback=14)
RL_WEIGHT_DRIFT_ESCAPE_MULTIPLIER: float = cfg("rl.weight_drift_escape_multiplier", env="RL_WEIGHT_DRIFT_ESCAPE_MULTIPLIER", fallback=1.5)

# ---------------------------------------------------------------------------
# RL Intelligence Phase, Component 2 — Per-Agent Calibration Reward
# An agent earns a "calibration hit" when its own predicted_agent_scores[agent]
# lean (bullish if >= AGENT_BULLISH_THRESHOLD) matches the realized direction,
# independent of whether the ensemble verdict was correct. WeightAdapter blends
# this into the hit_rate that drives boost/penalty deltas. Flag default ON
# (user-confirmed); when False, behavior is byte-identical to pre-Component-2.
# ---------------------------------------------------------------------------
RL_CALIBRATION_REWARD_ENABLED: bool = cfg("rl.calibration_reward_enabled", env="RL_CALIBRATION_REWARD_ENABLED", fallback=True)
RL_CALIBRATION_WEIGHT: float = cfg("rl.calibration_weight", env="RL_CALIBRATION_WEIGHT", fallback=0.5)

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

SERPER_TIMEOUT_SECONDS: int   = cfg("data_fetch.serper_timeout_seconds", fallback=10)    # Serper HTTP timeout
TAVILY_MAX_CONTENT_CHARS: int = cfg("data_fetch.tavily_max_content_chars", fallback=600)  # Tavily content cap

# ---------------------------------------------------------------------------
# Chat Reviewer Loop
# Max number of synthesize→review cycles before accepting the answer as-is.
# Set to 0 to disable the reviewer entirely (useful for dev / low-latency mode).
# Reviewer checks: date integrity, price grounding, question relevance.
# Each extra cycle costs ~300 tokens (reviewer) + ~600 tokens (re-synthesis).
# ---------------------------------------------------------------------------
CHAT_MAX_REVIEW_CYCLES: int = cfg("chat.max_review_cycles", fallback=0)  # Reviewer loop removed in 3-node redesign

# ---------------------------------------------------------------------------
# Macro News Background Feed
# Two APScheduler jobs: market-hours (3×/day) + daily policy (1×/day)
# ---------------------------------------------------------------------------

# Retain daily JSON feed files for this many days before deleting
MACRO_NEWS_RETAIN_DAYS: int = cfg("macro_news.retain_days", env="MACRO_NEWS_RETAIN_DAYS", fallback=90)

# Max HIGH-severity items injected into the chat context per synthesize call
MACRO_NEWS_CONTEXT_MAX_ITEMS: int = cfg("macro_news.context_max_items", env="MACRO_NEWS_CONTEXT_MAX_ITEMS", fallback=3)

# Max HIGH-severity items passed to the reviewer criterion-4 check
MACRO_NEWS_REVIEWER_MAX_ITEMS: int = cfg("macro_news.reviewer_max_items", env="MACRO_NEWS_REVIEWER_MAX_ITEMS", fallback=5)

# Set to "false" to disable the macro news scheduler jobs without removing them
MACRO_NEWS_ENABLED: bool = cfg("macro_news.enabled", env="MACRO_NEWS_ENABLED", fallback=True)

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
RL_FORGETTING_ENABLED: bool = cfg("rl.forgetting_enabled", env="RL_FORGETTING_ENABLED", fallback=True)

# Half-life (days) for recency decay of miss events — score halves every N days.
MISS_RECENCY_HALFLIFE_DAYS: float = cfg("rl.miss_recency_halflife_days", env="MISS_RECENCY_HALFLIFE_DAYS", fallback=21.0)

# Multiplier applied to non-penalizable miss types (e.g. external_shock) when
# computing recency-weighted miss scores.
MISS_PENALIZABLE_DISCOUNT: float = cfg("rl.miss_penalizable_discount", env="MISS_PENALIZABLE_DISCOUNT", fallback=0.3)

# Archival thresholds — a still_valid=False lesson is archived only when ALL
# three conditions hold: effective confidence at/below floor, effectiveness
# below floor, AND stale for longer than ARCHIVE_STALE_DAYS.
ARCHIVE_CONF_FLOOR: float = cfg("rl.archive_conf_floor", env="ARCHIVE_CONF_FLOOR", fallback=0.12)
ARCHIVE_EFFECTIVENESS_FLOOR: float = cfg("rl.archive_effectiveness_floor", env="ARCHIVE_EFFECTIVENESS_FLOOR", fallback=0.25)
ARCHIVE_STALE_DAYS: int = cfg("rl.archive_stale_days", env="ARCHIVE_STALE_DAYS", fallback=60)

# Half-life (months) for recency-weighted feedback cycle aggregation.
FEEDBACK_HALFLIFE_MONTHS: float = cfg("rl.feedback_halflife_months", env="FEEDBACK_HALFLIFE_MONTHS", fallback=3.0)

# ── RL Knowledge Layer — Ticker Dossier + executable claims (2026-06) ──────
RL_DOSSIER_ENABLED: bool = cfg("rl.dossier_enabled", env="RL_DOSSIER_ENABLED", fallback=True)
DOSSIER_MAX_OBSERVATIONS: int = cfg("rl.dossier_max_observations", env="DOSSIER_MAX_OBSERVATIONS", fallback=30)
DOSSIER_DIGEST_MAX_CHARS: int = cfg("rl.dossier_digest_max_chars", env="DOSSIER_DIGEST_MAX_CHARS", fallback=2500)
DOSSIER_AGENT_DIGEST_CHARS: int = cfg("rl.dossier_agent_digest_chars", env="DOSSIER_AGENT_DIGEST_CHARS", fallback=1500)
DOSSIER_MAX_NEW_OBS_PER_DAY: int = cfg("rl.dossier_max_new_obs_per_day", env="DOSSIER_MAX_NEW_OBS_PER_DAY", fallback=3)
# Post-cap dossiers (30 obs/20 guidance/12 questions/10 catalysts) serialize well under this
# limit, so this cut is a safety net only — not expected to bite in normal operation.
DOSSIER_DISTILL_INPUT_MAX_CHARS: int = cfg("rl.dossier_distill_input_max_chars", env="DOSSIER_DISTILL_INPUT_MAX_CHARS", fallback=20000)
RL_CLAIMS_ENABLED: bool = cfg("rl.claims_enabled", env="RL_CLAIMS_ENABLED", fallback=True)
RL_LESSON_EMPHASIS_DELTA: float = cfg("rl.lesson_emphasis_delta", env="RL_LESSON_EMPHASIS_DELTA", fallback=0.03)
RL_LESSON_EMPHASIS_CAP: float = cfg("rl.lesson_emphasis_cap", env="RL_LESSON_EMPHASIS_CAP", fallback=0.06)
RL_LESSON_MATCH_MIN_CONF: float = cfg("rl.lesson_match_min_conf", env="RL_LESSON_MATCH_MIN_CONF", fallback=0.45)

# ── RL Phase 3 — Event-driven dossier ingestion (2026-06-12) ───────────────
# Weekly scan + on-demand CLI: digest qualifying NSE corporate events
# (results, concalls, guidance, investor presentations) into the existing
# TickerDossier via the same bounded merge the daily curator uses.
RL_EVENT_INGEST_ENABLED: bool = cfg("rl.event_ingest_enabled", env="RL_EVENT_INGEST_ENABLED", fallback=True)
EVENT_INGEST_LOOKBACK_DAYS: int = cfg("rl.event_ingest_lookback_days", env="EVENT_INGEST_LOOKBACK_DAYS", fallback=8)
EVENT_INGEST_MAX_EVENTS_PER_SCAN: int = cfg("rl.event_ingest_max_events_per_scan", env="EVENT_INGEST_MAX_EVENTS_PER_SCAN", fallback=3)
EVENT_INGEST_TEXT_MAX_CHARS: int = cfg("rl.event_ingest_text_max_chars", env="EVENT_INGEST_TEXT_MAX_CHARS", fallback=6000)

# ── RL Phase 4 — Research Loop (active open-question resolution) (2026-06-13) ─
# Weekly per-ticker pass: select unresolved dossier open_questions, run targeted
# Serper/Tavily searches built from the question text, judge via one batched LLM
# call, and write results back through the same bounded merge. Stale questions
# expire after RL_RESEARCH_MAX_ATTEMPTS. Flag off -> zero I/O.
RL_RESEARCH_LOOP_ENABLED: bool = cfg("rl.research_loop_enabled", env="RL_RESEARCH_LOOP_ENABLED", fallback=True)
RL_RESEARCH_MAX_QUESTIONS_PER_RUN: int = cfg("rl.research_max_questions_per_run", env="RL_RESEARCH_MAX_QUESTIONS_PER_RUN", fallback=2)
RL_RESEARCH_MAX_ATTEMPTS: int = cfg("rl.research_max_attempts", env="RL_RESEARCH_MAX_ATTEMPTS", fallback=3)
RL_RESEARCH_CONTEXT_MAX_CHARS: int = cfg("rl.research_context_max_chars", env="RL_RESEARCH_CONTEXT_MAX_CHARS", fallback=6000)

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
RL_CONTROL_LANE_ENABLED: bool = cfg("rl.control_lane_enabled", env="RL_CONTROL_LANE_ENABLED", fallback=True)

# Control-lane model; empty string -> settings.LLM_MODEL_REASONING.
CONTROL_LANE_MODEL: str = cfg("rl.control_lane_model", env="CONTROL_LANE_MODEL", fallback="")

# Monthly scorecard scheduler job (CronTrigger day 1, 02:00 IST).
SCORECARD_ENABLED: bool = cfg("rl.scorecard_enabled", env="SCORECARD_ENABLED", fallback=True)

# Persisted scorecard time series (PERMANENT — improvement history; volume).
SCORECARD_DIR: str = os.getenv("SCORECARD_DIR", "data/eval/scorecards")

# ---------------------------------------------------------------------------
# Living Envelope (RL Phase 2.5) — shock-robust forecasting (2026-06-13)
#
# Sticky regime hysteresis + shock-triggered mid-month re-forecast + pre-open
# sanity check. All flag-gated; flags off => byte-identical current behavior.
# ---------------------------------------------------------------------------

# Shock-triggered re-forecast (Component 2): regenerate the envelope mid-month
# when external_shock / thesis_break / regime_flip fires.
RL_REFORECAST_ENABLED: bool = cfg("rl.reforecast_enabled", env="RL_REFORECAST_ENABLED", fallback=True)

# Hard cap on regenerate_envelope() calls per ticker per calendar month.
RL_REFORECAST_MAX_PER_MONTH: int = cfg("rl.reforecast_max_per_month", env="RL_REFORECAST_MAX_PER_MONTH", fallback=2)

# thesis_break trigger fires when ThesisReviewer's horizon_confidence_multiplier
# drops to/below this threshold.
RL_REFORECAST_THESIS_MULT_THRESHOLD: float = cfg("rl.reforecast_thesis_mult_threshold", env="RL_REFORECAST_THESIS_MULT_THRESHOLD", fallback=0.5)

# Sticky regime (Component 1): hysteresis on top of the raw daily RegimeDetector
# label so a single calm day doesn't immediately exit RISK_OFF/MACRO_CRISIS.
RL_REGIME_STICKY_ENABLED: bool = cfg("rl.regime_sticky_enabled", env="RL_REGIME_STICKY_ENABLED", fallback=True)

# Consecutive milder-than-sticky detections required before exiting to the
# milder label.
RL_REGIME_CALM_DAYS: int = cfg("regime.calm_days", env="RL_REGIME_CALM_DAYS", fallback=3)

# Pre-open sanity check (Component 3): scheduler job at 08:45 IST on trading
# days, 1 Serper + 1 fast-tier LLM call market-wide.
RL_PREOPEN_CHECK_ENABLED: bool = cfg("rl.preopen_check_enabled", env="RL_PREOPEN_CHECK_ENABLED", fallback=True)

# Severity threshold (0.0-1.0) above which contradicted tickers trigger
# regenerate_envelope(reason="preopen_shock").
RL_PREOPEN_SHOCK_SEVERITY: float = cfg("rl.preopen_shock_severity", env="RL_PREOPEN_SHOCK_SEVERITY", fallback=0.7)

# ---------------------------------------------------------------------------
# Data integrity — NSE official close cross-check (2026-06)
#
# yfinance (get_price_history) is the sole source for RL scoring closes
# (daily_review actual close + generate_forecast re-forecast base close) but
# is an unofficial scraper that has served the WRONG COMPANY's price under
# symbol-cache poisoning and has regular outage days. NSE's official EOD
# close (fetch_equity_historical_data) is used as a cross-check via
# services/data/fetchers/close_verifier.get_verified_close().
# ---------------------------------------------------------------------------
CLOSE_VERIFY_ENABLED: bool = cfg("rl.close_verify_enabled", env="CLOSE_VERIFY_ENABLED", fallback=True)

# Max % difference between yfinance and NSE closes considered "agreement".
# Differences beyond this trigger a WARNING log and use the NSE value
# (poisoning detector).
CLOSE_VERIFY_TOLERANCE_PCT: float = cfg("rl.close_verify_tolerance_pct", env="CLOSE_VERIFY_TOLERANCE_PCT", fallback=1.0)

# ---------------------------------------------------------------------------
# Unified Sector Analyst (2026-06-12 redesign) — one data bundle + one
# reasoning-model call replaces the per-sector parallel agent fan-out.
# CSV of sector names on the unified path; "" disables it everywhere.
# ---------------------------------------------------------------------------
UNIFIED_ANALYST_SECTORS: str = cfg(
    "unified_analyst.sectors", env="UNIFIED_ANALYST_SECTORS",
    fallback="automobile,banking_bfsi,it_sector,renewable_energy,generic",
)
UNIFIED_ANALYST_FALLBACK_LEGACY: bool = cfg("unified_analyst.fallback_legacy", env="UNIFIED_ANALYST_FALLBACK_LEGACY", fallback=True)
UNIFIED_ANALYST_MAX_TOKENS: int = cfg("unified_analyst.max_tokens", env="UNIFIED_ANALYST_MAX_TOKENS", fallback=6000)
UNIFIED_SECTION_MAX_CHARS: int = cfg("unified_analyst.section_max_chars", env="UNIFIED_SECTION_MAX_CHARS", fallback=2500)
UNIFIED_BUNDLE_MAX_CHARS: int = cfg("unified_analyst.bundle_max_chars", env="UNIFIED_BUNDLE_MAX_CHARS", fallback=18000)


def unified_analyst_sectors() -> set[str]:
    """Parsed UNIFIED_ANALYST_SECTORS; empty set when disabled."""
    return {s.strip() for s in UNIFIED_ANALYST_SECTORS.split(",") if s.strip()}


# ---------------------------------------------------------------------------
# Compass Phase A — Portfolio Core + Position Advisor (spec 2026-07-06)
# ---------------------------------------------------------------------------
PORTFOLIO_DATA_DIR: str = cfg("portfolio.data_dir", env="PORTFOLIO_DATA_DIR", fallback="data/portfolio")
PORTFOLIO_DEFAULT_USER_ID: str = cfg("portfolio.default_user_id", env="PORTFOLIO_DEFAULT_USER_ID", fallback="primary")
PORTFOLIO_MAX_MANAGED_TICKERS: int = cfg("portfolio.max_managed_tickers", env="PORTFOLIO_MAX_MANAGED_TICKERS", fallback=40)
PORTFOLIO_WEEKLY_REVIEW_WEEKDAY: int = cfg("portfolio.weekly_review_weekday", fallback=4)

ADVISOR_ENABLED: bool = bool(cfg("advisor.enabled", env="ADVISOR_ENABLED", fallback=True))
ADVISOR_NARRATE: bool = bool(cfg("advisor.narrate", fallback=True))
ADVISOR_ATR_PERIOD: int = cfg("advisor.atr_period", fallback=20)
ADVISOR_STOP_ATR_MULT: float = cfg("advisor.stop_atr_mult", fallback=3.0)
_DEFAULT_STOP_BUCKETS: dict[str, tuple[float, float]] = {
    "large": (8.0, 12.0),
    "mid":   (12.0, 18.0),
    "small": (15.0, 22.0),
}
ADVISOR_STOP_BUCKETS: dict[str, tuple[float, float]] = {
    k: tuple(v) for k, v in cfg("advisor.stop_buckets", fallback=_DEFAULT_STOP_BUCKETS).items()
}
ADVISOR_LARGE_CAP_FLOOR_CR: float = float(cfg("advisor.large_cap_floor_cr", fallback=65000))
ADVISOR_MID_CAP_FLOOR_CR: float = float(cfg("advisor.mid_cap_floor_cr", fallback=20000))
ADVISOR_TRIM_PROFIT_PCT: float = cfg("advisor.trim_profit_pct", fallback=25.0)
ADVISOR_REVERSION_PRIOR_ELEVATED: float = cfg("advisor.reversion_prior_elevated", fallback=0.20)
ADVISOR_CONFIDENCE_DECLINE_THRESHOLD: float = cfg("advisor.confidence_decline_threshold", fallback=0.05)
ADVISOR_ENVELOPE_FLAT_BAND_PCT: float = cfg("advisor.envelope_flat_band_pct", fallback=1.0)
ADVISOR_ADD_MIN_DIRECTION_ACCURACY: float = cfg("advisor.add_min_direction_accuracy", fallback=0.60)
ADVISOR_MAX_POSITION_PCT: float = cfg("advisor.max_position_pct", fallback=10.0)
ADVISOR_SECTOR_CONCENTRATION_WARN_PCT: float = cfg("advisor.sector_concentration_warn_pct", fallback=30.0)
ADVISOR_LTCG_WAIT_MIN_MONTHS: int = cfg("advisor.ltcg_wait_min_months", fallback=10)
ADVISOR_EARNINGS_GAP_DAYS: int = cfg("advisor.earnings_gap_days", fallback=3)

# ---------------------------------------------------------------------------
# Compass Phase B — Discovery funnel + generic sector graph (spec 2026-07-06)
# ---------------------------------------------------------------------------
DISCOVERY_ENABLED: bool = bool(cfg("discovery.enabled", env="DISCOVERY_ENABLED", fallback=False))
DISCOVERY_HISTORY_DAYS: int = int(cfg("discovery.history_days", fallback=550))
DISCOVERY_BHAVCOPY_DIR: str = cfg("discovery.bhavcopy_dir", fallback="data/market_cache/bhavcopy")
DISCOVERY_DATA_DIR: str = cfg("discovery.data_dir", fallback="data/discovery")
PAPER_PREDICTION_DATA_DIR: str = cfg(
    "discovery.paper_data_dir", env="PAPER_PREDICTION_DATA_DIR",
    fallback="data/rl/paper/predictions",
)
DISCOVERY_LIQUIDITY_FLOOR_CR: float = float(cfg("discovery.liquidity_floor_cr", fallback=5.0))
DISCOVERY_FLOAT_MCAP_FLOOR_CR: float = float(cfg("discovery.float_mcap_floor_cr", fallback=500.0))
DISCOVERY_MIN_PRICE: float = float(cfg("discovery.min_price", fallback=20.0))
DISCOVERY_MAX_PLEDGE_PCT: float = float(cfg("discovery.max_promoter_pledge_pct", fallback=25.0))
DISCOVERY_CIRCUIT_STREAK_MAX: int = int(cfg("discovery.circuit_streak_max", fallback=3))
DISCOVERY_SHORTLIST_SIZE: int = int(cfg("discovery.shortlist_size", fallback=80))
DISCOVERY_MAX_CANDIDATES: int = int(cfg("discovery.max_candidates", fallback=40))
DISCOVERY_DEEP_DIVE_COUNT: int = int(cfg("discovery.deep_dive_count", fallback=10))
DISCOVERY_SHELF_SIZE: int = int(cfg("discovery.shelf_size", fallback=10))
DISCOVERY_STALE_DAYS: int = int(cfg("discovery.stale_days", fallback=60))
DISCOVERY_MIN_CONVICTION: float = float(cfg("discovery.min_conviction", fallback=0.55))
DISCOVERY_INCLUDE_SME: bool = bool(cfg("discovery.include_sme", fallback=False))

_DISCOVERY_SIGNAL_WEIGHTS_FALLBACK: dict[str, float] = {
    "momentum": 0.30, "delivery_surge": 0.15, "volume_breakout": 0.15,
    "bulk_block": 0.15, "high_52wk_rs": 0.10, "insider_buying": 0.10,
    "mf_holding": 0.05,
}
DISCOVERY_SIGNAL_WEIGHTS: dict[str, float] = {
    str(k): float(v)
    for k, v in cfg("discovery.signal_weights", fallback=_DISCOVERY_SIGNAL_WEIGHTS_FALLBACK).items()
}

_GENERIC_AGENT_WEIGHTS_FALLBACK: dict[str, float] = {
    "business": 0.14, "fundamentals": 0.18, "valuation": 0.14, "technical": 0.12,
    "macro": 0.12, "risk": 0.12, "management": 0.09, "earnings": 0.09,
}
GENERIC_AGENT_WEIGHTS: dict[str, float] = {
    str(k): float(v)
    for k, v in cfg("generic_graph.agent_weights", fallback=_GENERIC_AGENT_WEIGHTS_FALLBACK).items()
}
