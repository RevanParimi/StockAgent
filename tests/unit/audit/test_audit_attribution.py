"""Miss taxonomy — ordering is the whole design, so it is tested first."""
from core.audit.attribution import attribution_distribution, classify_miss


def _miss(symbol="OLD", issued="2026-08-20", origin_excess=-2.0,
          dest_excess=-9.0, reason="not_best", ref="switch:x"):
    from backend.shared.schemas.audit import AuditOutcome
    return AuditOutcome(
        ref=ref, lane="switch", user_id="u", symbol=symbol, candidate="NEW",
        triggers=["taken", reason], issued_on=issued, horizon_td=10,
        graded_on=issued, entry_close=100.0, exit_close=98.0, return_pct=-2.0,
        bench_entry=1.0, bench_exit=1.0, bench_pct=0.0,
        excess_pct=origin_excess, switch_excess_pct=dest_excess, correct=False,
        graded_at="2026-09-01T00:00:00+00:00")


NEWS_SEEN = {("OLD", "2026-08-20"): True}
NEWS_BLIND = {("OLD", "2026-08-20"): False}


def test_a_shock_classifies_unpredictable():
    assert classify_miss(_miss(), news_index=NEWS_SEEN,
                         had_shock=True) == "unpredictable"


def test_a_shock_on_a_blind_day_is_still_unpredictable():
    """Ordering: a genuine shock must never be recorded as a plumbing failure,
    or the fix list fills with work that would not have helped."""
    assert classify_miss(_miss(), news_index=NEWS_BLIND,
                         had_shock=True) == "unpredictable"


def test_an_atr_breach_alone_classifies_unpredictable():
    assert classify_miss(_miss(), news_index=NEWS_SEEN,
                         atr_breach=True) == "unpredictable"


def test_news_blind_without_a_shock_classifies_technical():
    assert classify_miss(_miss(), news_index=NEWS_BLIND) == "technical"


def test_news_seen_and_still_wrong_classifies_knowledge():
    assert classify_miss(_miss(), news_index=NEWS_SEEN) == "knowledge"


def test_a_below_chance_rule_classifies_research_not_knowledge():
    assert classify_miss(_miss(), news_index=NEWS_SEEN,
                         below_chance=True) == "research"


def test_no_news_record_classifies_unknown_evidence():
    """Rows issued before the evidence writer shipped must not be silently
    blamed on the model — they sit outside the denominator, not inside it."""
    assert classify_miss(_miss(), news_index={}) == "unknown_evidence"


def test_a_correct_row_is_never_classified():
    row = _miss(dest_excess=9.0).model_copy(update={"correct": True})
    assert classify_miss(row, news_index=NEWS_SEEN) == ""


def test_distribution_excludes_unknown_evidence_from_the_denominator():
    rows = [_miss(), _miss(), _miss(symbol="NOREC")]
    dist = attribution_distribution(rows, news_index=NEWS_SEEN)
    assert dist["knowledge"] == 2
    assert dist["unknown_evidence"] == 1
    assert dist["n_classified"] == 2      # the denominator for any percentage


def test_distribution_marks_shocked_refs_unpredictable():
    rows = [_miss(ref="switch:a"), _miss(ref="switch:b")]
    dist = attribution_distribution(rows, news_index=NEWS_SEEN,
                                    shocked_refs={"switch:a"})
    assert dist["unpredictable"] == 1 and dist["knowledge"] == 1


def test_distribution_routes_a_below_chance_reason_to_research():
    rows = [_miss(reason="conviction_gap_too_small")]
    dist = attribution_distribution(
        rows, news_index=NEWS_SEEN,
        below_chance_reasons={"conviction_gap_too_small"})
    assert dist["research"] == 1 and dist["knowledge"] == 0
