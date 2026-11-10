"""
The company-event feed: what happened to each held, watched and shelf stock,
typed, dated and sourced (KT section 4).

- `feed.run_event_feed` — one run (scheduler jobs company_events_am/_pm)
- `sources` — NSE filings and news results as cited items
- `classify` — the bulk-tier classifier and its grounding checks
- `store.EventStore` — data/events/<SYMBOL>.jsonl, market facts only

Outside the intelligence plane on purpose: the feed reads users' holdings
and watchlists, and core/intelligence must never import the user plane.
"""
