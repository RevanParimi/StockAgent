"""
F2 — run_daily_review reports whether market-wide context rescued a blind ticker.

news_available (F5) answers "did the agent see company news"; it deliberately
stays False when the macro fallback fires, so the F1 blind-rate A/B is not
polluted. This second flag answers the F2 question — "did the agent have ANY
real evidence today" — which is what the miss-taxonomy validation compares.
"""
from datetime import date

from tests.unit.intelligence.rl.test_macro_fallback_context import _run_review, _BLIND, _HAS_NEWS


def test_summary_reports_macro_fallback_used_on_rescued_blind_ticker(tmp_path, monkeypatch):
    summary, _prompts = _run_review("TESTMACROFLAG1", tmp_path, monkeypatch, news_fn=_BLIND)

    assert summary["news_available"] is False, "company news is still absent — F1 metric intact"
    assert summary["macro_fallback_used"] is True


def test_summary_reports_no_fallback_when_macro_feed_empty(tmp_path, monkeypatch):
    summary, _prompts = _run_review(
        "TESTMACROFLAG2", tmp_path, monkeypatch, news_fn=_BLIND, macro_block="",
    )

    assert summary["news_available"] is False
    assert summary["macro_fallback_used"] is False


def test_summary_reports_no_fallback_when_company_news_present(tmp_path, monkeypatch):
    summary, _prompts = _run_review("TESTMACROFLAG3", tmp_path, monkeypatch, news_fn=_HAS_NEWS)

    assert summary["news_available"] is True
    assert summary["macro_fallback_used"] is False
