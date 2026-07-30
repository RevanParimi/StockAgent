"""Compass Phase C — morning brief: assembly, rendering, run gating (spec §7)."""
from datetime import date
from unittest.mock import patch

import core.delivery.brief as br
from core.portfolio.store import PortfolioStore


def _digest():
    return {"date": "2026-07-08", "user_id": "u1", "portfolio_value": 110000.0,
            "cost_basis": 100000.0, "total_pnl_pct": 10.0,
            "holdings": [
                {"symbol": "OLDCO", "verdict": "EXIT", "close": 80.0,
                 "pnl_pct": -15.0, "reason": "stop breached", "notes": []},
                {"symbol": "GOODCO", "verdict": "HOLD", "close": 210.0,
                 "pnl_pct": 22.0, "reason": "thesis intact", "notes": []},
            ],
            "escalations": ["OLDCO"]}


def _mk_store(tmp_path, with_digest=True):
    store = PortfolioStore(user_id="u1", base_dir=str(tmp_path))
    if with_digest:
        store.save_digest(_digest())
    return store


def test_build_brief_assembles_sections(tmp_path, monkeypatch):
    store = _mk_store(tmp_path)
    monkeypatch.setattr(br, "_narrate_brief", lambda b: "Deterministic headline.")
    monkeypatch.setattr(br, "_read_regime", lambda: {"label": "RISK_OFF"})
    monkeypatch.setattr(br, "_overnight_items", lambda: [
        {"headline": "Fed shock", "severity": "HIGH"}])
    monkeypatch.setattr(br, "_shelf_events_since", lambda since: [
        {"event": "added", "symbol": "NEWCO", "detail": "conviction=0.72"}])
    monkeypatch.setattr(br, "_earnings_soon", lambda symbols, on: [
        {"symbol": "GOODCO", "date": "2026-07-10"}])
    monkeypatch.setattr(br, "_ipo_watch", lambda: [
        {"symbol": "SOON", "company": "Soon Ltd", "status": "upcoming"}])
    monkeypatch.setattr(br, "upcoming_lockin_alerts", lambda on, symbols=None: [])

    brief = br.build_morning_brief("u1", date(2026, 7, 9), store=store)
    assert brief["kind"] == "morning_brief" and brief["date"] == "2026-07-09"
    assert brief["portfolio"]["total_pnl_pct"] == 10.0
    assert brief["advisor_flags"] == [
        {"symbol": "OLDCO", "verdict": "EXIT", "reason": "stop breached", "notes": []}]
    assert brief["regime"]["label"] == "RISK_OFF"
    assert brief["overnight"][0]["headline"] == "Fed shock"
    assert brief["discovery_adds"][0]["symbol"] == "NEWCO"
    assert brief["earnings_soon"][0]["symbol"] == "GOODCO"
    assert brief["headline"] == "Deterministic headline."

    text = br.render_brief_text(brief)
    for token in ("Deterministic headline.", "OLDCO", "Consider exiting", "RISK_OFF", "NEWCO"):
        assert token in text


def test_build_brief_survives_missing_everything(tmp_path, monkeypatch):
    store = _mk_store(tmp_path, with_digest=False)
    monkeypatch.setattr(br, "_narrate_brief", lambda b: "h")
    # Settings-backed collectors: point at empty tmp subdirs so the
    # "missing file" branches genuinely run, hermetically (no real repo data).
    monkeypatch.setattr(br.settings, "PREDICTION_DATA_DIR", str(tmp_path / "predictions"))
    monkeypatch.setattr(br.settings, "DISCOVERY_DATA_DIR", str(tmp_path / "discovery"))
    # Collectors backed by hardcoded module-level cache paths (no settings
    # attribute to redirect) must be stubbed directly to avoid touching real
    # repo data (data/macro_news, data/market_cache/*).
    monkeypatch.setattr(br, "_overnight_items", lambda *a, **k: [])
    monkeypatch.setattr(br, "_earnings_soon", lambda *a, **k: [])
    monkeypatch.setattr(br, "_ipo_watch", lambda *a, **k: [])
    monkeypatch.setattr(br, "upcoming_lockin_alerts", lambda on, symbols=None: [])
    brief = br.build_morning_brief("u1", date(2026, 7, 9), store=store)
    assert brief["portfolio"] is None and brief["advisor_flags"] == []
    assert isinstance(br.render_brief_text(brief), str)


def test_run_skips_non_trading_day(monkeypatch):
    monkeypatch.setattr(br, "is_trading_day", lambda d: False)
    out = br.run_morning_brief(on=date(2026, 7, 12))
    assert out == {"status": "not_trading_day"}


def test_run_builds_saves_delivers(tmp_path, monkeypatch):
    monkeypatch.setattr(br, "is_trading_day", lambda d: True)
    monkeypatch.setattr(br, "active_user_ids", lambda: ["u1"])
    monkeypatch.setattr(br.settings, "PORTFOLIO_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(br.settings, "PREDICTION_DATA_DIR", str(tmp_path / "predictions"))
    monkeypatch.setattr(br.settings, "DISCOVERY_DATA_DIR", str(tmp_path / "discovery"))
    _mk_store(tmp_path)
    monkeypatch.setattr(br, "_narrate_brief", lambda b: "h")
    monkeypatch.setattr(br, "_overnight_items", lambda *a, **k: [])
    monkeypatch.setattr(br, "_earnings_soon", lambda *a, **k: [])
    monkeypatch.setattr(br, "_ipo_watch", lambda *a, **k: [])
    monkeypatch.setattr(br, "upcoming_lockin_alerts",
                        lambda on, symbols=None: [])
    with patch.object(br, "deliver", return_value={"delivered": True}) as m:
        out = br.run_morning_brief(on=date(2026, 7, 9))
    assert out["status"] == "completed" and out["users"] == 1
    assert m.call_count == 1
    saved = PortfolioStore(user_id="u1", base_dir=str(tmp_path)).load_latest_brief()
    assert saved and saved["date"] == "2026-07-09"


def test_overnight_items_read_cache_title_field(monkeypatch):
    # Cache entries carry "title" (macro_news_cache schema); the 2026-07-17
    # brief rendered three blank "Overnight:" lines because the collector
    # read a nonexistent "headline" key. Empty/missing titles are dropped.
    class _FakeCache:
        def get_high_severity(self, hours_back=24):
            return [
                {"title": "Fed shock", "severity": "HIGH"},
                {"title": "", "severity": "HIGH"},
                {"severity": "HIGH"},
                {"title": "RBI policy surprise", "severity": "HIGH"},
            ]

    import services.background.macro_news_cache as mnc
    monkeypatch.setattr(mnc, "MacroNewsCache", _FakeCache)
    items = br._overnight_items()
    assert items == [
        {"headline": "Fed shock", "severity": "HIGH"},
        {"headline": "RBI policy surprise", "severity": "HIGH"},
    ]


def test_run_brief_delivers_inbox_deeplink(tmp_path, monkeypatch):
    from core.config import settings
    captured = {}
    monkeypatch.setattr(br, "is_trading_day", lambda on: True)
    monkeypatch.setattr(br, "active_user_ids", lambda: ["u1"])
    monkeypatch.setattr(br, "build_morning_brief",
                        lambda uid, on, store=None: {"date": on.isoformat(),
                                                     "kind": "morning_brief",
                                                     "lockin_flags": []})
    monkeypatch.setattr(br, "render_brief_text", lambda b: "text")
    monkeypatch.setattr(br, "deliver",
                        lambda *a, **k: captured.update(k) or {"delivered": True})
    monkeypatch.setattr(settings, "PORTFOLIO_DATA_DIR", str(tmp_path))
    br.run_morning_brief(date(2026, 7, 22))
    assert captured["url"] == "/#/inbox/brief"


# --------------------------------------------------------------------------
# Redesign 2026-07-27: sectioned layout, plain-English, dedup, %-confidence
# --------------------------------------------------------------------------

def test_brief_settings_have_defaults():
    from core.config import settings
    assert settings.DELIVERY_BRIEF_MAX_OVERNIGHT == 3
    assert settings.DELIVERY_BRIEF_OVERNIGHT_DEDUP_THRESHOLD == 0.6
    assert settings.DELIVERY_BRIEF_OVERNIGHT_MAXLEN == 240
    assert settings.DELIVERY_BRIEF_MAX_IDEAS == 5
    assert settings.DELIVERY_BRIEF_IDEA_REASON_MAXLEN == 180
    assert settings.DELIVERY_BRIEF_MAX_IPOS == 3


def test_pct_formats_conviction():
    assert br._pct(0.654) == "65%"
    assert br._pct(0.62) == "62%"
    assert br._pct(None) == "" and br._pct("x") == ""


def test_first_sentence_ignores_decimals():
    thesis = "Acme has 65% EBITDA margin and INR 547.86cr revenue. The next line."
    assert br._first_sentence(thesis, 180) == "Acme has 65% EBITDA margin and INR 547.86cr revenue."


def test_first_sentence_caps_length():
    assert br._first_sentence("word " * 60, 40).endswith("…")
    assert br._first_sentence("", 40) == ""


def test_clean_headline_trims_overlong_at_word_boundary():
    out = br._clean_headline("a " * 200, 20)
    assert len(out) <= 21 and out.endswith("…") and not out.endswith(" …")


def test_regime_and_verdict_maps():
    assert br._REGIME_PLAIN["RISK_OFF"][0] == "Cautious"
    assert {"MACRO_CRISIS", "RISK_OFF", "MOMENTUM_EXTENDED", "RISK_ON",
            "OVERSOLD", "NORMAL"} <= set(br._REGIME_PLAIN)
    assert br._VERDICT_PLAIN["EXIT"] == "Consider exiting"


def test_overnight_prefers_summary_over_truncated_title(monkeypatch):
    class _Fake:
        def get_high_severity(self, hours_back=24):
            return [{"title": "Rupee rallies amid Middle East con",
                     "summary": "The rupee rallied after the RBI eased rules for foreign investors.",
                     "severity": "HIGH"}]
    import services.background.macro_news_cache as mnc
    monkeypatch.setattr(mnc, "MacroNewsCache", _Fake)
    items = br._overnight_items()
    assert items[0]["headline"] == "The rupee rallied after the RBI eased rules for foreign investors."


def test_overnight_dedups_same_story(monkeypatch):
    class _Fake:
        def get_high_severity(self, hours_back=24):
            return [
                {"summary": "RBI raised equity investment limits for NRIs and OCIs.", "severity": "HIGH"},
                {"summary": "RBI raised equity investment limits for NRIs and OCIs, boosting inflows.", "severity": "HIGH"},
                {"summary": "SEBI to launch corporate bond index derivatives.", "severity": "HIGH"},
            ]
    import services.background.macro_news_cache as mnc
    monkeypatch.setattr(mnc, "MacroNewsCache", _Fake)
    items = br._overnight_items()
    heads = [i["headline"] for i in items]
    assert len(heads) == 2
    assert "RBI raised equity investment limits for NRIs and OCIs, boosting inflows." in heads
    assert any("SEBI" in h for h in heads)


def test_ipo_dedups_by_symbol(monkeypatch):
    monkeypatch.setattr(br, "load_ipo_cache", lambda: {
        "current": [{"symbol": "LSR", "company": "Laser", "status": "current", "total_x": 8.2}],
        "upcoming": [{"symbol": "LSR", "company": "Laser", "status": "upcoming"},
                     {"symbol": "KUS", "company": "Kusum", "status": "upcoming"}]})
    rows = br._ipo_watch()
    assert [r["symbol"] for r in rows] == ["LSR", "KUS"]
    assert rows[0]["total_x"] == 8.2


def test_ipo_demand_string():
    assert br._ipo_demand({"total_x": 8.2, "qib_x": 12.0, "retail_x": 3.0}) == "8.2× overall (QIB 12×, retail 3×)"
    assert br._ipo_demand({}) == "demand data pending"


def test_enrich_discovery_adds_joins_shelf(monkeypatch):
    class _Idea:
        symbol, verdict, conviction = "NEWCO", "BUY", 0.62
        thesis = "Newco is a fast grower with 40% margins. More detail here."

    class _Shelf:
        def load(self):
            return type("S", (), {"ideas": [_Idea()]})()
    import core.discovery.shelf as sh
    monkeypatch.setattr(sh, "ShelfStore", _Shelf)
    out = br._enrich_discovery_adds([{"event": "added", "symbol": "NEWCO", "detail": ""},
                                     {"event": "added", "symbol": "GHOST", "detail": ""}])
    assert out[0]["verdict"] == "BUY" and out[0]["conviction"] == 0.62
    assert out[0]["reason"] == "Newco is a fast grower with 40% margins."
    assert "verdict" not in out[1]


def _full_brief():
    return {
        "date": "2026-07-27", "headline": "A cautious day.",
        "portfolio": {"portfolio_value": 620904.0, "total_pnl_pct": -5.9},
        "advisor_flags": [{"symbol": "OLDCO", "verdict": "EXIT", "reason": "stop breached"}],
        "regime": {"label": "RISK_OFF"},
        "overnight": [{"headline": "RBI eased foreign-investor rules.", "severity": "HIGH"}],
        "earnings_soon": [{"symbol": "SUZLON", "date": "2026-07-28"}],
        "discovery_adds": [{"symbol": "ACMESOLAR", "verdict": "BUY", "conviction": 0.65,
                            "reason": "One of the most efficient renewable operators."}],
        "ipo_watch": [{"symbol": "XTRANET", "company": "Xtranet", "status": "current",
                       "total_x": 8.2, "qib_x": 12.0, "retail_x": 3.0}],
        "lockin_flags": [],
    }


def test_render_full_brief_has_sections_and_glosses():
    t = br.render_brief_text(_full_brief())
    for h in ("MORNING BRIEF · 27 Jul 2026", "SUMMARY", "YOUR PORTFOLIO",
              "NEEDS ATTENTION", "MARKET CONDITIONS", "OVERNIGHT — HIGH-IMPACT NEWS",
              "EARNINGS THIS WEEK", "IDEAS THE TOOL IS RESEARCHING", "IPOs OPEN NOW"):
        assert h in t
    assert "Cautious (RISK_OFF)" in t
    assert "down 5.9% since inception" in t
    assert "OLDCO  Consider exiting — stop breached" in t
    assert "ACMESOLAR   BUY · 65%" in t
    assert "One of the most efficient renewable operators." in t
    assert "8.2× overall (QIB 12×, retail 3×)" in t
    assert "never personal advice" in t


def test_render_hides_empty_sections():
    b = _full_brief()
    b.update({"overnight": [], "earnings_soon": [], "discovery_adds": [],
              "ipo_watch": [], "advisor_flags": []})
    t = br.render_brief_text(b)
    for absent in ("OVERNIGHT", "EARNINGS THIS WEEK", "IDEAS THE TOOL", "IPOs OPEN NOW", "NEEDS ATTENTION"):
        assert absent not in t
    assert "YOUR PORTFOLIO" in t and "Nothing needs your attention today." in t


# ---- Enhancements 2026-07-28: earnings-why, IPO lean, overnight notes ------

def test_ipo_lean_classifies_by_demand():
    assert br._ipo_lean({"total_x": 24.0, "qib_x": 41.0})[0] == "STRONG DEMAND"
    assert br._ipo_lean({"qib_x": 18.0})[0] == "STRONG DEMAND"
    assert br._ipo_lean({"total_x": 1.5})[0] == "SOFT DEMAND"
    assert br._ipo_lean({"total_x": 5.0})[0] == "MODERATE DEMAND"
    lbl, reason = br._ipo_lean({})
    assert lbl == "data pending" and "not yet" in reason


def test_earnings_watch_returns_open_guidance(monkeypatch):
    class _G:
        def __init__(self, status, guidance):
            self.status, self.guidance = status, guidance

    class _Dossier:
        guidance = [_G("met", "old thing"),
                    _G("open", "FY27 capex guidance of INR 42,000 crore")]

    monkeypatch.setattr(br, "_resolve_sector", lambda t: "renewable_energy")
    monkeypatch.setattr(br, "_load_ticker_dossier", lambda t, s: _Dossier())
    assert br._earnings_watch("ACMESOLAR") == "FY27 capex guidance of INR 42,000 crore"


def test_earnings_watch_empty_when_no_dossier(monkeypatch):
    monkeypatch.setattr(br, "_resolve_sector", lambda t: "x")
    monkeypatch.setattr(br, "_load_ticker_dossier", lambda t, s: None)
    assert br._earnings_watch("FOO") == ""


def test_render_earnings_generic_and_watch():
    b = _full_brief()
    b["earnings_soon"] = [
        {"symbol": "SUZLON", "date": "2026-07-28"},
        {"symbol": "ACMESOLAR", "date": "2026-07-29", "watch": "FY27 capex guidance"},
    ]
    t = br.render_brief_text(b)
    assert "You hold this — results & guidance are the next catalyst." in t
    assert "You hold this — watch: FY27 capex guidance" in t


def test_render_ipo_shows_lean():
    b = _full_brief()
    b["ipo_watch"] = [{"symbol": "XTRANET", "company": "Xtranet", "status": "current",
                       "total_x": 24.0, "qib_x": 41.0}]
    t = br.render_brief_text(b)
    assert "the tool's research view — not advice" in t
    assert "Lean: STRONG DEMAND" in t


def test_render_overnight_note():
    b = _full_brief()
    b["overnight"] = [{"headline": "SEBI tightens bond-derivative oversight",
                       "severity": "HIGH",
                       "note": "signals a firmer regulatory hand on debt markets."}]
    t = br.render_brief_text(b)
    assert "Why it matters: signals a firmer regulatory hand on debt markets." in t


def test_build_attaches_overnight_notes(tmp_path, monkeypatch):
    store = _mk_store(tmp_path)
    monkeypatch.setattr(br, "_narrate_brief", lambda b: ("Head.", ["note-A"]))
    monkeypatch.setattr(br, "_read_regime", lambda: {"label": "RISK_OFF"})
    monkeypatch.setattr(br, "_overnight_items", lambda: [{"headline": "X", "severity": "HIGH"}])
    monkeypatch.setattr(br, "_shelf_events_since", lambda since: [])
    monkeypatch.setattr(br, "_earnings_soon", lambda symbols, on: [])
    monkeypatch.setattr(br, "_ipo_watch", lambda: [])
    monkeypatch.setattr(br, "upcoming_lockin_alerts", lambda on, symbols=None: [])
    brief = br.build_morning_brief("u1", date(2026, 7, 9), store=store)
    assert brief["headline"] == "Head."
    assert brief["overnight"][0]["note"] == "note-A"


# -- Task 1: overnight de-dup — salient-entity clustering (redesign 2026-07-30) --

def test_dedup_overnight_merges_salient_entities():
    # The two NRI/OCI items are one story worded differently; the rupee item is separate.
    items = [
        {"headline": "RBI measures boost rupee amid Middle East conflict.", "severity": "HIGH"},
        {"headline": "Govt raises equity limits for NRIs, OCIs to boost foreign investment.", "severity": "HIGH"},
        {"headline": "RBI increases NRI/OCI investment limits without SEBI registration.", "severity": "HIGH"},
    ]
    stop = frozenset(br.settings.DELIVERY_BRIEF_OVERNIGHT_STOPWORDS)
    out = br._dedup_overnight(items, 0.6, 5, min_shared=2, stopwords=stop)
    heads = [o["headline"] for o in out]
    assert len(out) == 2                                   # 3 -> 2
    assert any("rupee" in h.lower() for h in heads)        # rupee survives
    assert sum("nri" in h.lower() or "oci" in h.lower() for h in heads) == 1  # one NRI row


def test_dedup_overnight_min_shared_zero_is_legacy():
    # min_shared=0 disables the entity path — unrelated items are NOT merged.
    items = [
        {"headline": "Govt raises equity limits for NRIs, OCIs.", "severity": "HIGH"},
        {"headline": "RBI increases NRI/OCI investment limits without SEBI.", "severity": "HIGH"},
    ]
    out = br._dedup_overnight(items, 0.6, 5)               # legacy call, no entity merge
    assert len(out) == 2


# -- Task 2: richer portfolio line — best/worst/count/last-exit (2026-07-30) --

def test_portfolio_extras_best_worst_and_last_exit():
    digest = {
        "holdings": [
            {"symbol": "SUZLON", "pnl_pct": -10.9},
            {"symbol": "PAYTM", "pnl_pct": -2.3},
            {"symbol": "TATAELXSI", "pnl_pct": -2.9},
        ],
        "trades": [
            {"symbol": "IDFCFIRSTB", "side": "SELL", "pnl_pct": 6.1},
        ],
    }
    x = br._portfolio_extras(digest)
    assert x["holdings_count"] == 3
    assert x["best"] == {"symbol": "PAYTM", "pnl_pct": -2.3}
    assert x["worst"] == {"symbol": "SUZLON", "pnl_pct": -10.9}
    assert x["all_below_cost"] is True
    assert x["last_exit"] == {"symbol": "IDFCFIRSTB", "pnl_pct": 6.1}


def test_portfolio_extras_empty_digest_is_blank():
    assert br._portfolio_extras({}) == {}
    assert br._portfolio_extras({"holdings": []}) == {}


# -- Task 3: distinct why-it-matters notes (2026-07-30) --

def test_dedupe_notes_blanks_near_duplicate():
    notes = [
        "Higher NRI/OCI limits could boost equity inflows.",
        "Eased NRI/OCI limits boost equity inflows.",     # near-dup of #0
        "Rupee support curbs imported inflation.",
    ]
    out = br._dedupe_notes(notes)
    assert out[0] == notes[0]
    assert out[1] == ""                                    # duplicate blanked
    assert out[2] == notes[2]
    assert len(out) == len(notes)                          # order/length preserved


# -- Task 4: render_brief_html — clean-fintech email-safe renderer (2026-07-30) --

def test_render_brief_html_full_and_safe():
    brief = {
        "date": "2026-07-30",
        "headline": "Calm NORMAL market; policy-heavy overnight tape.",
        "portfolio": {"portfolio_value": 556826.57, "total_pnl_pct": -6.81,
                      "holdings_count": 8, "all_below_cost": True,
                      "best": {"symbol": "PAYTM", "pnl_pct": -2.3},
                      "worst": {"symbol": "SUZLON", "pnl_pct": -10.9},
                      "last_exit": {"symbol": "IDFCFIRSTB", "pnl_pct": 6.1}},
        "advisor_flags": [],
        "regime": {"label": "NORMAL"},
        "overnight": [{"headline": "RBI steadies the rupee.", "severity": "HIGH",
                       "note": "Curbs imported-inflation risk."}],
        "earnings_soon": [{"symbol": "WAAREEENER", "date": "2026-07-30", "watch": ""}],
        "discovery_adds": [],
        "ipo_watch": [{"symbol": "XTRANET", "company": "Xtranet Technologies",
                       "status": "current", "issue_price": 127.0,
                       "qib_x": None, "retail_x": None, "total_x": None}],
        "lockin_flags": [{"symbol": "KISSHT", "kind": "anchor_remaining", "expiry": "2026-08-06"}],
    }
    html = br.render_brief_html(brief)
    assert html.lstrip().lower().startswith("<!doctype html>")
    assert "<script" not in html.lower()                       # no scripts
    assert "http://" not in html and 'src="https://' not in html  # no external images
    assert 'style="' in html                                    # inline styles present
    for token in ("Morning Brief", "5,56,827", "PAYTM", "SUZLON", "IDFCFIRSTB",
                  "RBI steadies the rupee.", "Curbs imported-inflation risk.",
                  "WAAREEENER", "XTRANET", "KISSHT",
                  "never personal advice"):
        assert token in html


def test_render_brief_html_never_raises_on_empty():
    assert isinstance(br.render_brief_html({}), str)
    assert isinstance(br.render_brief_html({"date": "2026-07-30", "portfolio": None}), str)


# -- Task 6: run_morning_brief renders HTML when enabled; kill-switch => None --

def test_run_brief_renders_html_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setattr(br, "is_trading_day", lambda d: True)
    monkeypatch.setattr(br, "active_user_ids", lambda: ["u1"])
    monkeypatch.setattr(br.settings, "PORTFOLIO_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(br.settings, "PREDICTION_DATA_DIR", str(tmp_path / "predictions"))
    monkeypatch.setattr(br.settings, "DISCOVERY_DATA_DIR", str(tmp_path / "discovery"))
    monkeypatch.setattr(br.settings, "DELIVERY_BRIEF_HTML_ENABLED", True)
    _mk_store(tmp_path)
    monkeypatch.setattr(br, "_narrate_brief", lambda b: ("h", []))
    monkeypatch.setattr(br, "_overnight_items", lambda *a, **k: [])
    monkeypatch.setattr(br, "_earnings_soon", lambda *a, **k: [])
    monkeypatch.setattr(br, "_ipo_watch", lambda *a, **k: [])
    monkeypatch.setattr(br, "upcoming_lockin_alerts", lambda on, symbols=None: [])
    captured = {}
    monkeypatch.setattr(br, "deliver", lambda title, body, **k: captured.update(k) or {"delivered": True})
    br.run_morning_brief(on=date(2026, 7, 9))
    assert captured.get("html_body", "").lstrip().lower().startswith("<!doctype html>")

    captured.clear()
    monkeypatch.setattr(br.settings, "DELIVERY_BRIEF_HTML_ENABLED", False)
    br.run_morning_brief(on=date(2026, 7, 9))
    assert captured.get("html_body") is None            # kill-switch => text only
