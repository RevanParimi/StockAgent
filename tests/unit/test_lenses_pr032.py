"""PR-032: industry lenses on the general path.

The card's acceptance, one class each:

- the lookup: a listed label gives its lens, an unlisted one the default lens,
  none today's wording; a malformed file or a label in two lenses does not load;
- with `lenses.enabled` off every query on every path is today's, byte for byte,
  and with it on the four sector paths' are too (golden strings, typed from the
  code before PR-032, not computed by it);
- with it on, a general-path stock's queries never name the graph and carry the
  lens's own words, for every label of every committed lens (the oracle reads
  the YAML files directly, not through the module);
- one peer choice per bundle: no extra profile lookup;
- the industry block is not a section, so nothing counts it and nothing needs it.

Every network producer is a stub; no test reaches Serper, Tavily or Yahoo.
"""
from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from core.schemas.pipeline import StockQuery
from services.data.context import bundle_builder as bb
from services.data.context import lenses as L
from services.data.context.fetch_result import STATUS_OK, FetchResult
from services.data.context.peers import PeerChoice

REPO = Path(__file__).resolve().parents[2]
LENS_DIR = REPO / "config" / "lenses"
DAY = date(2026, 11, 27)
NATIVE = ("automobile", "banking_bfsi", "it_sector", "renewable_energy")


class _Day(date):
    @classmethod
    def today(cls):
        return DAY


# Today's queries for "Acme Ltd" (ACME) on 27 Nov 2026, typed from the code as
# it stood before PR-032 (services/data/context/bundle_builder.py at eb5da62):
# company news, sector news, macro news, page extract.
GOLDEN = {
    "generic": (
        "Acme Ltd ACME latest news results guidance outlook November 2026",
        "India stock market November 2026 sector news policy demand",
        "India generic sector macro economy INR USD crude oil RBI November 2026",
        "Acme Ltd NSE ACME results outlook policy regulation 2026",
    ),
    "automobile": (
        "Acme Ltd ACME latest news results guidance November 2026",
        "India automobile sector demand policy regulation competitors news November 2026",
        "India automobile sector macro economy INR USD crude oil RBI November 2026",
        "India Acme Ltd sector policy regulation circular FAME PLI 2026",
    ),
    "banking_bfsi": (
        "Acme Ltd ACME latest news quarterly results NPA NIM deposits November 2026",
        "India banking sector RBI policy credit growth banking regulation news November 2026",
        "India banking_bfsi sector macro economy INR USD crude oil RBI November 2026",
        "Acme Ltd RBI policy regulation impact banking 2026",
    ),
    "it_sector": (
        "Acme Ltd ACME latest news results deal wins attrition guidance November 2026",
        "US tech spending H1B visa AI services disruption India IT sector news November 2026",
        "India it_sector sector macro economy INR USD crude oil RBI November 2026",
        "Acme Ltd earnings call transcript guidance commentary 2026",
    ),
    "renewable_energy": (
        "Acme Ltd ACME latest news results PPA commissioning capacity November 2026",
        "India MNRE solar wind auctions module prices DISCOM renewable energy news November 2026",
        "India renewable_energy sector macro economy INR USD crude oil RBI November 2026",
        "India MNRE renewable auction policy Acme Ltd 2026",
    ),
}
DEFAULT_MACRO = "India economy inflation RBI rupee crude oil news November 2026"


def _raw_lenses() -> dict[str, dict]:
    """The committed files as YAML says, not as the module reads them."""
    return {p.stem: yaml.safe_load(p.read_text(encoding="utf-8"))
            for p in sorted(LENS_DIR.glob("*.yaml"))}


def _query() -> StockQuery:
    return StockQuery(ticker="ACME", company_name="Acme Ltd", nse_data={})


@pytest.fixture()
def wire(monkeypatch):
    """Every producer stubbed; the four searches' queries and the peer
    choices recorded. `industry` is the Yahoo label the peer choice returns."""
    calls = {"news": [], "tavily": [], "peers": []}
    state = SimpleNamespace(calls=calls, industry="")

    def news(queries, max_queries=3, api_key=None, tbs=None, searches=None):
        calls["news"].append(list(queries)[:max_queries])
        if searches is not None:
            searches.append({"query": queries[0], "source": "serper", "results": []})
        return FetchResult("news text", STATUS_OK, "serper")

    def tavily(queries, max_queries=2, max_results_per_query=2):
        calls["tavily"].append(list(queries)[:max_queries])
        return FetchResult("page text", STATUS_OK, "tavily")

    def choose(ticker, *, sector="", **kw):
        calls["peers"].append((ticker, sector))
        return PeerChoice(ticker, (), state.industry, "fixture: no peers")

    monkeypatch.setattr("services.data.fetchers.news.fetch_news_result", news)
    monkeypatch.setattr("services.clients.tavily_fetcher.fetch_tavily_result", tavily)
    monkeypatch.setattr("services.data.fetchers.macro.get_macro_result",
                        lambda: FetchResult("macro text", STATUS_OK, "yfinance"))
    monkeypatch.setattr("services.data.context.peers.choose_peers", choose)
    monkeypatch.setattr("core.intelligence.algorithms.indicators.fetcher.get_valuation_result",
                        lambda t, **k: FetchResult("valuation text", STATUS_OK, "yfinance"))
    monkeypatch.setattr("services.data.fetchers.nse_announcements.format_nse_context",
                        lambda *a, **k: "")
    for name in ("_fetch_fundamentals", "_fetch_technicals", "_fetch_commodities",
                 "_fetch_flows_sentiment", "_fetch_dossier"):
        monkeypatch.setattr(bb, name, lambda *a, **k: FetchResult("x", STATUS_OK, "fixture"))
    monkeypatch.setattr(bb, "date", _Day)
    return state


def _setting(monkeypatch, on: bool) -> None:
    monkeypatch.setattr(L, "lenses_enabled", lambda: on)


def _build(wire, sector: str, industry: str = ""):
    wire.industry = industry
    for v in wire.calls.values():
        v.clear()
    bundle = bb.build_sector_bundle(_query(), sector)
    news = [q[0] for q in wire.calls["news"]]
    assert len(news) == 3 and len(wire.calls["tavily"]) == 1     # the same four calls
    return bundle, (news[0], news[1], news[2], wire.calls["tavily"][0][0])


# ---------------------------------------------------------------------------
# The lookup
# ---------------------------------------------------------------------------

class TestLookup:
    def test_a_listed_label_gives_its_lens(self):
        found = L.load_lenses(LENS_DIR)
        choice = found.lens_for("Building Materials")
        assert (choice.kind, choice.record, choice.industry) == ("lens", "cement",
                                                                 "Building Materials")

    def test_labels_match_without_case_or_edge_spaces(self):
        found = L.load_lenses(LENS_DIR)
        assert found.lens_for("  building materials ").record == "cement"

    def test_an_unlisted_label_gives_the_default_lens(self):
        choice = L.load_lenses(LENS_DIR).lens_for("Conglomerates")
        assert (choice.kind, choice.record, choice.lens) == ("default", "default", None)
        assert choice.sector_query(DAY) == (
            "India Conglomerates industry demand prices policy news November 2026")

    @pytest.mark.parametrize("label", ["", "   ", None])
    def test_no_label_keeps_todays_wording(self, label):
        choice = L.load_lenses(LENS_DIR).lens_for(label)
        assert choice.kind == "none" and choice.record == "none"
        assert choice.sector_query(DAY) is None
        assert choice.company_news_terms() is None
        assert choice.policy_query("Acme Ltd", "ACME", DAY) is None
        assert choice.macro_query(DAY) == DEFAULT_MACRO
        assert choice.block() == ""


# ---------------------------------------------------------------------------
# The committed files
# ---------------------------------------------------------------------------

class TestCommittedFiles:
    def test_they_load_and_cover_at_least_twelve_industry_groups(self):
        found = L.load_lenses(LENS_DIR)
        assert len(found.lenses) >= 12
        assert [x.id for x in found.lenses] == sorted(_raw_lenses())

    def test_no_label_is_one_a_sector_path_takes(self):
        """A label the deep dive routes to a native graph would never reach a
        lens; FIX-026's routing table is the oracle."""
        from core.discovery.sector_naming import _GRAPH_GUESS_INDUSTRIES
        native = {x for labels in _GRAPH_GUESS_INDUSTRIES.values() for x in labels}
        assert not native & set(L.load_lenses(LENS_DIR).covered_labels())

    def test_every_block_fits_and_names_the_lens(self):
        found = L.load_lenses(LENS_DIR)
        for label in found.covered_labels():
            choice = found.lens_for(label)
            block = choice.block()
            assert len(block) <= L.BLOCK_MAX_CHARS
            assert block.startswith(f"Industry: {choice.lens.display} (Yahoo: {label}).")
            assert block.endswith("A number the bundle does not contain stays unknown.")

    def test_the_folder_readme_is_not_read_as_a_lens(self):
        assert (LENS_DIR / "README.md").exists()
        assert "README" not in {x.id for x in L.load_lenses(LENS_DIR).lenses}


# ---------------------------------------------------------------------------
# Malformed files do not load
# ---------------------------------------------------------------------------

GOOD = {
    "id": "cement", "display": "Cement", "industries": ["Building Materials"],
    "kpis": ["realisation per tonne"], "news_terms": "results volumes",
    "sector_query": "India cement prices news {month} {year}",
    "policy_query": "{company_name} {ticker} cement volumes {year}",
    "macro_drivers": ["coal prices"],
}


def _write(folder: Path, name: str, data) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    text = data if isinstance(data, str) else yaml.safe_dump(data)
    (folder / f"{name}.yaml").write_text(text, encoding="utf-8")


class TestChecks:
    def test_a_good_file_loads(self, tmp_path):
        _write(tmp_path, "cement", GOOD)
        assert L.load_lenses(tmp_path).lens_for("Building Materials").record == "cement"

    @pytest.mark.parametrize("change,why", [
        ({"kpis": None}, "kpis"),
        ({"sector_query": "India cement {company_name} news {month} {year}"}, "{company_name}"),
        ({"sector_query": "India cement news {month!r} {year}"}, "{month}"),
        ({"sector_query": "India cement news {month:>5} {year}"}, "{month}"),
        ({"policy_query": "{company_name} cement {month} {year}"}, "{month}"),
        ({"news_terms": "results {year}"}, "{year}"),
        ({"sector_query": "India cement news {month {year}"}, "not a valid template"),
        ({"id": "Cement"}, "id must be"),
        ({"id": "cement_two"}, "differs from the file name"),
        ({"sector_query": "India generic cement news {month} {year}"}, "generic"),
        ({"news_terms": "results Generic"}, "generic"),
        ({"industries": []}, "industries"),
        ({"industries": "Building Materials"}, "industries"),
        ({"kpis": [f"k{i}" for i in range(9)]}, "at most 8"),
        ({"macro_drivers": ["a", "b", "c", "d", "e"]}, "at most 4"),
        ({"display": ""}, "display"),
    ])
    def test_a_bad_field_does_not_load(self, tmp_path, change, why):
        data = {**GOOD, **change}
        if change.get("kpis", "") is None:
            del data["kpis"]
        _write(tmp_path, "cement", data)
        with pytest.raises(L.LensError) as err:
            L.load_lenses(tmp_path)
        assert why in str(err.value)

    def test_a_label_in_two_lenses_does_not_load(self, tmp_path):
        _write(tmp_path, "cement", GOOD)
        _write(tmp_path, "tiles", {**GOOD, "id": "tiles",
                                   "industries": ["building materials", "Tiles"]})
        with pytest.raises(L.LensError, match="is in two lenses: cement and tiles"):
            L.load_lenses(tmp_path)

    @pytest.mark.parametrize("text", ["- just\n- a list\n", "id: [unclosed\n", ""])
    def test_a_file_that_is_not_a_mapping_does_not_load(self, tmp_path, text):
        _write(tmp_path, "cement", text)
        with pytest.raises(L.LensError):
            L.load_lenses(tmp_path)

    def test_an_empty_or_missing_folder_does_not_load(self, tmp_path):
        with pytest.raises(L.LensError, match="no lens files"):
            L.load_lenses(tmp_path)
        with pytest.raises(L.LensError, match="no lens directory"):
            L.load_lenses(tmp_path / "missing")


class TestStartup:
    def test_a_broken_set_is_an_error_line_and_today_s_wording(self, tmp_path, monkeypatch,
                                                                caplog, wire):
        _write(tmp_path, "cement", GOOD)
        _write(tmp_path, "tiles", {**GOOD, "id": "tiles"})
        monkeypatch.setenv("LENS_DIR", str(tmp_path))
        _setting(monkeypatch, True)
        from services.api import server
        with caplog.at_level(logging.INFO):
            server._log_lens_check()                     # never raises
        assert any(r.levelno == logging.ERROR and "lens files NOT loaded" in r.getMessage()
                   and "is in two lenses" in r.getMessage() for r in caplog.records)
        assert L.active_lenses() is None
        bundle, queries = _build(wire, "generic", "Building Materials")
        assert queries == GOLDEN["generic"]
        assert bundle.industry_block == "" and bundle.lens == ""

    def test_the_committed_set_is_an_info_line(self, monkeypatch, caplog):
        monkeypatch.setenv("LENS_DIR", str(LENS_DIR))
        from services.api import server
        with caplog.at_level(logging.INFO):
            server._log_lens_check()
        line = next(r for r in caplog.records if "industry lenses" in r.getMessage())
        assert line.levelno == logging.INFO
        assert re.search(r"lenses\.enabled off; \d+ lenses covering \d+ Yahoo industries",
                         line.getMessage())

    def test_a_fixed_file_is_read_again(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LENS_DIR", str(tmp_path))
        _write(tmp_path, "cement", {**GOOD, "kpis": []})
        assert L.checked_lenses()[0] is None
        import os
        _write(tmp_path, "cement", GOOD)
        later = (tmp_path / "cement.yaml").stat().st_mtime + 5
        os.utime(tmp_path / "cement.yaml", (later, later))
        assert L.checked_lenses()[0] is not None

    def test_the_setting_ships_off(self):
        config = yaml.safe_load((REPO / "config.yaml").read_text(encoding="utf-8"))
        assert config["lenses"]["enabled"] is False


# ---------------------------------------------------------------------------
# Off, and the sector paths: byte for byte today's
# ---------------------------------------------------------------------------

class TestTodaysWording:
    @pytest.mark.parametrize("sector", list(GOLDEN))
    @pytest.mark.parametrize("label", ["", "Building Materials", "Conglomerates"])
    def test_off_every_query_on_every_path_is_today_s(self, wire, monkeypatch, sector, label):
        _setting(monkeypatch, False)
        bundle, queries = _build(wire, sector, label)
        assert queries == GOLDEN[sector]
        assert bundle.industry_block == "" and bundle.lens == ""
        assert all("lens" not in (bundle.section_provenance.get(n) or {})
                   for n in bb.SECTION_ORDER)

    @pytest.mark.parametrize("sector", NATIVE)
    @pytest.mark.parametrize("label", ["", "Building Materials", "Conglomerates"])
    def test_on_the_four_sector_paths_are_today_s(self, wire, monkeypatch, sector, label):
        _setting(monkeypatch, True)
        bundle, queries = _build(wire, sector, label)
        assert queries == GOLDEN[sector]
        assert bundle.industry_block == "" and bundle.lens == ""
        assert "## INDUSTRY" not in bundle.to_prompt_text()

    def test_off_the_bundle_text_is_unchanged(self, wire, monkeypatch):
        _setting(monkeypatch, False)
        bundle, _ = _build(wire, "generic", "Building Materials")
        assert bundle.to_prompt_text().startswith("## COMPANY_NEWS\nnews text")


# ---------------------------------------------------------------------------
# On, the general path: the lens's words, never the graph's name
# ---------------------------------------------------------------------------

def _every_label():
    return [(stem, label) for stem, raw in _raw_lenses().items() for label in raw["industries"]]


class TestLensWording:
    @pytest.mark.parametrize("stem,label", _every_label())
    def test_each_label_gets_its_lens_s_queries(self, wire, monkeypatch, stem, label):
        _setting(monkeypatch, True)
        raw = _raw_lenses()[stem]
        bundle, (company, sector, macro, page) = _build(wire, "generic", label)
        assert company == f"Acme Ltd ACME latest news {raw['news_terms']} November 2026"
        assert sector == raw["sector_query"].format(month="November", year=2026)
        assert macro == ("India " + " ".join(raw["macro_drivers"])
                         + " economy news November 2026")
        assert page == raw["policy_query"].format(company_name="Acme Ltd", ticker="ACME",
                                                  year=2026)
        for q in (company, sector, macro, page):
            assert not re.search(r"\bgeneric\b", q, re.IGNORECASE), q
        assert all(bundle.section_provenance[n]["lens"] == stem for n in bb.LENS_SECTIONS)
        assert bundle.lens == stem
        assert all(k in bundle.industry_block for k in raw["kpis"])
        assert f"Industry: {raw['display']} (Yahoo: {label})." in bundle.industry_block

    def test_an_unlisted_label_gets_the_default_lens(self, wire, monkeypatch):
        _setting(monkeypatch, True)
        bundle, (company, sector, macro, page) = _build(wire, "generic", "Conglomerates")
        assert company == GOLDEN["generic"][0] and page == GOLDEN["generic"][3]
        assert sector == "India Conglomerates industry demand prices policy news November 2026"
        assert macro == DEFAULT_MACRO
        assert all(bundle.section_provenance[n]["lens"] == "default" for n in bb.LENS_SECTIONS)
        assert bundle.industry_block.startswith("Industry: Conglomerates (Yahoo's label;")

    def test_no_label_keeps_today_s_but_not_the_graph_s_name(self, wire, monkeypatch):
        _setting(monkeypatch, True)
        bundle, queries = _build(wire, "generic", "")
        assert queries == (GOLDEN["generic"][0], GOLDEN["generic"][1], DEFAULT_MACRO,
                           GOLDEN["generic"][3])
        assert all(bundle.section_provenance[n]["lens"] == "none" for n in bb.LENS_SECTIONS)
        assert bundle.industry_block == "" and bundle.lens == "none"

    def test_only_the_four_search_sections_record_the_lens(self, wire, monkeypatch):
        _setting(monkeypatch, True)
        bundle, _ = _build(wire, "generic", "Steel")
        for name in bb.SECTION_ORDER:
            has = "lens" in (bundle.section_provenance.get(name) or {})
            assert has == (name in bb.LENS_SECTIONS), name

    def test_a_failed_search_still_records_its_lens(self, wire, monkeypatch):
        _setting(monkeypatch, True)
        def boom(*a, **k):
            raise RuntimeError("serper down")
        monkeypatch.setattr("services.data.fetchers.news.fetch_news_result", boom)
        wire.industry = "Steel"
        bundle = bb.build_sector_bundle(_query(), "generic")
        assert bundle.section_status["company_news"] == "failed:RuntimeError"
        assert bundle.section_provenance["company_news"]["lens"] == "steel"
        assert bundle.section_provenance["company_news"]["reason"].startswith("raised")

    def test_a_failing_lens_lookup_keeps_today_s_wording(self, wire, monkeypatch):
        _setting(monkeypatch, True)
        def broken():
            raise OSError("disk")
        monkeypatch.setattr(L, "active_lenses", broken)
        bundle, queries = _build(wire, "generic", "Steel")
        assert queries == GOLDEN["generic"] and bundle.lens == ""


# ---------------------------------------------------------------------------
# No extra lookup
# ---------------------------------------------------------------------------

class TestOneLookup:
    @pytest.mark.parametrize("on", [False, True])
    @pytest.mark.parametrize("sector", list(GOLDEN))
    def test_one_peer_choice_per_bundle(self, wire, monkeypatch, on, sector):
        _setting(monkeypatch, on)
        _build(wire, sector, "Steel")
        assert wire.calls["peers"] == [("ACME", sector)]

    def test_the_peers_section_uses_the_shared_choice(self, wire, monkeypatch):
        _setting(monkeypatch, True)
        bundle, _ = _build(wire, "generic", "Steel")
        assert bundle.section_provenance["peers_valuation"]["peers"] == (
            "peers unavailable: fixture: no peers")

    def test_profile_lookups_are_the_same_on_and_off(self, monkeypatch, tmp_path):
        """The real peer choice, with Yahoo replaced by a counting stub: the
        lens adds no profile lookup and reads the label the peers step read."""
        from services.data.context import peers as P
        table = {"SUNPHARMA.NS": "Drug Manufacturers - Specialty & Generic",
                 "CIPLA.NS": "Drug Manufacturers - Specialty & Generic",
                 "LUPIN.NS": "Drug Manufacturers - Specialty & Generic",
                 "DRREDDY.NS": "Drug Manufacturers - Specialty & Generic",
                 "TATASTEEL.NS": "Steel"}
        asked: list[str] = []

        def lookup(symbol):
            asked.append(symbol)
            return {"industry": table.get(symbol, ""), "sector": "Healthcare",
                    "market_cap": 1e12}

        monkeypatch.setattr(P, "known_symbols", lambda: [s[:-3] for s in table])
        monkeypatch.setattr(P, "lookup_profile", lookup)
        monkeypatch.setattr(P, "max_lookups", lambda: 1000)
        monkeypatch.setattr("services.data.fetchers.news.fetch_news_result",
                            lambda *a, **k: FetchResult("n", STATUS_OK, "serper"))
        monkeypatch.setattr("services.clients.tavily_fetcher.fetch_tavily_result",
                            lambda *a, **k: FetchResult("p", STATUS_OK, "tavily"))
        monkeypatch.setattr("services.data.fetchers.macro.get_macro_result",
                            lambda: FetchResult("m", STATUS_OK, "yfinance"))
        monkeypatch.setattr(
            "core.intelligence.algorithms.indicators.fetcher.get_valuation_result",
            lambda t, **k: FetchResult("v", STATUS_OK, "yfinance"))
        for name in ("_fetch_fundamentals", "_fetch_technicals", "_fetch_commodities",
                     "_fetch_flows_sentiment", "_fetch_dossier"):
            monkeypatch.setattr(bb, name, lambda *a, **k: FetchResult("x", STATUS_OK, "f"))
        query = StockQuery(ticker="SUNPHARMA", company_name="Sun Pharma", nse_data={})
        counts = {}
        for on in (False, True):
            monkeypatch.setattr(P, "PROFILE_PATH", tmp_path / f"profiles_{on}.json")
            _setting(monkeypatch, on)
            asked.clear()
            bundle = bb.build_sector_bundle(query, "generic")
            counts[on] = sorted(asked)
            if on:
                assert bundle.lens == "pharma"
        assert counts[True] == counts[False] and len(counts[True]) == len(table)


# ---------------------------------------------------------------------------
# The block is not a section
# ---------------------------------------------------------------------------

class TestBlockIsNotASection:
    def test_it_sits_above_the_sections_which_keep_every_character(self, wire, monkeypatch):
        _setting(monkeypatch, False)
        off, _ = _build(wire, "generic", "Steel")
        _setting(monkeypatch, True)
        on, _ = _build(wire, "generic", "Steel")
        assert on.sections == off.sections               # the stubs return the same text
        assert on.to_prompt_text() == f"## INDUSTRY\n{on.industry_block}\n\n{off.to_prompt_text()}"

    def test_the_cap_cuts_the_sections_not_the_block(self, wire, monkeypatch):
        from core.config import settings
        monkeypatch.setattr(settings, "UNIFIED_BUNDLE_MAX_CHARS", 50)
        _setting(monkeypatch, True)
        on, _ = _build(wire, "generic", "Steel")
        text = on.to_prompt_text()
        assert text.startswith(f"## INDUSTRY\n{on.industry_block}\n\n")
        assert len(text) == len(on.industry_block) + len("## INDUSTRY\n\n\n") + 50

    def test_no_status_no_health_count_never_essential(self, wire, monkeypatch):
        from services.data.stores.data_health import build_record, essential_sections
        rows = {}
        for on in (False, True):
            _setting(monkeypatch, on)
            bundle, _ = _build(wire, "generic", "Steel")
            assert set(bundle.section_status) == set(bb.SECTION_ORDER)
            rows[on] = build_record(run_id="r", ticker="ACME", sector="generic",
                                    section_status=bundle.section_status, api_calls={},
                                    dimensions_expected=["a"], dimensions_missing=[],
                                    section_provenance=bundle.section_provenance)
        assert not any("industry" in n.lower() for n in essential_sections())
        for key in ("sections", "health", "health_reasons", "essential_unusable", "live",
                    "empty", "degraded", "unverified", "not_applicable"):
            assert rows[True][key] == rows[False][key], key
        assert rows[True]["section_provenance"]["company_news"]["lens"] == "steel"

    def test_has_real_data_does_not_count_it(self, wire, monkeypatch):
        _setting(monkeypatch, True)
        for name in ("_fetch_fundamentals", "_fetch_technicals", "_fetch_commodities",
                     "_fetch_flows_sentiment", "_fetch_dossier"):
            monkeypatch.setattr(bb, name, lambda *a, **k: FetchResult("", "empty", "f"))
        monkeypatch.setattr("services.data.fetchers.news.fetch_news_result",
                            lambda *a, **k: FetchResult("", "empty", "serper"))
        monkeypatch.setattr("services.clients.tavily_fetcher.fetch_tavily_result",
                            lambda *a, **k: FetchResult("", "empty", "tavily"))
        monkeypatch.setattr("services.data.fetchers.macro.get_macro_result",
                            lambda: FetchResult("", "empty", "yfinance"))
        wire.industry = "Steel"
        bundle = bb.build_sector_bundle(_query(), "generic")
        assert bundle.industry_block                     # told the industry
        assert bundle.has_real_data is False             # one live section is not three


# ---------------------------------------------------------------------------
# Coverage: the weekly line
# ---------------------------------------------------------------------------

def _dive(symbol, graph, industry):
    return SimpleNamespace(symbol=symbol, graph=graph, industry=industry)


class TestCoverage:
    def test_counts_general_path_dives_by_lens_default_and_none(self, monkeypatch):
        _setting(monkeypatch, False)
        found = L.load_lenses(LENS_DIR)
        dives = [_dive("A", "generic", "Steel"), _dive("B", "generic", "Conglomerates"),
                 _dive("C", "generic", "Conglomerates"), _dive("D", "generic", ""),
                 _dive("E", "native", "Auto Parts"), _dive("F", "generic", "Uranium"),
                 _dive("G", "generic", "Waste Management")]
        out = L.coverage(dives, found)
        assert (out["dives"], out["lens"], out["default"], out["none"]) == (6, 2, 3, 1)
        assert out["lacking"] == {"Conglomerates": 2, "Waste Management": 1}
        assert L.coverage_line(out) == (
            "general-path dives 6: lens 2, default 3, no label 1; no lens yet: "
            "Conglomerates (2), Waste Management (1); lenses.enabled off")

    def test_a_broken_set_says_so(self):
        assert L.coverage_line({"loaded": False}) == "lens files not loaded"
        assert L.coverage_line(None) == "lens files not loaded"

    def test_the_scheduler_logs_the_line(self, monkeypatch, caplog):
        import core.discovery as disc
        import services.scheduler.python.scheduler as sched
        lenses = {"dives": 2, "lens": 1, "default": 1, "none": 0,
                  "lacking": {"Conglomerates": 1}, "enabled": False, "loaded": True}
        monkeypatch.setattr(disc, "run_discovery_cycle", lambda: {"sectors": {},
                                                                  "lenses": lenses})
        monkeypatch.setattr("core.delivery.ops_alerts.alert_job_zero_output",
                            lambda *a, **k: None)
        with caplog.at_level(logging.INFO):
            sched.AutomobileScheduler.__new__(sched.AutomobileScheduler)._discovery_weekly_job()
        assert ("Discovery lenses: general-path dives 2: lens 1, default 1, no label 0; "
                "no lens yet: Conglomerates (1); lenses.enabled off") in caplog.text
        assert "Discovery FAILED" not in caplog.text

    def test_the_weekly_cycle_returns_it(self, tmp_path, monkeypatch):
        import core.discovery as disc
        import core.discovery.deep_dive as dd
        import tests.unit.test_idea_supply_pr004 as pr004
        from backend.shared.schemas.discovery import DiscoveryCandidate
        screen = [DiscoveryCandidate(symbol=s, close=100.0, composite=0.9 - k / 100)
                  for k, s in enumerate(["HOSPCO", "STEELCO", "SOFTCO"])]
        pr004._cycle_env(tmp_path, monkeypatch, screen=screen)
        labels = {"HOSPCO": ("Healthcare", "Medical Care Facilities"),
                  "STEELCO": ("Basic Materials", "Waste Management"),
                  "SOFTCO": ("Technology", "Software - Application")}
        classify = lambda s: {"sector": labels[s][0], "industry": labels[s][1]}  # noqa: E731
        monkeypatch.setattr(disc, "market_classification", classify, raising=False)
        monkeypatch.setattr(dd, "market_classification", classify)
        result = disc.run_discovery_cycle(on=date(2026, 7, 4))
        lenses = result["lenses"]
        assert (lenses["dives"], lenses["lens"], lenses["default"]) == (2, 1, 1)
        assert lenses["lacking"] == {"Waste Management": 1}
