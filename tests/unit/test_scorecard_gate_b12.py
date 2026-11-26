"""BACKLOG B-12: after PR-015's switch, the scorecard's "Exit rule test" line names the rule
that was acting and words the switch gate for it.

Independent invariants:

- the acting rule is read from the rows (`mode`) of the week and before, the latest review
  day's, never from today's setting, and the line says that day;
- with the evidence rule acting, no sentence asks to switch to it; a pass supports keeping
  it; a fail says it is a reason to consider the rollback only when the rows show the
  evidence rule behind in count or money; while a result is unknown and no shortfall is
  shown it says it cannot yet tell, never that the rule is not doing worse; only with every
  result known (one stock's share) does it say the rule is not shown worse;
- with the price-path rule acting (`shadow`), the gate reads as it did before.

Each population below is counted by hand in its test. `S<i>` is decided at ₹100 with the Nifty
unused (plain EXITs graded against cash), its close at both horizons ₹100 + move: the evidence
rule that sold it is right when the move is below 0 and its result is -move.
"""
from __future__ import annotations

import json
from datetime import date

import pytest

from core.intelligence.rl.nse_calendar import trading_days_after
from core.portfolio import exit_shadow as xs
from tests.unit.test_exit_evidence_pr009 import _no_actions, _nse
from tests.unit.test_exit_fix016 import _rows_and_prices

AS_OF = date(2026, 12, 31)
PASS_WORDS = "not worse than the price-path rule in count and money"
KEEP = "which supports keeping the evidence rule. The owner decides."
ROLLBACK = "That is a reason to consider the rollback to the price-path rule. The owner decides."
NOT_SHOWN = "That does not show the evidence rule doing worse than the price-path rule."
UNKNOWN_YET = ("Some results are still unknown, so this does not yet show whether the evidence "
               "rule is doing worse than the price-path rule.")
# The first decision is 1 Jun 2026 and the last 60 days on, Friday 31 Jul.
LATEST = "31 Jul"
ACTING = {"evidence": f"Acting at the latest recorded review ({LATEST}): the evidence rule; "
                      "the price-path rule's verdict is recorded beside it. ",
          "shadow": f"Acting at the latest recorded review ({LATEST}): the price-path rule; "
                    "the evidence rule's verdict is recorded beside it. "}


def _sold(move: float):
    return (True, move)


def _rows(spec, mode="evidence", same_stock=()):
    """`spec` as in FIX-016's gate fixture, all rows in `mode`. The decisions at the indices
    in `same_stock` are one stock bought again (its move is the first one's)."""
    rows, moves = _rows_and_prices(spec)
    for i, row in enumerate(rows):
        row["mode"] = mode
        if i in same_stock:
            row["symbol"] = "SAME"
            row["buy_date"] = f"2026-05-{4 + i:02d}"      # each purchase its own holding
    if same_stock:
        moves["SAME"] = moves[f"S{min(same_stock)}"]
    return rows, moves


def _block(spec, mode="evidence", missing=(), same_stock=(), previous_look=None):
    """The block read after every horizon has ended. `missing` lists (index, horizon) pairs
    whose NSE close cannot be had that day."""
    rows, moves = _rows(spec, mode, same_stock)
    gone = {(rows[i]["symbol"], trading_days_after(date.fromisoformat(rows[i]["date"]), h))
            for i, h in missing}

    def close(symbol, day):
        if (symbol, day) in gone:
            raise LookupError("no close")
        return 100.0 + moves[symbol]

    return xs.scorecard_block(rows, as_of=AS_OF, stock_quote_on=_nse(close),
                              bench_close_on=lambda d: 1000.0, corp_actions=_no_actions,
                              previous_look=previous_look)


def _tail(block) -> str:
    """The line from its gate sentence on."""
    text = xs.scorecard_text(block)
    return text[text.index("Switch gate:"):]


# 11 sold stocks fell 3% (right), 4 rose 2% (wrong): 73% right, (11 x 3 - 4 x 2) / 15 = +1.67%.
GOOD = [_sold(-3.0)] * 11 + [_sold(2.0)] * 4
# 8 fell 2% (right), 7 rose 10% (wrong): 53% right, (8 x 2 - 7 x 10) / 15 = -3.6%.
LOSING = [_sold(-2.0)] * 8 + [_sold(10.0)] * 7
# 8 fell 5% (right), 7 rose 1% (wrong): 53% right, (8 x 5 - 7 x 1) / 15 = +2.2%.
NARROW = [_sold(-5.0)] * 8 + [_sold(1.0)] * 7


# -- The acting rule ------------------------------------------------------------------------------

def _row(day: str, mode: str, symbol="AAA") -> dict:
    return {"date": day, "mode": mode, "symbol": symbol}


def test_the_acting_rule_is_the_latest_review_days_by_date_not_file_order():
    rows = [_row("2026-11-23", "evidence"), _row("2026-11-20", "shadow", "BBB")]
    assert xs.latest_acting(rows) == {"rule": "evidence", "date": "2026-11-23"}
    # A rollback: the later day is shadow, so the price-path rule was acting.
    rows.append(_row("2026-11-27", "shadow"))
    assert xs.latest_acting(rows) == {"rule": "legacy", "date": "2026-11-27"}


def test_of_one_days_rows_the_later_written_counts():
    """The setting changed between two runs of one day: the rows are appended in order."""
    rows = [_row("2026-11-23", "shadow"), _row("2026-11-23", "evidence", "BBB")]
    assert xs.latest_acting(rows)["rule"] == "evidence"
    assert xs.latest_acting(rows[::-1])["rule"] == "legacy"


def test_rows_that_name_no_mode_or_day_give_no_acting_rule_and_no_sentence():
    assert xs.latest_acting([]) is None
    assert xs.latest_acting([{"date": "2026-11-23"}, {"mode": "evidence"},
                             _row("not a day", "evidence"), _row("2026-11-23", "x")]) is None
    block = _block(GOOD)
    block["acting"] = None
    assert xs.scorecard_text(block).startswith("The price-path rule and the evidence rule")
    assert "may replace" not in _tail(block) and "it must pass again next week" in _tail(block)


def test_the_acting_rule_reads_only_rows_up_to_the_weeks_end():
    """The week ending 31 Jul is read after the switch to `evidence` on 3 Aug: the line still
    names the rule that was acting by 31 Jul."""
    rows, moves = _rows(GOOD, "shadow")
    rows.append({**rows[-1], "date": "2026-08-03", "symbol": "LATER", "mode": "evidence"})
    block = xs.scorecard_block(rows, as_of=date(2026, 8, 2), stock_quote_on=_nse(100.0),
                               bench_close_on=lambda d: 1000.0, corp_actions=_no_actions)
    assert block["acting"] == {"rule": "legacy", "date": "2026-07-31"}
    assert block["rows"] == 15


def test_the_line_opens_with_the_acting_rule_and_its_review_day():
    for mode, opening in ACTING.items():
        block = _block(GOOD, mode)
        assert xs.scorecard_text(block).startswith(
            opening + "The price-path rule and the evidence rule disagreed on 15 decisions")


# -- The gate's words ------------------------------------------------------------------------------

def test_a_passing_week_under_the_evidence_rule_supports_keeping_it():
    block = _block(GOOD)
    assert (block["gate"]["status"], block["gate"]["worse"], block["recommend"]) == (
        xs.PASS, False, False)
    assert _tail(block) == (
        f"Switch gate: passed this week ({PASS_WORDS}; better: right on at least 70% with a "
        "positive mean); a second passing week running would support keeping the evidence "
        "rule.")
    twice = _block(GOOD, previous_look={"status": xs.PASS})
    assert twice["recommend"] is True
    assert _tail(twice) == (
        f"Switch gate: passed two weeks running ({PASS_WORDS}; better: right on at least 70% "
        f"with a positive mean), {KEEP}")


def test_under_the_price_path_rule_the_gate_reads_as_before():
    assert _tail(_block(GOOD, "shadow")) == (
        f"Switch gate: passed this week ({PASS_WORDS}; better: right on at least 70% with a "
        "positive mean); it must pass again next week.")
    assert _tail(_block(GOOD, "shadow", previous_look={"status": xs.PASS})) == (
        f"Switch gate: passed two weeks running ({PASS_WORDS}; better: right on at least 70% "
        "with a positive mean), so the evidence rule may replace the price-path rule. "
        "The owner decides.")
    losing = _block(LOSING, "shadow")
    assert losing["gate"]["worse"] is True
    assert _tail(losing) == (
        "Switch gate: fails (its mean result at 10 sessions is -3.60% (needs at least +0.00%); "
        "its mean result at 30 sessions is -3.60% (needs at least +0.00%)).")


def test_no_line_asks_to_switch_to_the_rule_that_already_acts():
    for spec in (GOOD, LOSING, NARROW):
        for previous in (None, {"status": xs.PASS}):
            text = xs.scorecard_text(_block(spec, previous_look=previous))
            assert "may replace" not in text and "must pass again" not in text


def test_a_money_shortfall_is_a_reason_to_consider_the_rollback():
    block = _block(LOSING)
    assert (block["gate"]["status"], block["gate"]["worse"]) == (xs.FAIL, True)
    assert _tail(block) == (
        "Switch gate: fails (its mean result at 10 sessions is -3.60% (needs at least +0.00%); "
        f"its mean result at 30 sessions is -3.60% (needs at least +0.00%)). {ROLLBACK}")


def test_a_count_shortfall_alone_is_a_reason_even_with_a_positive_mean():
    """6 fell 10% (right), 9 rose 1% (wrong): right on 6 of 15, 40%, mean (60 - 9) / 15 = +3.4."""
    block = _block([_sold(-10.0)] * 6 + [_sold(1.0)] * 9)
    assert block["gate"]["mean_result_pct"] == {"10": 3.4, "30": 3.4}
    assert block["gate"]["worse"] is True and _tail(block).endswith(ROLLBACK)


def test_a_missing_price_alone_is_not_a_reason():
    """NARROW with one right decision's close missing at 10 sessions: right on 7 of 15 there
    (below half) only because that one is unknown (7 + 1 = 8 of 15), and the 30-session mean is
    +2.2%. The gate fails, and the line does not blame the rule."""
    block = _block(NARROW, missing=[(0, 10)])
    look = block["gate"]
    assert (look["status"], look["right"], look["unknown_result"]) == (
        xs.FAIL, {"10": 7, "30": 8}, {"10": 1, "30": 0})
    assert look["worse"] is False
    assert _tail(block).endswith(f"so the money check cannot pass). {UNKNOWN_YET}")
    assert "right on 7 of 15 at 10 sessions" in _tail(block)


def test_a_loss_among_the_known_results_beside_a_missing_price_is_not_called_not_worse():
    """The Opus review's case: at 10 sessions 8 sold stocks fell 2% and 7 rose 10%, with one
    of the wrong ones missing (right on 8 of 14 known, mean (8 x 2 - 6 x 10) / 14 = -3.14%); at
    30 sessions all 15 fell 3% (right on 15, mean +3.0%). The only fail reason is the unknown,
    so the line must not say the rule is not doing worse: its own 10-session figure is a loss."""
    rows, _ = _rows(LOSING)
    at10 = {r["symbol"]: m for r, (_, m) in zip(rows, LOSING)}
    due10 = {(r["symbol"], trading_days_after(date.fromisoformat(r["date"]), 10)): r["symbol"]
             for r in rows}
    gone = ("S14", trading_days_after(date.fromisoformat(rows[14]["date"]), 10))

    def close(symbol, day):
        if (symbol, day) == gone:
            raise LookupError("no close")
        return 100.0 + (at10[symbol] if (symbol, day) in due10 else -3.0)

    block = xs.scorecard_block(rows, as_of=AS_OF, stock_quote_on=_nse(close),
                               bench_close_on=lambda d: 1000.0, corp_actions=_no_actions)
    look = block["gate"]
    assert (look["status"], look["right"], look["unknown_result"], look["worse"]) == (
        xs.FAIL, {"10": 8, "30": 15}, {"10": 1, "30": 0}, False)
    text = xs.scorecard_text(block)
    assert "at 10 sessions it was right on 8 of 14, averaging -3.14%" in text
    assert text.endswith(UNKNOWN_YET) and NOT_SHOWN not in text


def test_a_set_aside_decision_leaves_a_money_shortfall_a_reason():
    """16 decisions, 3.6% a decision lost on the 15 judged (the LOSING 15) and a 16th, in the
    middle of the span, never gradable after a demerger: set aside, the 15 still fail on money."""
    from core.portfolio.corp_actions import ActionRecord
    rows, moves = _rows(LOSING)
    extra_day = rows[7]["date"]
    rows.append({**rows[7], "symbol": "DEM", "buy_date": "2026-05-20"})
    moves["DEM"] = -50.0
    ex = trading_days_after(date.fromisoformat(extra_day), 3).isoformat()

    def actions(symbol):
        return ActionRecord(covers_from="2000-01-01",
                            basis_changes=[(ex, "demerger")] if symbol == "DEM" else [])

    block = xs.scorecard_block(rows, as_of=AS_OF, stock_quote_on=_nse(
        lambda s, d: 100.0 + moves[s]), bench_close_on=lambda d: 1000.0, corp_actions=actions)
    look = block["gate"]
    assert (look["status"], look["judged"], len(look["set_aside"]), look["worse"]) == (
        xs.FAIL, 15, 1, True)
    assert f"{ROLLBACK} Set aside, as its result can never be known: DEM" in (
        xs.scorecard_text(block))


def test_short_even_counting_the_unknown_as_right_is_a_reason():
    """5 right of 15 at both, one wrong decision's close missing at 10 sessions: 5 + 1 = 6 of 15
    is still below half. Its mean is positive at 30."""
    spec = [_sold(-10.0)] * 5 + [_sold(1.0)] * 10
    block = _block(spec, missing=[(14, 10)])
    assert block["gate"]["unknown_result"] == {"10": 1, "30": 0}
    assert block["gate"]["worse"] is True and _tail(block).endswith(ROLLBACK)


def test_a_known_money_loss_at_one_horizon_is_a_reason_beside_a_missing_price_at_the_other():
    block = _block(LOSING, missing=[(0, 10)])
    assert block["gate"]["unknown_result"] == {"10": 1, "30": 0}
    assert block["gate"]["mean_result_pct"] == {"10": None, "30": -3.6}
    assert block["gate"]["worse"] is True and _tail(block).endswith(ROLLBACK)


def test_one_stocks_share_alone_is_not_a_reason():
    """NARROW with five of the right decisions one stock bought five times: 5 of 15 is 33%."""
    block = _block(NARROW, same_stock=(0, 1, 2, 3, 4))
    look = block["gate"]
    assert (look["status"], look["reasons"], look["worse"]) == (
        xs.FAIL, ["SAME is 5 of the 15 (more than 30%)"], False)
    assert _tail(block) == (
        f"Switch gate: fails (SAME is 5 of the 15 (more than 30%)). {NOT_SHOWN}")
    assert UNKNOWN_YET not in _tail(block)


def test_right_on_exactly_half_with_a_zero_mean_is_not_worse():
    """16 decisions: 8 right at +1, 8 wrong at -1. 50% and a mean of exactly 0 both pass."""
    block = _block([_sold(-1.0)] * 8 + [_sold(1.0)] * 8)
    assert (block["gate"]["status"], block["gate"]["worse"]) == (xs.PASS, False)


@pytest.mark.parametrize("spec, status", [
    ([_sold(-3.0)] * 14, xs.NOT_ENOUGH),                      # 14 of the 15 it needs
    ([_sold(-3.0)] * 15, xs.PASS),
])
def test_a_gate_that_has_not_failed_says_nothing_of_the_rollback(spec, status):
    block = _block(spec)
    assert block["gate"]["status"] == status and block["gate"]["worse"] is False
    assert "rollback" not in xs.scorecard_text(block)


def test_cannot_judge_says_nothing_of_the_rollback():
    """18 decisions past 30 sessions, 3 of them (in the middle, so the other 15 still span 60
    days) never gradable after a demerger: more than the 2 the cap allows, so a passing look
    reads cannot judge."""
    from core.portfolio.corp_actions import ActionRecord
    spec = [_sold(-3.0)] * 18
    rows, moves = _rows(spec)

    def actions(symbol):
        if symbol in ("S5", "S6", "S7"):
            decided = date.fromisoformat(rows[int(symbol[1:])]["date"])
            ex = trading_days_after(decided, 3).isoformat()
            return ActionRecord(covers_from="2000-01-01", basis_changes=[(ex, "demerger")])
        return ActionRecord(covers_from="2000-01-01")

    block = xs.scorecard_block(rows, as_of=AS_OF, stock_quote_on=_nse(
        lambda s, d: 100.0 + moves[s]), bench_close_on=lambda d: 1000.0, corp_actions=actions)
    assert block["gate"]["status"] == xs.CANNOT_JUDGE and block["gate"]["worse"] is False
    assert "rollback" not in xs.scorecard_text(block)


# -- Through the weekly scorecard ------------------------------------------------------------------

def test_the_sunday_email_names_the_acting_rule_from_the_stored_rows(tmp_path):
    """The real weekly scorecard on Sunday 8 Nov 2026, rows decided under `evidence`: the line
    in the email opens with the acting rule and a fail on money names the rollback."""
    from core.portfolio import results as R
    from core.portfolio.store import PortfolioStore

    store = PortfolioStore(user_id="u1", base_dir=str(tmp_path))
    store.load()
    rows, moves = _rows(LOSING)
    with open(tmp_path / "u1" / "exit_shadow.jsonl", "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps({**row, "user_id": "u1"}) + "\n")
    card = R.weekly_scorecard(
        "u1", date(2026, 11, 8), store=store,
        audit_store=type("A", (), {"load_all": lambda self: []})(),
        close_on=lambda d: 1000.0, stock_close_on=lambda s, d: 100.0 + moves[s],
        stock_quote_on=_nse(lambda s, d: 100.0 + moves[s]), corp_actions=_no_actions,
        today=date(2026, 11, 8))
    line = next(l["text"] for l in card["lines"] if l.get("label") == "Exit rule test")
    assert line.startswith(ACTING["evidence"]) and line.endswith(ROLLBACK)
    email = "\n".join(R.render_scorecard_text(card))
    assert line in email
    # Written once and read back as stored.
    assert store.load_scorecard(card["week"])["exit_rule"]["acting"] == {
        "rule": "evidence", "date": "2026-07-31"}
