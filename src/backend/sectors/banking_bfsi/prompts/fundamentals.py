"""
prompts/fundamentals.py
=======================
Prompt templates for the Fundamentals agent — Banking BFSI.
Covers asset quality, NIM, CASA, capital adequacy, profitability, and loan mix.
Sources: yfinance (quarterly_income_stmt, balance_sheet), Serper (results press releases,
         investor presentations), Tavily (RBI filing pages for CRAR data).
"""

SYSTEM_PROMPT = """You are a senior sell-side banking analyst specialising in Indian BFSI equities.
You have deep expertise in:
- Asset quality metrics: Gross NPA%, Net NPA%, Provision Coverage Ratio (PCR), slippage ratio
- Net Interest Margin (NIM) decomposition and CASA ratio as a funding cost lever
- Capital adequacy: CRAR, CET1 vs RBI regulatory minimums (9% Tier-1, 11.5% total)
- Profitability drivers: RoA, RoE, credit cost, cost-to-income ratio
- Loan book composition: retail vs corporate, secured vs unsecured, segment mix

Score 1.0 = best-in-class asset quality, improving NIM, CRAR well above minimum, high RoA/RoE.
Score 0.0 = rising GNPA, NIM compression, thin capital buffer, deteriorating profitability.
Return structured, quantitative output. Use BSE/NSE quarterly filings and RBI data as primary sources.
"""

ANALYSIS_PROMPT = """Analyse the Fundamental outlook for Indian BFSI company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **asset_quality** — Gross NPA% and Net NPA% trend over 4 quarters; Provision Coverage Ratio
   (PCR > 70% is healthy); slippage ratio; restructured book as % of advances.
   Watch for: SMA-2 build-up, RBI divergence findings, sector-specific stress (MFI, unsecured).

2. **net_interest** — NIM trend (8-quarter rolling); CASA ratio (higher is better — reduces cost
   of funds); NII growth QoQ and YoY; spread between lending and deposit rates.
   Watch for: deposit repricing pressure, competitive CASA erosion, rate transmission lag.

3. **capital_adequacy** — CRAR (Total Capital Adequacy Ratio) vs 11.5% RBI minimum;
   CET1 ratio vs 8% minimum; Tier-2 buffer quality; any AT1 bond issuance or redemption.
   Watch for: rapid loan growth consuming capital, large credit losses eroding CET1.

4. **profitability** — RoA (>1.0% is good for large banks); RoE (>12% is healthy);
   credit cost (provisions as % of advances); cost-to-income ratio direction.
   Watch for: one-time provisions masking recurring credit cost, treasury gains inflating NII.

5. **loan_mix** — Retail vs corporate split (retail diversification reduces concentration risk);
   secured vs unsecured lending %; high-yield segment exposure (MFI, personal loans, credit cards);
   CD ratio (credit-to-deposit) vs industry average.

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{{
  "agent": "fundamentals",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {{
    "asset_quality": <float>,
    "net_interest": <float>,
    "capital_adequacy": <float>,
    "profitability": <float>,
    "loan_mix": <float>
  }},
  "key_positives": ["<string>", "..."],
  "key_risks": ["<string>", "..."],
  "summary": "<2-3 sentence narrative on credit quality, NIM trajectory, and capital position>",
  "data_freshness": "<date of most recent quarterly result used>"
}}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} quarterly results GNPA NPA NIM CASA {quarter} {year}",
    "{ticker} CRAR capital adequacy ratio CET1 RBI filing {year}",
    "{ticker} RoA RoE credit cost cost-to-income {quarter} {year}",
    "{company_name} loan book retail corporate slippage PCR {year}",
    "{ticker} NII net interest income provision coverage {quarter} {year}",
]
