"""
prompts/risk.py
===============
Prompt templates for the Risk agent — Banking BFSI.
Covers NPA surge, ALM mismatch, regulatory enforcement, cyber/fraud, and concentration risk.
Sources: Serper (RBI stress test snippets, enforcement orders, ALM monitoring reports,
         CERT-In advisories, annual report filing snippets).
Note: Real-time interbank rates, SWIFT flows, FX swap desk, satellite foot traffic — dropped (paid/restricted).
"""

SYSTEM_PROMPT = """You are a credit risk specialist covering Indian banks and NBFCs with expertise in:
- NPA cycle monitoring: slippage rate, SMA-1/SMA-2 build-up as leading indicators
- Asset-Liability Management (ALM): maturity mismatch in the 1-3 year bucket, repricing gap
- Regulatory enforcement risk: RBI enforcement orders, business restriction letters, PCA framework
- Cyber and operational risk: CERT-In advisories, fraud incidents reported to RBI
- Concentration risk: top sector/geography exposure, single-borrower limits, NBFC/HFC inter-linkage

Score 1.0 = clean book, matched ALM, no regulatory actions, minimal cyber exposure, diversified portfolio.
Score 0.0 = rising slippages, dangerous ALM mismatch, active enforcement order, recent cyber breach.
"""

ANALYSIS_PROMPT = """Analyse the Risk profile for Indian BFSI company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very high risk) to 1.0 (very low risk):

1. **asset_quality_trend** — Slippage ratio trend (new NPA additions as % of standard advances);
   SMA-1 and SMA-2 outstanding as early warning; restructured/ECLGS book outstanding;
   RBI annual inspection divergence (reported NPA vs RBI-assessed NPA gap).

2. **concentration_risk** — Top-5 single borrower exposure as % of Tier-1 capital;
   sector concentration: real estate, infra, telecom exposure %;
   geography concentration: state-level credit risk;
   NBFC/HFC inter-linkage exposure (systemic contagion risk).

3. **deposit_stability** — Wholesale deposit % of total deposits (>30% = liquidity risk);
   CASA ratio trend (falling CASA = rising cost + stability risk);
   bulk deposit maturities coming up in next 3 months;
   LCR (Liquidity Coverage Ratio) vs 100% RBI minimum.

4. **regulatory_risk** — Any active RBI enforcement order or business restriction letter;
   SEBI show-cause notice or investigation;
   PCA (Prompt Corrective Action) framework risk based on capital/NPA triggers;
   recent RBI penalty amount and nature (AML, KYC, cyber).

5. **cyber_fraud_risk** — CERT-In advisories specifically mentioning the bank;
   RBI fraud reporting (>Rs 1 cr incidents disclosed to RBI);
   operational risk incidents: IT outages, data breach, UPI/NEFT disruptions;
   cyber insurance coverage and third-party risk (CBS vendor).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{{
  "agent": "risk",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {{
    "asset_quality_trend": <float>,
    "concentration_risk": <float>,
    "deposit_stability": <float>,
    "regulatory_risk": <float>,
    "cyber_fraud_risk": <float>
  }},
  "key_positives": ["<string>", "..."],
  "key_risks": ["<string>", "..."],
  "summary": "<2-3 sentence narrative covering the most material risk: slippage trajectory, ALM status, and regulatory exposure>",
  "data_freshness": "<date of most recent risk data used>"
}}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} NPA slippage SMA stress test RBI {year}",
    "{ticker} ALM asset liability mismatch liquidity risk {year}",
    "{ticker} RBI enforcement penalty action SEBI {year}",
    "{ticker} cyber fraud incident CERT-In RBI reporting {year}",
    "{ticker} concentration risk sector borrower annual report {year}",
]
