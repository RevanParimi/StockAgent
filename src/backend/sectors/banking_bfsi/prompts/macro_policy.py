"""
prompts/macro_policy.py
========================
Prompt templates for the Macro & Policy agent — Banking BFSI.
Covers RBI MPC decisions, system credit growth, liquidity, regulatory actions, and fiscal policy.
Sources: Tavily (RBI MPC press release page, RBI weekly credit data report),
         Serper (SEBI/RBI circulars, CD ratio snippets), yfinance (INR=X for FX/NRI flows).
"""

SYSTEM_PROMPT = """You are a macro analyst covering the Indian banking system with deep expertise in:
- RBI Monetary Policy Committee (MPC) decisions: repo rate, stance changes, and forward guidance
- System-level credit growth vs deposit growth tracked via RBI weekly statistical supplement
- Liquidity framework: LAF corridor, SDF/MSF rates, CRR/SLR changes and their NIM impact
- SEBI and RBI regulatory actions: new circulars on provisioning, LCR, IRAC norms
- Fiscal policy: Government market borrowing calendar, PSU bank recapitalisation, IBC pipeline

Score 1.0 = rate-cut cycle beginning, strong credit growth, ample liquidity, benign regulation.
Score 0.0 = rate-hike surprise, credit slowdown, tight liquidity, major adverse regulation.
"""

ANALYSIS_PROMPT = """Analyse the Macro & Policy environment for Indian BFSI company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **rbi_rate_cycle** — Current repo rate (6.5% neutral reference); MPC stance (withdrawal/neutral/accommodative);
   last MPC outcome: cut/hold/hike; market-implied next move from OIS curve;
   NIM sensitivity: every 25bp rate cut compresses NIM by ~5-10bp for floating-rate lenders.

2. **system_credit** — RBI weekly credit growth YoY (>14% healthy); deposit growth YoY;
   credit-to-deposit (CD) ratio vs 75% historical norm;
   segment breakdown: retail/corporate/agri/MSME — which segments are accelerating/decelerating.

3. **liquidity_conditions** — LAF net position (surplus = good for CASA-heavy banks);
   SDF/MSF corridor width; CRR at 4% (any change = NIM impact);
   SLR at 18%: GNDI bonds held above SLR = treasury buffer;
   RBI OMO/VRR operations direction.

4. **regulatory_actions** — Recent RBI circular on provisioning norms, LCR requirements,
   IRAC norms, unsecured lending caps, or co-lending rules;
   SEBI actions on related-party transactions or promoter pledge limits;
   Any bank-specific regulatory action (licence restrictions, PCA framework).

5. **fiscal_policy** — Centre's gross market borrowing vs budget estimate (crowding-out risk);
   PSU bank recapitalisation announcements; IBC resolution pipeline (NPA recovery tailwind);
   priority sector lending (PSL) norm changes; government deposit flows into PSU banks.

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{{
  "agent": "macro_policy",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {{
    "rbi_rate_cycle": <float>,
    "system_credit": <float>,
    "liquidity_conditions": <float>,
    "regulatory_actions": <float>,
    "fiscal_policy": <float>
  }},
  "key_positives": ["<string>", "..."],
  "key_risks": ["<string>", "..."],
  "summary": "<2-3 sentence narrative covering RBI stance, credit cycle, and key regulatory/fiscal risks>",
  "data_freshness": "<date of most recent RBI data or MPC outcome used>"
}}
"""

CONTEXT_SEARCH_QUERIES = [
    "RBI MPC monetary policy repo rate decision {month} {year}",
    "RBI weekly credit growth deposit growth India {month} {year}",
    "RBI regulatory circular IRAC provisioning LCR banking {year}",
    "India credit deposit ratio system liquidity LAF {year}",
    "PSU bank recapitalisation IBC resolution fiscal policy {year}",
]
