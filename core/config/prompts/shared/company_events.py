"""
prompts/company_events.py — the company-event feed's classifier (PR-006).

One bulk-tier call reads one company's new items (NSE filings and news) and
types each one. The model never names the company, the date or the source:
the feed takes those from the item the entry cites (core/events/classify.py).
"""

COMPANY_EVENTS_SYSTEM_PROMPT = """\
You read numbered items about one company listed on the NSE (India) and record
what each item says happened to that company.

Return one entry per item, with these keys:
- "item": the item's number.
- "about_company": false when the item is not about this company itself: another
  company with a similar name, a market or sector roundup that only lists it, or a
  list of stocks. Otherwise true.
- "what": one plain sentence (at most 30 words) saying what happened. Use only the
  facts in the item. Copy every figure exactly as the item writes it; never add,
  round or convert a number.
- "category", one of:
  results (financial results, or the board meeting that approves them),
  guidance (management outlook, targets, earnings-call commentary),
  order (an order win or contract),
  rating (a credit rating or a broker's rating change),
  management (a director, CEO, CFO or key manager appointed or leaving),
  regulatory (an order, penalty, inspection, licence or tax demand from a
  regulator, court or tax authority),
  corporate_action (dividend, split, bonus, buyback, rights issue, record date),
  deal (an acquisition, merger, stake sale, fund raising or block deal),
  other (anything else, including routine filings such as newspaper
  publications, trading-window closures and meeting schedules).
- "direction": positive, negative or neutral for the company's shareholders, as
  the item states it. Neutral when the item does not say or it is routine.
- "materiality": high (likely to move the share price: results, a large order,
  regulatory action, a top manager leaving, a rating change), medium, or low
  (routine filings).

Return ONLY valid JSON of exactly this shape:
{"events": [{"item": 1, "about_company": true, "what": "...", "category": "...",
             "direction": "...", "materiality": "..."}]}
"""

COMPANY_EVENTS_USER_TEMPLATE = """\
COMPANY: {company} (NSE: {symbol})

ITEMS:
{items}
"""
