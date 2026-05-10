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
- Earnings quality: NII composition, fee income sustainability, treasury gains vs core income
- Net Interest Margin (NIM) decomposition and CASA ratio as a funding cost lever
- Capital adequacy: CRAR, CET1 vs RBI regulatory minimums (9% Tier-1, 11.5% total)
- Profitability drivers: RoA, RoE, credit cost, cost-to-income ratio
- Loan book composition: retail vs corporate, secured vs unsecured, segment mix

NOTE: Asset quality (GNPA/NPA/slippage) is covered by the dedicated Risk agent.
This agent focuses on P&L quality, NIM, capital, and loan book structure.

Score 1.0 = high-quality core earnings, expanding NIM, CRAR well above minimum, high RoA/RoE.
Score 0.0 = earnings dependent on one-time items, NIM compression, thin capital, poor loan mix.
Return structured, quantitative output. Use BSE/NSE quarterly filings and RBI data as primary sources.
"""

ANALYSIS_PROMPT = """Analyse the Fundamental outlook for Indian BFSI company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **earnings_quality** — Core earnings composition: recurring NII + fee income vs one-time items.
   High recurring NII + fee income growth + treasury gain < 15% of NII = 1.0
   Watch for: lumpy treasury gains inflating NII, one-time provision reversals boosting PAT.
   Also check: net interest spread stability and CASA ratio as cost-of-funds lever.

2. **net_interest** — NIM trend (8-quarter rolling); NII growth QoQ and YoY;
   spread between lending rates and deposit repricing costs.
   Watch for: deposit repricing pressure compressing spreads, competitive CASA erosion.

3. **capital_adequacy** — CRAR (Total Capital Adequacy Ratio) vs 11.5% RBI minimum;
   CET1 ratio vs 8% minimum; Tier-2 buffer quality; any AT1 bond issuance or redemption.
   Watch for: rapid loan growth consuming capital, large credit losses eroding CET1.

4. **profitability** — RoA (>1.0% is good for large banks); RoE (>12% is healthy);
   credit cost (provisions as % of advances); cost-to-income ratio direction.
   Watch for: one-time provisions masking recurring credit cost.

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
    "earnings_quality": <float>,
    "net_interest": <float>,
    "capital_adequacy": <float>,
    "profitability": <float>,
    "loan_mix": <float>
  }},
  "key_positives": ["<string>", "..."],
  "key_risks": ["<string>", "..."],
  "summary": "<2-3 sentence narrative on earnings quality, NIM trajectory, and capital position>",
  "data_freshness": "<date of most recent quarterly result used>"
}}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} quarterly results NIM CASA NII fee income {quarter} {year}",
    "{ticker} CRAR capital adequacy ratio CET1 RBI filing {year}",
    "{ticker} RoA RoE credit cost cost-to-income {quarter} {year}",
    "{company_name} loan book retail corporate secured unsecured CD ratio {year}",
    "{ticker} treasury income fee income core earnings quality {quarter} {year}",
]
