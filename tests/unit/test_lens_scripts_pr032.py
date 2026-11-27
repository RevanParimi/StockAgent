"""PR-032's scripts: the bench (its counting, its predeclared rule and a dry run
on stubs), the coverage read and the lens drafter. Nothing here reaches the
network or a model; the bench's arithmetic is checked against hand-worked
examples, not against its own code."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from scripts.lenses import bench as B
from scripts.lenses import coverage_report as C
from scripts.lenses import draft_lens as D
from services.data.context import lenses as L
from services.data.context.fetch_result import STATUS_OK, FetchResult

REPO = Path(__file__).resolve().parents[2]
LENSES = L.load_lenses(REPO / "config" / "lenses")


def _r(title="", snippet="", link=""):
    return {"title": title, "snippet": snippet, "link": link}


# ---------------------------------------------------------------------------
# What the bench counts
# ---------------------------------------------------------------------------

class TestCounting:
    def test_lens_words_leave_out_what_every_business_story_says(self):
        words = B.lens_words(LENSES.lens_for("Building Materials"))
        assert {"realisation", "tonne", "fuel", "utilisation", "ebitda"} <= words
        assert not {"results", "volumes", "capacity", "growth", "sales", "per", "and"} & words

    def test_the_default_lens_s_words_are_the_label_s(self):
        assert B.lens_words(LENSES.lens_for("Conglomerates")) == {"conglomerates"}

    def test_no_label_has_no_words(self):
        assert B.lens_words(LENSES.lens_for("")) == frozenset()
        assert B.lens_words(None) == frozenset()

    def test_usable_needs_a_title_or_a_snippet(self):
        assert B.usable([_r("a"), _r(snippet="b"), _r(), _r("  ", "  ")]) == 2
        assert B.usable([]) == 0 and B.usable(None) == 0

    def test_on_industry_matches_whole_words_in_title_or_snippet(self):
        words = frozenset({"realisation", "clinker"})
        rows = [_r("Cement realisation up"), _r("x", "clinker exports rise"),
                _r("Realisations fell"), _r("market news")]
        assert B.on_industry(rows, words) == 2            # "realisations" is not "realisation"
        assert B.on_industry(rows, frozenset()) == 0

    def test_repeats_match_on_link_else_title(self):
        sector = [_r("A", link="u1"), _r("Same Title"), _r("C", link="u3")]
        macro = [_r("other", link="u1"), _r("same title"), _r("C", link="u9"), _r()]
        assert B.repeats(sector, macro) == 2

    def test_the_composite_is_the_aggregator_s(self):
        out = {"business": SimpleNamespace(overall_score=0.8, error=None),
               "valuation": SimpleNamespace(overall_score=0.4, error=None),
               "risk": SimpleNamespace(overall_score=0.5, error="parse")}
        weights = {"business": 0.5, "valuation": 0.25, "risk": 0.25}
        # (0.8*0.5 + 0.4*0.25) / (0.5 + 0.25): the errored one is left out.
        assert B.composite(out, weights) == pytest.approx(0.5 / 0.75)
        assert B.composite({"risk": out["risk"]}, weights) is None
        assert B.composite({}, weights) is None


class TestChoosing:
    def test_one_stock_each_taken_in_turn_from_each_industry(self):
        dives = [{"symbol": f"S{i}", "dive_date": f"2026-11-{10 + i:02d}", "graph": "generic",
                  "industry": ind} for i, ind in enumerate(["Steel", "Steel", "Steel",
                                                            "Lodging", "Lodging", "Copper"])]
        dives += [{"symbol": "N1", "dive_date": "2026-11-20", "graph": "native",
                   "industry": "Auto Parts"},
                  {"symbol": "U1", "dive_date": "2026-11-20", "graph": "generic", "industry": ""},
                  {"symbol": "S2", "dive_date": "2026-11-01", "graph": "generic",
                   "industry": "Steel"}]                       # an older dive of S2
        chosen = [d["symbol"] for d in B.choose_stocks(dives, n=5)]
        # Steel (3 dives, latest first: S2, S1, S0), Lodging (S4, S3), Copper (S5).
        assert chosen == ["S2", "S4", "S5", "S1", "S3"]

    def test_fewer_than_asked_when_the_dives_run_out(self):
        dives = [{"symbol": "A", "dive_date": "2026-11-01", "graph": "generic",
                  "industry": "Steel"}]
        assert [d["symbol"] for d in B.choose_stocks(dives, n=20)] == ["A"]


def _row(sym, *, a, b, c, a2=None, ua=5, ub=5, oa=1, ob=3, results=10, words=("x",)):
    def arm(comp, usable, on):
        return {"composite": comp, "verdict": "BUY" if comp >= 0.6 else "HOLD",
                "usable": {"company_news": usable, "sector_policy_news": usable,
                           "macro_context": usable, "policy_deep_dive": 1},
                "results": results, "on_industry": on, "repeats": 0}
    return {"symbol": sym, "words": list(words), "arms": {
        "A": arm(a, ua, oa), "A2": {"composite": a if a2 is None else a2, "verdict": ""},
        "B": arm(b, ub, ob), "C": arm(c, ub, ob)}}


class TestRule:
    def test_b_and_c_ready(self):
        rows = [_row(f"S{i}", a=0.5, b=0.52, c=0.53) for i in range(4)]
        s = B.summarise(rows)
        # On-industry: A 4 of 40, B 12 of 40 -> a rise of 20 points.
        assert s["on_industry_A"] == (0.1, 40) and s["on_industry_B"] == (0.3, 40)
        assert s["share_rise"] == pytest.approx(0.2)
        assert s["b_ready"] and s["c_goes"]
        assert s["mean_abs_C_B"] == (0.01, 4)
        assert s["outcome"].startswith("B and C ready")
        assert s["too_few"] is True

    def test_a_rise_under_twenty_points_is_no_benefit(self):
        rows = [_row(f"S{i}", a=0.5, b=0.5, c=0.5, ob=2) for i in range(4)]
        s = B.summarise(rows)
        assert s["share_rise"] == pytest.approx(0.1)
        assert not s["b_ready"] and not s["c_goes"]
        assert s["outcome"].startswith("no benefit shown: the setting stays off")

    def test_fewer_usable_results_in_any_search_blocks_b(self):
        rows = [_row(f"S{i}", a=0.5, b=0.5, c=0.5, ua=5, ub=4) for i in range(4)]
        s = B.summarise(rows)
        assert not s["b_ready"]
        assert s["fewer_usable"] == ["company_news", "sector_policy_news", "macro_context"]
        assert "fewer usable results" in s["outcome"]

    def test_a_block_that_moves_the_composite_waits(self):
        rows = [_row("S1", a=0.5, b=0.5, c=0.58), _row("S2", a=0.5, b=0.5, c=0.44)]
        s = B.summarise(rows)
        # |0.58-0.5| and |0.44-0.5|: a mean of 0.07, over 0.05.
        assert s["mean_abs_C_B"] == (0.07, 2)
        assert s["b_ready"] and not s["c_goes"]
        assert s["outcome"].startswith("B ready; the block waits for PR-017's grades")

    def test_exactly_the_limit_still_goes(self):
        rows = [_row("S1", a=0.5, b=0.5, c=0.55)]
        assert B.summarise(rows)["c_goes"] is True

    def test_noise_and_verdict_changes_are_reported(self):
        rows = [_row("S1", a=0.5, b=0.62, c=0.62, a2=0.53), _row("S2", a=0.5, b=0.5, c=0.5)]
        s = B.summarise(rows)
        assert s["mean_abs_A2_A"] == (0.015, 2)
        assert s["verdict_changes_B_A"] == (1, 2)

    def test_stocks_without_lens_words_are_left_out_of_the_share(self):
        rows = [_row("S1", a=0.5, b=0.5, c=0.5), _row("S2", a=0.5, b=0.5, c=0.5, words=())]
        s = B.summarise(rows)
        assert s["on_industry_stocks"] == 1 and s["on_industry_A"][1] == 10

    def test_nothing_completed(self):
        s = B.summarise([{"symbol": "X", "error": "boom"}])
        assert s == {"stocks": 0, "outcome": "no stock completed: nothing to judge"}
        assert "nothing to judge" in B.render(s, [])

    def test_the_render_names_every_figure_with_its_n(self):
        rows = [_row(f"S{i}", a=0.5, b=0.52, c=0.53) for i in range(3)]
        text = B.render(B.summarise(rows), rows)
        assert "too few to judge" in text and "RULE: B and C ready" in text
        assert "company_news | 5 (3) | 5 (3)" in text


# ---------------------------------------------------------------------------
# A dry run on stubs: four arms, captured searches, no store written
# ---------------------------------------------------------------------------

class _Analyst:
    """The analysis's model, stubbed: scores higher when told the industry."""
    seen: list = []

    def run(self, query, bundle, sector, run_id="", sector_question=None):
        type(self).seen.append((run_id, bool(bundle.industry_block), sector))
        bump = 0.1 if bundle.industry_block else 0.0
        return {"business": SimpleNamespace(overall_score=0.5 + bump, error=None),
                "risk": SimpleNamespace(overall_score=0.5, error=None)}


class _Orchestrator:
    _aggregator_weights = None

    def _resolve_ticker(self, symbol, exact=False):
        from core.schemas.pipeline import StockQuery
        assert exact is True
        return StockQuery(ticker=symbol, company_name="Acme Industries", nse_data={})

    def _resolve_weights_for(self, ticker):
        self._aggregator_weights = {"business": 0.5, "risk": 0.5}


@pytest.fixture()
def stubbed_world(monkeypatch):
    from services.data.context import bundle_builder as bb
    from services.data.context.peers import PeerChoice

    def serper(query, n=5, api_key=None, tbs=None):
        if "steel" in query.lower() and "economy" not in query:
            return [{"title": "Steel realisation per tonne rises", "snippet": "coking coal",
                     "link": f"https://x/{query[:12]}", "date": ""}]
        return [{"title": "Markets end higher", "snippet": "Sensex", "link": "https://m/1",
                 "date": ""}]

    pages = []

    def tavily(query, max_results=3, search_depth="advanced"):
        pages.append(query)
        return [{"title": "t", "content": "plain intro " * 60 + "realisation tonne EBITDA",
                 "url": "u", "published_date": "", "score": 1.0}]

    monkeypatch.setattr("services.data.fetchers.news.search_serper", serper)
    monkeypatch.setattr("services.clients.tavily_fetcher.search_tavily", tavily)
    monkeypatch.setattr("services.data.fetchers.macro.get_macro_result",
                        lambda: FetchResult("macro", STATUS_OK, "yfinance"))
    monkeypatch.setattr("services.data.context.peers.choose_peers",
                        lambda t, **k: PeerChoice(t, (), "Steel",
                                                  '0 other known symbol(s) in Yahoo industry '
                                                  '"Steel", 3 needed'))
    monkeypatch.setattr("core.intelligence.algorithms.indicators.fetcher.get_valuation_result",
                        lambda t, **k: FetchResult("v", STATUS_OK, "yfinance"))
    for name in ("_fetch_fundamentals", "_fetch_technicals", "_fetch_commodities",
                 "_fetch_flows_sentiment", "_fetch_dossier"):
        monkeypatch.setattr(bb, name, lambda *a, **k: FetchResult("x", STATUS_OK, "f"))

    def no_write(*a, **k):
        raise AssertionError("the bench wrote a verdict-shadow row")
    monkeypatch.setattr("backend.shared.pipeline.verdict_shadow.log_verdict_shadow", no_write)
    _Analyst.seen = []
    return SimpleNamespace(pages=pages)


class TestDryRun:
    def test_one_stock_through_the_four_arms(self, stubbed_world, monkeypatch):
        monkeypatch.setattr(L, "lenses_enabled", lambda: False)   # production's setting
        row = B.bench_stock("ACME", orchestrator=_Orchestrator(), analyst_cls=_Analyst,
                            lens_set=LENSES)
        assert row["lens"] == "steel" and row["industry"] == "Steel"
        a, c = row["arms"]["A"], row["arms"]["C"]
        assert a["queries"]["sector_policy_news"] == (
            f"India stock market {date.today().strftime('%B')} {date.today().year} "
            "sector news policy demand")
        assert c["queries"]["sector_policy_news"].startswith("India steel prices demand")
        assert "generic" in a["queries"]["macro_context"]
        assert "generic" not in c["queries"]["macro_context"]
        # The lens's sector search found the steel story; today's searches did
        # not, and their sector and macro searches found the same story.
        assert (a["on_industry"], a["results"], a["repeats"]) == (0, 3, 1)
        assert (c["on_industry"], c["results"], c["repeats"]) == (1, 3, 0)
        assert a["usable"] == {"company_news": 1, "sector_policy_news": 1, "macro_context": 1,
                               "policy_deep_dive": 1}
        # B is C without the block: the stub scores the block 0.1 higher on one of two.
        assert row["arms"]["B"]["composite"] == 0.5 and row["arms"]["C"]["composite"] == 0.55
        assert row["arms"]["A2"]["composite"] == 0.5
        assert [s[1] for s in _Analyst.seen] == [False, False, False, True]
        assert {s[2] for s in _Analyst.seen} == {"generic"}
        assert row["extract"]["chars"] > 600
        assert row["extract"]["words_600"] == 0 and row["extract"]["words_2000"] >= 2
        assert L.lenses_enabled() is False                # the bench changed no setting

    def test_the_plan_calls_nothing_without_yes(self, monkeypatch, capsys):
        dives = [{"symbol": f"S{i}", "dive_date": "2026-11-20", "graph": "generic",
                  "industry": ind, "source": "dives.jsonl"}
                 for i, ind in enumerate(["Steel", "Copper", "Lodging"])]
        monkeypatch.setattr(C, "gather", lambda *a, **k: dives)

        def no_run(*a, **k):
            raise AssertionError("the plan ran an analysis")
        monkeypatch.setattr("core.intelligence.rl.workflows.sector_router.get_orchestrator",
                            no_run)
        assert B.main([]) == 0
        out = capsys.readouterr().out
        assert "3 stocks from 3 industries (the card asks for at least 8)" in out
        assert "S0 | Steel | lens steel" in out
        assert "plan only: nothing was called" in out

    def test_a_run_writes_its_rows_and_one_failure_costs_one_stock(self, stubbed_world,
                                                                    monkeypatch, tmp_path,
                                                                    capsys):
        monkeypatch.setattr("core.intelligence.rl.workflows.sector_router.get_orchestrator",
                            lambda key: _Orchestrator())
        monkeypatch.setattr("backend.shared.pipeline.unified_analyst.UnifiedAnalyst", _Analyst)
        real = B.bench_stock

        def flaky(symbol, **kw):
            if symbol == "BAD":
                raise RuntimeError("no listing")
            return real(symbol, **kw)
        monkeypatch.setattr(B, "bench_stock", flaky)
        out = tmp_path / "bench.json"
        assert B.main(["--yes", "--symbols", "ACME,BAD", "--out", str(out)]) == 0
        saved = json.loads(out.read_text(encoding="utf-8"))
        assert [r["symbol"] for r in saved["rows"]] == ["ACME", "BAD"]
        assert saved["rows"][1]["error"] == "RuntimeError: no listing"
        assert saved["summary"]["stocks"] == 1
        assert "RULE:" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# The coverage read
# ---------------------------------------------------------------------------

def _jsonl(path: Path, rows) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


class TestCoverageRead:
    @pytest.fixture()
    def base(self, tmp_path):
        _jsonl(tmp_path / "dives.jsonl", [
            {"row": "run", "dive_date": "2026-11-21"},
            {"row": "dive", "symbol": "STEELCO", "dive_date": "2026-11-21", "graph": "generic",
             "industry": "Steel"},
            {"row": "dive", "symbol": "AUTOCO", "dive_date": "2026-11-21", "graph": "native",
             "industry": "Auto Parts"},
            {"row": "dive", "symbol": "OLDCO", "dive_date": "2026-09-01", "graph": "generic",
             "industry": "Steel"},                                  # over 8 weeks old
            {"row": "dive", "symbol": "BLANKCO", "dive_date": "2026-11-14", "graph": "",
             "industry": ""},                                       # filled from the shelf
        ])
        _jsonl(tmp_path / "shelf_events.jsonl", [
            # 20:00 UTC on 6 Nov is 01:30 IST on 7 Nov.
            {"ts": "2026-11-06T20:00:00+00:00", "event": "added", "symbol": "HOTELCO"},
            {"ts": "2026-11-07T07:00:00+00:00", "event": "dropped", "symbol": "HOTELCO"},
            {"ts": "2026-11-14T07:00:00+00:00", "event": "redived", "symbol": "STEELCO"},
        ])
        (tmp_path / "dives.json").write_text(json.dumps({
            "MYSTERY": {"date": "2026-11-14"}, "STEELCO": {"date": "2026-11-21"}}))
        (tmp_path / "shelf.json").write_text(json.dumps({"ideas": [
            {"symbol": "HOTELCO", "graph": "generic", "industry": "Lodging"},
            {"symbol": "BLANKCO", "graph": "generic", "industry": ""},
            {"symbol": "STEELCO", "graph": "generic", "industry": "Steel"}]}))
        profiles = tmp_path / "peer_profiles.json"
        profiles.write_text(json.dumps({"profiles": {
            "BLANKCO.NS": {"industry": "Conglomerates"}}}))
        return tmp_path, profiles

    def test_gather_joins_the_three_records(self, base):
        folder, profiles = base
        rows = C.gather(folder, date(2026, 11, 27), 8, profiles_path=profiles)
        got = {(r["symbol"], r["dive_date"]): (r["graph"], r["industry"]) for r in rows}
        assert got == {
            ("STEELCO", "2026-11-21"): ("generic", "Steel"),
            ("STEELCO", "2026-11-14"): ("generic", "Steel"),
            ("AUTOCO", "2026-11-21"): ("native", "Auto Parts"),
            ("BLANKCO", "2026-11-14"): ("generic", "Conglomerates"),
            ("HOTELCO", "2026-11-07"): ("generic", "Lodging"),
            ("MYSTERY", "2026-11-14"): ("", ""),
        }

    def test_the_report_counts_general_path_dives_only(self, base):
        folder, profiles = base
        rep = C.report(C.gather(folder, date(2026, 11, 27), 8, profiles_path=profiles),
                       LENSES)
        assert (rep["dives"], rep["general_path"], rep["native"], rep["graph_unknown"]) == (
            6, 4, 1, 1)
        assert rep["covered"] == 3 and rep["share"] == pytest.approx(0.75)
        assert rep["passes"] is False
        assert rep["by_label"][0] == {"industry": "Steel", "dives": 2, "lens": "steel"}
        text = C.render(rep, "2026-10-02", 8)
        assert "covered by a lens: 3 of 4 (75%)" in text and "NOT met" in text
        assert "too few to judge" in text
        assert "Conglomerates | 1 | default" in text

    def test_no_files_is_nothing_to_judge(self, tmp_path):
        rep = C.report(C.gather(tmp_path, date(2026, 11, 27)), LENSES)
        assert rep["general_path"] == 0 and rep["passes"] is False
        assert "nothing to judge" in C.render(rep, "2026-10-02", 8)


# ---------------------------------------------------------------------------
# The drafter
# ---------------------------------------------------------------------------

ANSWER = {"kpis": ["occupancy", "average room rate"], "news_terms": "results occupancy",
          "sector_query": "India hotels demand room rates news {month} {year}",
          "policy_query": "{company_name} occupancy room rates results {year}",
          "macro_drivers": ["travel demand"]}


class TestDrafter:
    def test_a_draft_loads_like_a_committed_lens(self, tmp_path):
        text = D.to_yaml("hotels", "Hotels", ["Lodging"], ANSWER)
        (tmp_path / "hotels.yaml").write_text(text, encoding="utf-8")
        lens = L.load_lenses(tmp_path).lens_for("Lodging").lens
        assert lens.kpis == ("occupancy", "average room rate")
        assert yaml.safe_load(text)["sector_query"] == ANSWER["sector_query"]

    @pytest.mark.parametrize("bad", [{"kpis": []},
                                     {"sector_query": "India generic news {month} {year}"},
                                     {"policy_query": "{company} results {year}"}])
    def test_a_bad_answer_is_refused(self, bad):
        with pytest.raises(L.LensError):
            D.to_yaml("hotels", "Hotels", ["Lodging"], {**ANSWER, **bad})

    def test_the_brief_names_the_labels_and_the_placeholders(self):
        text = D.brief("hotels", "Hotels", ["Lodging", "Resorts & Casinos"])
        assert '"Lodging", "Resorts & Casinos"' in text
        assert "{month}" in text and "{company_name}" in text and '"generic"' in text

    def test_dry_run_calls_no_model(self, monkeypatch, capsys):
        def no_call(prompt):
            raise AssertionError("called the model")
        monkeypatch.setattr(D, "ask_model", no_call)
        assert D.main(["--id", "hotels", "--display", "Hotels", "--industry", "Lodging",
                       "--dry-run"]) == 0
        assert "Industry group id: hotels" in capsys.readouterr().out

    def test_a_run_prints_the_checked_draft(self, monkeypatch, capsys, tmp_path):
        monkeypatch.setattr(D, "ask_model", lambda prompt: ANSWER)
        assert D.main(["--id", "hotels", "--display", "Hotels", "--industry", "Lodging"]) == 0
        assert "id: hotels" in capsys.readouterr().out
        out = tmp_path / "d.yaml"
        assert D.main(["--id", "hotels", "--display", "Hotels", "--industry", "Lodging",
                       "--out", str(out)]) == 0
        assert out.read_text(encoding="utf-8").startswith("# PR-032 industry lens (Hotels).")
