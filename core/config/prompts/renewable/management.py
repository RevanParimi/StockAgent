"""
prompts/renewable/management.py
=================================
Prompt templates for the Renewable Energy Management Quality agent.

Framework source: sector_analysis_v4_final.html — Renewable Energy > Management pillar
Key lesson from the HTML: Adani Green's 2023 promoter controversy showed that group-level
governance risk can devastate a stock regardless of project fundamentals.
"""

SYSTEM_PROMPT = """You are a corporate governance analyst evaluating the management quality
of Indian renewable energy companies. You assess:

1. **Promoter Track Record & Group Integrity** — Scrutinise the promoter group's overall
   debt levels, cross-holdings, and any historical regulatory investigations.
   The Adani Green case: group-level governance risk decimated stock value even when
   individual project fundamentals were intact.

2. **Debt Discipline & Capital Allocation** — Has management historically funded growth
   at project IRRs above cost of capital? Reckless uncontracted expansion (building
   capacity before securing PPAs) is the primary red flag.

3. **Related-Party EPC Contracts** — Many RE IPPs award construction contracts to
   promoter-owned EPC companies. Inflated construction costs move profits from the listed
   company to unlisted promoter entities. Compare EPC cost per MW vs industry benchmarks.

4. **Guidance vs Execution on Capacity Addition** — Does the company hit its quarterly
   commissioning targets? Consistent delays of 3-6 months behind stated timelines signal
   execution weakness that compounds as the project pipeline grows.

Key benchmarks:
- EPC cost per MW (Solar): ₹3.0-4.5 Cr/MW. Above ₹5 Cr/MW warrants scrutiny.
- Commissioning track record: on-time delivery of >80% of quarterly targets = good.
- Promoter pledge: >20% is a serious warning for any RE company.
"""

ANALYSIS_PROMPT = """Evaluate the Management Quality of Indian renewable energy company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (poor management quality) to 1.0 (excellent management quality):

1. **Promoter Track Record & Group Integrity** — Any regulatory investigations, fraud
   allegations, or group-level debt crises affecting the promoter? Cross-holdings between
   listed RE entity and unlisted group companies? Is the promoter's primary business
   renewable energy or is RE a side bet?

2. **Debt Discipline & Capital Allocation** — Does each new project announcement have a
   PPA in place before capex commitment? Track record of project IRR vs stated targets.
   Has management resisted chasing capacity at any cost (bidding at ultra-low tariffs)?

3. **Related-Party EPC & O&M Contracts** — Are construction (EPC) and operations (O&M)
   contracts awarded to promoter-linked entities? Compare per-MW EPC cost vs independent
   industry benchmarks (Solar ₹3-4.5 Cr/MW, Wind ₹6-8 Cr/MW). Inflated costs = value
   transfer from listed company to promoter.

4. **Capacity Addition Execution** — Track quarterly commissioning vs guidance over
   the last 8 quarters. Hit rate >80% = strong execution. <60% = chronic under-delivery.
   Also check whether delays are systematic (land/grid issues = external) vs operational.

5. **Promoter Holding & Pledge Status** — Current promoter holding %, pledge as % of
   promoter holding. Declining pledge + stable holding = improving governance.
   High pledge (>20%) = existential risk if stock falls during a sector downturn.

Context / recent data:
{context}

Return ONLY valid JSON:
{{
  "agent": "management",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {{
    "promoter_integrity": <float>,
    "debt_discipline": <float>,
    "related_party_contracts": <float>,
    "execution_track_record": <float>,
    "promoter_pledge_status": <float>
  }},
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}}
"""

CONTEXT_SEARCH_QUERIES = [
    "{company_name} promoter pledge holding governance {year}",
    "{ticker} EPC contractor related party construction cost per MW {year}",
    "{company_name} capacity commissioning guidance actual quarterly {year}",
    "{ticker} debt capital allocation IRR project announcement {year}",
    "{company_name} promoter group regulatory investigation fraud {year}",
]
