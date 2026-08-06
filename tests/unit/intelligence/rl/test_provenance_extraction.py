"""F3 (sensing audit) — the pure provenance parser.

`extract_context_evidence` turns the news/macro bullets that already sit in
`market_context_today` into short "date — headline" provenance strings, so the
artifacts learned from a day's context (lessons, dossier observations) record
WHAT they were learned from instead of only the conclusion.

Pure function, no I/O, never raises: a bad context string must degrade to [],
never break a daily review.
"""
from core.intelligence.rl.provenance import extract_context_evidence

# Exactly the shape services/data/fetchers/news.py::_recent_article_lines emits.
_NEWS_BLOCK = (
    "• [Date: 2026-08-04] [Mint] Yes Bank Q1 profit doubles: net profit rose 104%.\n"
    "• [Date: 2026-08-03] Yes Bank board approves fundraise: board cleared Rs 5,000 cr.\n"
)

# Exactly the shape MacroNewsCache.get_for_daily_review emits.
_MACRO_BLOCK = (
    "[MARKET-WIDE CONTEXT — company-specific news unavailable]\n"
    "These are market/macro events, NOT news about this stock.\n"
    "• [2026-08-04] [HIGH] RBI holds repo rate — policy unchanged [tags: rates]\n"
)


def test_extracts_date_and_headline_from_company_news_bullet():
    evidence = extract_context_evidence(_NEWS_BLOCK, max_items=3)

    assert len(evidence) == 2
    assert evidence[0].startswith("2026-08-04 — ")
    assert "Yes Bank Q1 profit doubles" in evidence[0]


def test_caps_at_max_items_keeping_the_first_bullets():
    evidence = extract_context_evidence(_NEWS_BLOCK, max_items=1)

    assert len(evidence) == 1
    assert evidence[0].startswith("2026-08-04 — ")


def test_macro_bullets_are_marked_market_wide():
    """F2 injects market-wide items into the same string. Provenance must never
    let a macro headline read as company-specific evidence."""
    evidence = extract_context_evidence(_NEWS_BLOCK + _MACRO_BLOCK, max_items=5)

    company = [e for e in evidence if not e.startswith("market-wide ")]
    macro = [e for e in evidence if e.startswith("market-wide ")]
    assert len(company) == 2
    assert macro == ["market-wide 2026-08-04 — [HIGH] RBI holds repo rate — "
                     "policy unchanged [tags: rates]"]


def test_undated_bullet_is_skipped():
    """No date, no provenance — the AUD-041 rule applied to what we persist."""
    evidence = extract_context_evidence(
        "• [Date: date unknown] Some headline: body\n"
        "• A bullet with no bracket at all\n",
        max_items=3,
    )

    assert evidence == []


def test_non_bullet_noise_yields_nothing():
    noise = (
        "Market context unavailable.\n"
        "[No results for: YESBANK NSE India company news]\n"
        "[SEASONAL CONTEXT — pre-seeded domain knowledge, not from live news]\n"
        "Active patterns: results_season\n"
    )

    assert extract_context_evidence(noise, max_items=3) == []


def test_duplicate_bullets_are_deduplicated():
    evidence = extract_context_evidence(_NEWS_BLOCK + _NEWS_BLOCK, max_items=5)

    assert len(evidence) == 2


def test_long_bullet_is_truncated_to_max_chars():
    long_bullet = "• [Date: 2026-08-04] " + ("x" * 500) + "\n"

    evidence = extract_context_evidence(long_bullet, max_items=1, max_chars=60)

    assert len(evidence) == 1
    assert len(evidence[0]) <= 60


def test_empty_context_yields_empty_list():
    assert extract_context_evidence("", max_items=3) == []
    assert extract_context_evidence(None, max_items=3) == []  # type: ignore[arg-type]


def test_zero_max_items_yields_empty_list():
    assert extract_context_evidence(_NEWS_BLOCK, max_items=0) == []
