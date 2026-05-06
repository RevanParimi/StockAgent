"""Phase 4 code generation — Banking BFSI, IT, Renewable Energy sectors."""
import os

def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"  wrote {path}")


HEADER = '''"""Auto-generated agent file. Edit prompt strings to customise LLM behaviour."""
from __future__ import annotations
from typing import Any
from backend.shared.pipeline.base_agent import BaseAgent
from backend.shared.schemas.pipeline import AgentOutput, StockQuery
'''


def make_agent(sector_dir, sector_str, class_name, agent_name, system, user):
    path = f"src/backend/sectors/{sector_dir}/agents/{agent_name}.py"
    code = f'''{HEADER}

class {class_name}(BaseAgent):
    @property
    def sector(self) -> str: return "{sector_str}"
    @property
    def agent_name(self) -> str: return "{agent_name}"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = """{system}"""
        user = """{user}"""
        return system, user.format(
            ticker=query.ticker,
            company_name=query.company_name,
            analysis_date=query.analysis_date,
            context=context,
        )

    def _parse_output(self, data: dict, ticker: str) -> AgentOutput:
        return AgentOutput(
            agent=self.agent_name, ticker=ticker,
            overall_score=self._clamp(float(data.get("overall_score", 0.5))),
            key_positives=data.get("key_positives", []),
            key_risks=data.get("key_risks", []),
            summary=data.get("summary", ""),
            data_freshness=data.get("data_freshness", ""),
        )
'''
    write(path, code)


def make_prompt(sector_dir, agent_name, system, dimensions_str, sub_score_keys):
    sub_scores_schema = "\n".join(f'    "{k}": <float>,' for k in sub_score_keys)
    code = f'''"""Prompt templates for {sector_dir}/{agent_name}."""

SYSTEM_PROMPT = """{system}"""

ANALYSIS_PROMPT = """
{{ticker}} ({{company_name}}) as of {{analysis_date}}.

Context:
{{context}}

{dimensions_str}

Return ONLY valid JSON:
{{{{
  "overall_score": <0.0-1.0>,
  "sub_scores": {{{{
{sub_scores_schema}
  }}}},
  "key_positives": ["..."],
  "key_risks": ["..."],
  "summary": "<2-3 sentence summary>",
  "data_freshness": "<date/quarter>"
}}}}
"""
'''
    write(f"src/backend/sectors/{sector_dir}/prompts/{agent_name}.py", code)


def make_sub_scores(sector_dir, agents_sub_scores):
    """agents_sub_scores: list of (class_name, sub_score_keys)"""
    lines = ['"""Sector-specific sub-score Pydantic models."""\nfrom pydantic import BaseModel, Field\n']
    for class_name, keys in agents_sub_scores:
        lines.append(f'\nclass {class_name}(BaseModel):')
        for k in keys:
            lines.append(f'    {k}: float = Field(ge=0.0, le=1.0)')
    write(f"src/backend/sectors/{sector_dir}/schemas/sub_scores.py", "\n".join(lines) + "\n")


def make_settings(sector_dir, sector_label, tickers, weights_dict):
    w_lines = "\n".join(f'    "{k}": {v},' for k, v in weights_dict.items())
    t_list  = ", ".join(f'"{t}"' for t in tickers)
    code = f'''"""Sector-specific settings for {sector_label}."""
import os

AGENT_WEIGHTS: dict[str, float] = {{
{w_lines}
}}

TICKERS: list[str] = [{t_list}]
'''
    write(f"src/backend/sectors/{sector_dir}/config/settings.py", code)


def make_registry(sector_dir, agent_entries):
    """agent_entries: list of (key, class_name, module_name)"""
    imports = "\n".join(
        f"from backend.sectors.{sector_dir}.agents.{mod} import {cls}"
        for key, cls, mod in agent_entries
    )
    agents_dict = "\n".join(f'    "{key}": {cls}(),' for key, cls, mod in agent_entries)
    code = f'''"""Agent registry for {sector_dir}."""
from __future__ import annotations
{imports}
from backend.sectors.{sector_dir}.config.settings import AGENT_WEIGHTS

AGENTS: dict = {{
{agents_dict}
}}
WEIGHTS: dict[str, float] = AGENT_WEIGHTS
'''
    write(f"src/backend/sectors/{sector_dir}/config/registry.py", code)


def make_orchestrator(sector_dir, sector_name, class_name):
    code = f'''"""Orchestrator for {sector_name}."""
from __future__ import annotations
from backend.shared.pipeline.base_orchestrator import BaseSectorOrchestrator
from backend.sectors.{sector_dir}.config.registry import AGENTS

class {class_name}(BaseSectorOrchestrator):
    """Entry point for {sector_name} stock analysis."""
    SECTOR_NAME = "{sector_name}"

    def __init__(self) -> None:
        self._sub_agents = AGENTS
        super().__init__()
'''
    write(f"src/backend/sectors/{sector_dir}/pipeline/orchestrator.py", code)


def make_graph(sector_dir, sector_name):
    code = f'''"""LangGraph graph for {sector_name} sector."""
from langgraph.graph import END, START, StateGraph
try:
    from langgraph.types import RetryPolicy
except ImportError:
    from langgraph.pregel import RetryPolicy

from backend.shared.pipeline.graphs.nodes import (
    make_aggregate_node, make_dispatch_fn,
    make_input_rail_node, make_resolve_ticker_node, make_run_agent_node,
)
from backend.shared.pipeline.graphs.state import GraphState
from backend.sectors.{sector_dir}.config.registry import AGENTS, WEIGHTS

SECTOR = "{sector_name}"

_resolve_ticker = make_resolve_ticker_node(SECTOR)
_input_rail     = make_input_rail_node(SECTOR)
_run_agent      = make_run_agent_node(AGENTS, SECTOR)
_aggregate      = make_aggregate_node(WEIGHTS, SECTOR)
_dispatch       = make_dispatch_fn(list(AGENTS.keys()))

_workflow = StateGraph(GraphState)
_workflow.add_node("resolve_ticker", _resolve_ticker)
_workflow.add_node("input_rail", _input_rail)
_workflow.add_node("run_agent", _run_agent, retry=RetryPolicy(max_attempts=2))
_workflow.add_node("aggregate", _aggregate)
_workflow.add_edge(START, "resolve_ticker")
_workflow.add_edge("resolve_ticker", "input_rail")
_workflow.add_conditional_edges("input_rail", _dispatch)
_workflow.add_edge("run_agent", "aggregate")
_workflow.add_edge("aggregate", END)

graph = _workflow.compile()
graph.name = "{sector_name}"
'''
    write(f"src/backend/sectors/{sector_dir}/pipeline/graph.py", code)


def make_fetcher_stub(sector_dir, filename, description):
    code = f'''"""{description} — data fetcher stub for {sector_dir}.
Implement this to pull live data for the corresponding agent context builder.
"""
from __future__ import annotations


def fetch(ticker: str, **kwargs) -> str:
    """Return formatted context string. Raise on failure."""
    raise NotImplementedError(
        f"{{__name__}}.fetch() not yet implemented for {{ticker}}. "
        "Wire a real data source here."
    )
'''
    write(f"src/backend/sectors/{sector_dir}/data/fetchers/{filename}.py", code)


def make_context_builder(sector_dir, sector_label, agent_builder_map):
    """agent_builder_map: dict of agent_name -> body string for the _build_ method"""
    methods = []
    for agent_name, body in agent_builder_map.items():
        methods.append(f"    def _build_{agent_name}(self, query) -> str:\n{body}")

    methods_str = "\n\n".join(methods)
    code = f'''"""Context builder for {sector_label} sector."""
from __future__ import annotations
import logging
from backend.shared.schemas.pipeline import StockQuery

logger = logging.getLogger(__name__)


class {sector_dir.title().replace("_", "")}ContextBuilder:
    def build(self, agent_name: str, query: StockQuery, sector: str = "{sector_label}") -> tuple[str, bool]:
        from backend.shared.config import settings as _settings
        self._serper_key = _settings.get_serper_key(sector)
        fn = getattr(self, f"_build_{{agent_name}}", None)
        if fn is None:
            return self._build_generic(query), False
        try:
            return fn(query), True
        except Exception as exc:
            logger.error("[{sector_label}ContextBuilder] agent=%s ticker=%s: %s", agent_name, query.ticker, exc)
            return self._build_generic(query), False

{methods_str}

    def _build_generic(self, query) -> str:
        return (f"Stock: {{query.ticker}} | Company: {{query.company_name}} | "
                f"Exchange: {{query.exchange}} | Date: {{query.analysis_date}}\\n"
                "No specialised fetcher for this agent.")
'''
    write(f"src/backend/sectors/{sector_dir}/data/context/builder.py", code)


def shim(old_path, new_import_path, exported_names):
    names = ", ".join(exported_names)
    code = f'''# -- MIGRATION SHIM -- Real: {new_import_path}
from {new_import_path} import *  # noqa: F401, F403
from {new_import_path} import {names}  # noqa: F401
'''
    write(old_path, code)


# ═══════════════════════════════════════════════════════════════
# BANKING BFSI
# ═══════════════════════════════════════════════════════════════
BANKING_AGENTS = [
    ("fundamentals",    "BFSIFundamentalsAgent", "fundamentals",
     "Senior banking analyst specialising in Indian BFSI. Analyse credit quality, capital adequacy, and profitability. Return ONLY valid JSON.",
     "Analyse the fundamentals of {ticker} ({company_name}) as of {analysis_date}.\n\nContext:\n{context}",
     "Evaluate (score 0.0-1.0):\n1. asset_quality — Gross NPA, Net NPA, PCR\n2. net_interest — NIM trend, CASA ratio\n3. capital_adequacy — CRAR/CET1 vs RBI minimum\n4. profitability — RoA, RoE, credit cost, cost-to-income\n5. loan_mix — Retail vs corporate, secured vs unsecured",
     ["asset_quality","net_interest","capital_adequacy","profitability","loan_mix"]),
    ("risk",             "BFSIRiskAgent", "risk",
     "Credit risk specialist covering Indian banks and NBFCs. Return ONLY valid JSON.",
     "Risk assessment for {ticker} ({company_name}) as of {analysis_date}.\n\nContext:\n{context}",
     "Evaluate:\n1. asset_quality_trend — SMA slippage, restructured book\n2. concentration_risk — Top-5 borrower exposure\n3. deposit_stability — Wholesale deposit %, CASA trend\n4. regulatory_risk — RBI/SEBI penalties\n5. macro_sensitivity — Rate sensitivity, FX exposure",
     ["asset_quality_trend","concentration_risk","deposit_stability","regulatory_risk","macro_sensitivity"]),
    ("macro_policy",    "BFSIMacroPolicyAgent", "macro_policy",
     "Macro analyst covering the Indian banking system. Focus on RBI policy and systemic credit. Return ONLY valid JSON.",
     "Macro and policy environment for {ticker} ({company_name}) as of {analysis_date}.\n\nContext:\n{context}",
     "Evaluate:\n1. rbi_rate_cycle — Repo rate trajectory, MPC stance\n2. system_credit — Credit growth, deposit growth, CD ratio\n3. liquidity_conditions — LAF corridor, CRR/SLR impact\n4. regulatory_actions — Recent RBI/SEBI circulars\n5. fiscal_policy — Government borrowing, PSU bank recap, IBC",
     ["rbi_rate_cycle","system_credit","liquidity_conditions","regulatory_actions","fiscal_policy"]),
    ("institutional",   "BFSIInstitutionalAgent", "institutional",
     "Equity analyst tracking smart money flow for Indian banking stocks. Return ONLY valid JSON.",
     "Institutional and insider flow for {ticker} ({company_name}) as of {analysis_date}.\n\nContext:\n{context}",
     "Evaluate:\n1. fii_dii_flow — Net FII/DII buying over 1M and 3M\n2. promoter_holding — Promoter stake change, pledge %\n3. insider_trades — ESOP exercises, open-market purchases/sales\n4. analyst_changes — Rating upgrades/downgrades, target revisions\n5. institutional_conc — Mutual fund holding %, top-10 institutional",
     ["fii_dii_flow","promoter_holding","insider_trades","analyst_changes","institutional_conc"]),
    ("pattern_analysis","BFSIPatternAgent", "pattern_analysis",
     "Technical analyst specialising in Indian banking stocks. Return ONLY valid JSON.",
     "Technical and pattern analysis for {ticker} ({company_name}) as of {analysis_date}.\n\nContext:\n{context}",
     "Evaluate:\n1. price_cycle — 10-year cycle, rate-cut rally seasonality\n2. momentum — RSI (14d), MACD, Bollinger Bands\n3. breakout_zones — Key support/resistance\n4. relative_strength — Performance vs Nifty Bank, PSU Bank\n5. volume_pattern — OBV trend, accumulation/distribution",
     ["price_cycle","momentum","breakout_zones","relative_strength","volume_pattern"]),
    ("universe_setup",  "BFSIUniverseAgent", "universe_setup",
     "BFSI equity research analyst establishing peer group and index context. Return ONLY valid JSON.",
     "Universe setup and peer context for {ticker} ({company_name}) as of {analysis_date}.\n\nContext:\n{context}",
     "Evaluate:\n1. index_weight — Weight in Nifty Bank / PSU Bank\n2. peer_positioning — Rank among PSU/Private/SFB/NBFC peers\n3. market_cap_tier — Large/mid/small cap, free-float\n4. corporate_actions — Splits, bonuses, rights, mergers\n5. rebalancing_risk — Index inclusion/exclusion probability",
     ["index_weight","peer_positioning","market_cap_tier","corporate_actions","rebalancing_risk"]),
]

for key, cls, mod, system, user_base, dims, sub_keys in BANKING_AGENTS:
    make_agent("banking_bfsi", "bfsi", cls, key, system, user_base + "\n\n" + dims + "\n\nReturn ONLY valid JSON.")
    make_prompt("banking_bfsi", key, system, dims, sub_keys)

make_sub_scores("banking_bfsi", [(cls+"SubScores", keys) for _, cls, _, _, _, _, keys in BANKING_AGENTS])
make_settings("banking_bfsi", "Banking BFSI",
    ["HDFCBANK","ICICIBANK","SBIN","KOTAKBANK","AXISBANK","INDUSINDBK","BANKBARODA"],
    {"fundamentals":0.25,"risk":0.20,"macro_policy":0.20,"institutional":0.15,"pattern_analysis":0.15,"universe_setup":0.05})
make_registry("banking_bfsi", [(key, cls, mod) for key, cls, mod, *_ in BANKING_AGENTS])
make_orchestrator("banking_bfsi", "banking_bfsi", "BankingAgentOrchestrator")
make_graph("banking_bfsi", "banking_bfsi")
make_fetcher_stub("banking_bfsi", "rbi_data", "RBI website scraper — repo rate, CRR, SLR, circulars")
make_fetcher_stub("banking_bfsi", "npa_metrics", "BSE/NSE NPA/NIM quarterly data fetcher")
make_context_builder("banking_bfsi", "bfsi", {
    "fundamentals":    "        from services.data.fetchers.fundamentals import get_fundamentals_context\n        from services.data.fetchers.news import fetch_news_context\n        import datetime\n        today = datetime.date.today()\n        queries = [f\"{query.ticker} NPA NIM CASA capital adequacy {today.year}\"]\n        return get_fundamentals_context(query.ticker) + '\\n\\n' + fetch_news_context(queries, api_key=self._serper_key)",
    "risk":            "        from services.data.fetchers.news import fetch_news_context\n        import datetime\n        today = datetime.date.today()\n        queries = [f\"{query.company_name} NPA slippage restructured book {today.year}\", f\"{query.ticker} concentration CASA regulatory risk {today.year}\"]\n        return fetch_news_context(queries, api_key=self._serper_key)",
    "macro_policy":    "        from services.data.fetchers.macro import get_macro_context\n        from services.data.fetchers.news import fetch_news_context\n        import datetime\n        today = datetime.date.today()\n        queries = [f\"RBI MPC repo rate {today.strftime('%B')} {today.year}\", f\"India system credit growth deposit CD ratio {today.year}\"]\n        return get_macro_context() + '\\n\\n' + fetch_news_context(queries, api_key=self._serper_key)",
    "institutional":   "        from services.data.fetchers.fundamentals import get_fundamentals_context\n        from services.data.fetchers.news import fetch_news_context\n        import datetime\n        today = datetime.date.today()\n        queries = [f\"{query.ticker} FII DII promoter insider trade {today.year}\"]\n        return get_fundamentals_context(query.ticker) + '\\n\\n' + fetch_news_context(queries, api_key=self._serper_key)",
    "pattern_analysis":"        from core.intelligence.algorithms.indicators.fetcher import get_technical_context\n        return f'Stock: {query.ticker} | Company: {query.company_name} | Date: {query.analysis_date}\\n\\n' + get_technical_context(query.ticker)",
    "universe_setup":  "        from services.data.fetchers.news import fetch_news_context\n        import datetime\n        today = datetime.date.today()\n        queries = [f\"{query.ticker} Nifty Bank index weight peer comparison {today.year}\"]\n        return fetch_news_context(queries, api_key=self._serper_key)",
})

# Shim old banking paths
shim("core/sectors/banking/agents.py",
     "backend.sectors.banking_bfsi.config.registry",
     ["AGENTS", "WEIGHTS"])

print("Banking BFSI done")

# ═══════════════════════════════════════════════════════════════
# IT SECTOR
# ═══════════════════════════════════════════════════════════════
IT_AGENTS = [
    ("fundamentals",      "ITFundamentalsAgent",   "fundamentals",
     "Senior IT equity analyst covering Indian technology companies. Return ONLY valid JSON.",
     "Fundamental analysis of {ticker} ({company_name}) as of {analysis_date}.\n\nContext:\n{context}",
     "Evaluate:\n1. revenue_growth — QoQ/YoY revenue, constant-currency\n2. ebit_margins — EBIT margin trend 8 quarters\n3. deal_wins — TCV large deals, win rates\n4. attrition — 12M attrition %, fresher intake\n5. valuation — P/E, EV/Revenue, PEG vs peers",
     ["revenue_growth","ebit_margins","deal_wins","attrition","valuation"]),
    ("global_macro",      "ITGlobalMacroAgent",    "global_macro",
     "Global macro analyst tracking demand drivers for Indian IT. Return ONLY valid JSON.",
     "Global macro environment for {ticker} ({company_name}) as of {analysis_date}.\n\nContext:\n{context}",
     "Evaluate:\n1. us_tech_spend — US IT capex, enterprise software, cloud\n2. fed_rate_impact — Fed rate trajectory, client capex decisions\n3. usd_inr — USD/INR trend, hedge ratio\n4. geopolitical — US-China tech war, CHIPS Act, offshoring\n5. ma_activity — Global IT M&A multiples, consolidation",
     ["us_tech_spend","fed_rate_impact","usd_inr","geopolitical","ma_activity"]),
    ("risk_macro",        "ITRiskMacroAgent",      "risk_macro",
     "Risk analyst covering Indian IT companies. Return ONLY valid JSON.",
     "Risk assessment for {ticker} ({company_name}) as of {analysis_date}.\n\nContext:\n{context}",
     "Evaluate:\n1. visa_risk — H1B/L1 approval rates, visa reform\n2. ai_disruption — Revenue at risk from GenAI/automation\n3. client_concentration — Top-5 client revenue %, churn\n4. fx_hedge — INR/USD hedge coverage, derivatives\n5. talent_risk — Skilled talent supply, campus hiring",
     ["visa_risk","ai_disruption","client_concentration","fx_hedge","talent_risk"]),
    ("peer_benchmark",    "ITPeerBenchmarkAgent",  "peer_benchmark",
     "Equity analyst benchmarking Indian IT against TCS, Infosys, HCL, Wipro. Return ONLY valid JSON.",
     "Peer benchmarking for {ticker} ({company_name}) as of {analysis_date}.\n\nContext:\n{context}",
     "Evaluate relative positioning (0.0=worst, 1.0=best in peer group):\n1. revenue_growth_rank — QoQ/YoY revenue vs peers\n2. margin_rank — EBIT margin vs peer median\n3. deal_momentum_rank — TCV win rate vs peers\n4. return_metrics_rank — RoCE, dividend, buyback vs peers\n5. valuation_gap — Premium/discount to peer median P/E",
     ["revenue_growth_rank","margin_rank","deal_momentum_rank","return_metrics_rank","valuation_gap"]),
    ("pattern_analysis",  "ITPatternAgent",        "pattern_analysis",
     "Technical analyst covering Indian IT stocks. Return ONLY valid JSON.",
     "Technical analysis for {ticker} ({company_name}) as of {analysis_date}.\n\nContext:\n{context}",
     "Evaluate:\n1. price_cycle — 10yr cycle, quarter-end rebalancing\n2. momentum — RSI (14d), MACD crossover, BB width\n3. breakout_levels — Support/resistance, breakouts/breakdowns\n4. nifty_it_beta — Rolling 12M beta vs Nifty IT, alpha\n5. volume_quality — Volume trend, accumulation/distribution",
     ["price_cycle","momentum","breakout_levels","nifty_it_beta","volume_quality"]),
    ("sentiment",         "ITSentimentAgent",      "sentiment",
     "Sentiment analyst tracking news and social signals for Indian IT. Return ONLY valid JSON.",
     "Sentiment analysis for {ticker} ({company_name}) as of {analysis_date}.\n\nContext:\n{context}",
     "Evaluate:\n1. ai_narrative — GenAI deal announcements, AI transformation storyline\n2. layoff_signals — Workforce reduction news, bench utilisation\n3. management_tone — CFO/CEO interview sentiment, guidance language\n4. media_coverage — Volume and tone of news coverage\n5. social_buzz — LinkedIn/Twitter/Reddit IT community sentiment",
     ["ai_narrative","layoff_signals","management_tone","media_coverage","social_buzz"]),
    ("transcript_nlp",    "ITTranscriptNLPAgent",  "transcript_nlp",
     "NLP specialist extracting signals from earnings call transcripts. Return ONLY valid JSON.",
     "Transcript NLP for {ticker} ({company_name}) as of {analysis_date}.\n\nContext:\n{context}",
     "Evaluate:\n1. guidance_tone — Forward guidance: cautious/neutral/optimistic\n2. demand_signals — Client spending commentary, vertical demand\n3. margin_commentary — Management explanation of margin levers\n4. ai_deal_mentions — Frequency and conviction of GenAI references\n5. analyst_qa_tone — Quality of responses to analyst questions",
     ["guidance_tone","demand_signals","margin_commentary","ai_deal_mentions","analyst_qa_tone"]),
    ("insider_smart_money","ITInsiderAgent",       "insider_smart_money",
     "Analyst tracking insider and institutional smart-money flows for Indian IT. Return ONLY valid JSON.",
     "Insider and smart-money analysis for {ticker} ({company_name}) as of {analysis_date}.\n\nContext:\n{context}",
     "Evaluate:\n1. promoter_activity — Open-market buys/sells, ESOP exercise\n2. director_trades — Non-executive director trades pre/post results\n3. smart_money_flow — Tier-1 MF allocation changes\n4. short_interest — F&O put-call ratio, short-selling trend\n5. block_deals — Recent block/bulk deal activity and counterparties",
     ["promoter_activity","director_trades","smart_money_flow","short_interest","block_deals"]),
]

for key, cls, mod, system, user_base, dims, sub_keys in IT_AGENTS:
    make_agent("it_sector", "it", cls, key, system, user_base + "\n\n" + dims + "\n\nReturn ONLY valid JSON.")
    make_prompt("it_sector", key, system, dims, sub_keys)

make_sub_scores("it_sector", [(cls+"SubScores", keys) for _, cls, _, _, _, _, keys in IT_AGENTS])
make_settings("it_sector", "IT Sector",
    ["TCS","INFY","WIPRO","HCLTECH","TECHM","LTIM","COFORGE"],
    {"fundamentals":0.25,"global_macro":0.20,"risk_macro":0.15,"peer_benchmark":0.15,
     "pattern_analysis":0.10,"sentiment":0.08,"transcript_nlp":0.04,"insider_smart_money":0.03})
make_registry("it_sector", [(key, cls, mod) for key, cls, mod, *_ in IT_AGENTS])
make_orchestrator("it_sector", "it_sector", "ITAgentOrchestrator")
make_graph("it_sector", "it_sector")
make_fetcher_stub("it_sector", "deal_wins", "IT deal win announcement scraper — TCV, client name, vertical")
make_fetcher_stub("it_sector", "transcript",  "Earnings call transcript fetcher — Tavily/PDF extraction")
make_context_builder("it_sector", "it", {
    "fundamentals":      "        from services.data.fetchers.fundamentals import get_fundamentals_context\n        from services.data.fetchers.news import fetch_news_context\n        import datetime\n        today = datetime.date.today()\n        queries = [f\"{query.ticker} revenue growth deal wins TCV {today.year}\"]\n        return get_fundamentals_context(query.ticker) + '\\n\\n' + fetch_news_context(queries, api_key=self._serper_key)",
    "global_macro":      "        from services.data.fetchers.macro import get_macro_context\n        from services.data.fetchers.news import fetch_news_context\n        import datetime\n        today = datetime.date.today()\n        queries = [f\"US IT spending enterprise cloud capex {today.year}\", f\"USD INR impact Indian IT revenue {today.year}\"]\n        return get_macro_context() + '\\n\\n' + fetch_news_context(queries, api_key=self._serper_key)",
    "risk_macro":        "        from services.data.fetchers.macro import get_macro_context\n        from services.data.fetchers.news import fetch_news_context\n        import datetime\n        today = datetime.date.today()\n        queries = [f\"H1B visa denial rate US immigration {today.year}\", f\"GenAI automation Indian IT revenue risk {today.year}\"]\n        return get_macro_context() + '\\n\\n' + fetch_news_context(queries, api_key=self._serper_key)",
    "peer_benchmark":    "        from services.data.fetchers.fundamentals import get_fundamentals_context\n        from services.data.fetchers.news import fetch_news_context\n        import datetime\n        today = datetime.date.today()\n        queries = [f\"{query.ticker} vs TCS Infosys HCL revenue growth margin {today.year}\"]\n        return get_fundamentals_context(query.ticker) + '\\n\\n' + fetch_news_context(queries, api_key=self._serper_key)",
    "pattern_analysis":  "        from core.intelligence.algorithms.indicators.fetcher import get_technical_context\n        return f'Stock: {query.ticker} | Company: {query.company_name} | Date: {query.analysis_date}\\n\\n' + get_technical_context(query.ticker)",
    "sentiment":         "        from services.data.fetchers.news import fetch_news_context\n        import datetime\n        today = datetime.date.today()\n        queries = [f\"{query.company_name} GenAI AI deal layoff sentiment {today.year}\"]\n        return fetch_news_context(queries, api_key=self._serper_key)",
    "transcript_nlp":    "        from services.clients.tavily_fetcher import fetch_tavily_context\n        import datetime\n        today = datetime.date.today()\n        q = f'Q{((today.month-1)//3)+1} FY{today.year%100}'\n        queries = [f\"{query.company_name} earnings call transcript {q} {today.year}\"]\n        return fetch_tavily_context(queries, max_queries=2)",
    "insider_smart_money":"        from services.data.fetchers.fundamentals import get_fundamentals_context\n        from services.data.fetchers.news import fetch_news_context\n        import datetime\n        today = datetime.date.today()\n        queries = [f\"{query.ticker} promoter ESOP block deal FII {today.year}\"]\n        return get_fundamentals_context(query.ticker) + '\\n\\n' + fetch_news_context(queries, api_key=self._serper_key)",
})

shim("core/sectors/it/agents.py",
     "backend.sectors.it_sector.config.registry",
     ["AGENTS", "WEIGHTS"])

print("IT Sector done")

# ═══════════════════════════════════════════════════════════════
# RENEWABLE ENERGY
# ═══════════════════════════════════════════════════════════════
RE_AGENTS = [
    ("fundamentals",     "REFundamentalsAgent",      "fundamentals",
     "Project-finance analyst specialising in Indian renewable energy. Return ONLY valid JSON.",
     "Fundamental analysis of {ticker} ({company_name}) as of {analysis_date}.\n\nContext:\n{context}",
     "Evaluate:\n1. capacity_utilisation — CUF % vs technology benchmark\n2. ebitda_quality — EBITDA/MW trend, O&M cost control\n3. debt_serviceability — DSCR (target >= 1.2x), refinancing risk\n4. receivables — Receivables aging, DISCOM payment delays\n5. leverage — Project D/E, holdco leverage",
     ["capacity_utilisation","ebitda_quality","debt_serviceability","receivables","leverage"]),
    ("business",         "REBusinessAgent",          "business",
     "Energy sector analyst evaluating business quality of Indian renewable companies. Return ONLY valid JSON.",
     "Business quality for {ticker} ({company_name}) as of {analysis_date}.\n\nContext:\n{context}",
     "Evaluate:\n1. subsector_mix — Solar/Wind/Hydro/Hybrid %, diversification\n2. ppa_quality — PPA tariff level, tenor, counterparty quality\n3. pipeline_cred — Under-construction %, commissioning track record\n4. customer_divers — DISCOM diversification, C&I customer %\n5. geography_spread — MW by state, resource quality",
     ["subsector_mix","ppa_quality","pipeline_cred","customer_divers","geography_spread"]),
    ("valuation",        "REValuationAgent",         "valuation",
     "Valuation analyst for Indian renewable energy stocks using sector-specific multiples. Return ONLY valid JSON.",
     "Valuation analysis for {ticker} ({company_name}) as of {analysis_date}.\n\nContext:\n{context}",
     "Evaluate:\n1. ev_per_mw — EV/MW vs peer range (Solar: Rs 4-6Cr/MW, Wind: Rs 5-8Cr/MW)\n2. ev_ebitda — EV/EBITDA vs healthy range 15-25x\n3. tariff_vs_auction — Existing PPA vs MNRE auction L1 rates\n4. pipeline_dcf — Pipeline value with -25% haircut on unbuilt MW\n5. implied_irr — Implied equity IRR vs WACC (target spread >= 200bps)",
     ["ev_per_mw","ev_ebitda","tariff_vs_auction","pipeline_dcf","implied_irr"]),
    ("sentiment_policy", "RESentimentPolicyAgent",   "sentiment_policy",
     "Policy analyst and sentiment tracker for Indian renewable energy. Return ONLY valid JSON.",
     "Sentiment and policy analysis for {ticker} ({company_name}) as of {analysis_date}.\n\nContext:\n{context}",
     "Evaluate:\n1. mnre_auction_health — Recent auction GW awarded, tariff trajectory\n2. budget_allocation — Union Budget RE capex, green hydrogen funding\n3. policy_tailwinds — RPO targets, must-run status, ISTS waiver\n4. green_hydrogen — Company exposure to green H2 opportunity\n5. news_sentiment — Recent news tone: project wins, delays, support",
     ["mnre_auction_health","budget_allocation","policy_tailwinds","green_hydrogen","news_sentiment"]),
    ("technical",        "RETechnicalAgent",         "technical",
     "Technical analyst providing timing signals for Indian renewable energy stocks. Return ONLY valid JSON.",
     "Technical timing for {ticker} ({company_name}) as of {analysis_date}.\n\nContext:\n{context}",
     "Evaluate:\n1. moving_averages — 50-DMA vs 200-DMA (golden/death cross)\n2. rsi_signal — Weekly RSI: oversold < 35 bullish, overbought > 70 bearish\n3. macd_weekly — Weekly MACD crossover and histogram trend\n4. volume_catalyst — Volume surge on policy/MNRE news\n5. accumulation_zone — Price vs 52-week range, Fibonacci levels",
     ["moving_averages","rsi_signal","macd_weekly","volume_catalyst","accumulation_zone"]),
    ("risk",             "RERiskAgent",              "risk",
     "Risk specialist for Indian renewable energy projects. Return ONLY valid JSON.",
     "Risk assessment for {ticker} ({company_name}) as of {analysis_date}.\n\nContext:\n{context}",
     "Evaluate (1.0=low risk, 0.0=high risk — inverse scoring):\n1. discom_credit — DISCOM payment delays, UDAY/RDSS compliance\n2. regulatory_change — Retroactive tariff renegotiation, curtailment\n3. weather_resource — Monsoon variability, generation impact\n4. grid_integration — Transmission bottlenecks, curtailment %\n5. commodity_input — Steel/copper capex impact, module prices",
     ["discom_credit","regulatory_change","weather_resource","grid_integration","commodity_input"]),
]

for key, cls, mod, system, user_base, dims, sub_keys in RE_AGENTS:
    make_agent("renewable_energy", "re", cls, key, system, user_base + "\n\n" + dims + "\n\nReturn ONLY valid JSON.")
    make_prompt("renewable_energy", key, system, dims, sub_keys)

make_sub_scores("renewable_energy", [(cls+"SubScores", keys) for _, cls, _, _, _, _, keys in RE_AGENTS])
make_settings("renewable_energy", "Renewable Energy",
    ["ADANIGREEN","TATAPOWER","TORNTPOWER","CESC","SJVN","NHPC"],
    {"fundamentals":0.30,"business":0.25,"valuation":0.20,"sentiment_policy":0.15,"technical":0.10,"risk":0.00})
make_registry("renewable_energy", [(key, cls, mod) for key, cls, mod, *_ in RE_AGENTS])
make_orchestrator("renewable_energy", "renewable_energy", "RenewableAgentOrchestrator")
make_graph("renewable_energy", "renewable_energy")
make_fetcher_stub("renewable_energy", "mnre_data",   "MNRE tender/auction announcement scraper")
make_context_builder("renewable_energy", "re", {
    "fundamentals":    "        from services.data.fetchers.fundamentals import get_fundamentals_context\n        from services.data.fetchers.news import fetch_news_context\n        import datetime\n        today = datetime.date.today()\n        queries = [f\"{query.company_name} CUF EBITDA DSCR DISCOM receivables {today.year}\"]\n        return get_fundamentals_context(query.ticker) + '\\n\\n' + fetch_news_context(queries, api_key=self._serper_key)",
    "business":        "        from services.data.fetchers.news import fetch_news_context\n        import datetime\n        today = datetime.date.today()\n        queries = [f\"{query.company_name} PPA solar wind capacity commissioned {today.year}\", f\"{query.ticker} pipeline DISCOM C&I geography {today.year}\"]\n        return fetch_news_context(queries, api_key=self._serper_key)",
    "valuation":       "        from services.data.fetchers.fundamentals import get_fundamentals_context\n        from services.data.fetchers.news import fetch_news_context\n        import datetime\n        today = datetime.date.today()\n        queries = [f\"{query.ticker} EV per MW EV EBITDA valuation solar wind peer {today.year}\"]\n        return get_fundamentals_context(query.ticker) + '\\n\\n' + fetch_news_context(queries, api_key=self._serper_key)",
    "sentiment_policy":"        from services.clients.tavily_fetcher import fetch_tavily_context\n        from services.data.fetchers.news import fetch_news_context\n        import datetime\n        today = datetime.date.today()\n        tavily = fetch_tavily_context([f'MNRE renewable energy auction {today.year} GW awarded tariff'], max_queries=2)\n        news = fetch_news_context([f'{query.company_name} MNRE project win budget {today.year}'], api_key=self._serper_key)\n        return f'[Policy — Tavily]\\n{tavily}\\n\\n[Sector news]\\n{news}'",
    "technical":       "        from core.intelligence.algorithms.indicators.fetcher import get_technical_context\n        return f'Stock: {query.ticker} | Company: {query.company_name} | Date: {query.analysis_date}\\n\\n' + get_technical_context(query.ticker)",
    "risk":            "        from services.data.fetchers.news import fetch_news_context\n        import datetime\n        today = datetime.date.today()\n        queries = [f\"{query.company_name} DISCOM payment delay curtailment grid {today.year}\", f\"{query.ticker} weather monsoon solar wind generation risk {today.year}\"]\n        return fetch_news_context(queries, api_key=self._serper_key)",
})

shim("core/sectors/renewable/agents.py",
     "backend.sectors.renewable_energy.config.registry",
     ["AGENTS", "WEIGHTS"])

print("Renewable Energy done")

if __name__ == "__main__":
    print("Phase 4 generation complete")
