# Industry lenses (PR-032)

One file per industry group. The general path (stocks outside automobiles, banking, IT and
renewables) reads them only when `lenses.enabled` is on in `config.yaml`; the four sector paths
never do. Code: `services/data/context/lenses.py`. Design: section 4.1 of
`docs/superpowers/specs/2026-09-26-one-engine-sector-lenses-design.md` (this is its first slice;
SA-026 extends these files and never makes a second format).

```yaml
id: cement                      # equals the file name
display: "Cement"
industries:                     # Yahoo Finance industry labels; each in one lens only
  - "Building Materials"
kpis:                           # 1 to 8: the numbers that move this industry's profits
  - "realisation per tonne"
news_terms: "results volumes realisation capacity"     # added to the company-news search
sector_query: "India cement prices demand volumes capacity news {month} {year}"
policy_query: "{company_name} cement volumes realisation EBITDA per tonne capacity expansion {year}"
macro_drivers:                  # 1 to 4: named in the macro-news search and the block
  - "coal petcoke prices"
```

- `sector_query` may use `{month}` and `{year}`; `policy_query` `{company_name}`, `{ticker}` and
  `{year}`; `news_terms` none. No field may say "generic".
- A stock whose Yahoo label no lens lists gets the **default lens**: its sector search is
  "India {label} industry demand prices policy news {month} {year}". A stock with no label keeps
  today's wording (but its macro search no longer names the graph).
- **Writing one:** `python scripts/lenses/draft_lens.py --id <id> --display "<name>" --industry
  "<Yahoo label>"` drafts it with one model call from a fixed brief and checks it. Read the draft,
  edit it and commit it here; nothing is written at run time.
- **Which to write next:** the weekly discovery log line "Discovery lenses" names the general-path
  dives' industries without a lens, and `scripts/lenses/coverage_report.py` counts the last 8
  weeks.
- **Checked** by the server at startup (an ERROR line, and today's wording, if a file is broken)
  and by the test suite (`tests/unit/test_lenses_pr032.py`).
