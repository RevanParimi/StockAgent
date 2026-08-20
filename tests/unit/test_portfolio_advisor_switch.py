"""Compass Phase C — SWITCH verdict (spec §5.2): EXIT + stronger shelf idea
in an UNDERWEIGHT sector. SWITCH is an EXIT variant — precedence unchanged,
tax logic never softens it, escalation lists include it."""
from datetime import date

from backend.shared.schemas.discovery import ShelfIdea
from backend.shared.schemas.portfolio import AdviceRecord, Holding, Portfolio
from core.portfolio.advisor import AdvisorSignals, decide
from core.portfolio.digest import build_digest


def _holding(symbol="OLDCO", sector="automobile"):
    return Holding(symbol=symbol, sector=sector, qty=10, avg_buy_price=100.0,
                   adj_avg_price=100.0, adj_qty=10, buy_date="2026-01-15")


def _exit_signals(confidence=0.5, sector="automobile"):
    # stop breach -> EXIT fires
    return AdvisorSignals(symbol="OLDCO", sector=sector, close=80.0,
                          atr_stop_pct=12.0, unrealised_pnl_pct=-15.0,
                          holding_age_days=100, confidence=confidence)


def _idea(symbol="NEWCO", sector="pharma", conviction=0.75):
    return ShelfIdea(symbol=symbol, sector=sector, added="2026-07-01",
                     conviction=conviction)


def test_switch_fires_on_exit_with_stronger_underweight_idea():
    rec = decide(_exit_signals(confidence=0.5), _holding(), "balanced",
                 shelf_ideas=[_idea(conviction=0.75)],
                 sector_weights={"automobile": 60.0, "pharma": 10.0})
    assert rec.verdict == "SWITCH"
    assert rec.switch_candidate == "NEWCO"
    assert "switch_candidate_available" in rec.triggers
    assert "stop_breach" in rec.triggers          # underlying EXIT trigger kept


def test_no_switch_when_gap_too_small():
    rec = decide(_exit_signals(confidence=0.70), _holding(), "balanced",
                 shelf_ideas=[_idea(conviction=0.75)],       # gap 0.05 < 0.15
                 sector_weights={"automobile": 60.0, "pharma": 10.0})
    assert rec.verdict == "EXIT" and rec.switch_candidate == ""


def test_no_switch_when_candidate_sector_not_underweight():
    rec = decide(_exit_signals(), _holding(), "balanced",
                 shelf_ideas=[_idea(sector="automobile", conviction=0.9)],
                 sector_weights={"automobile": 60.0})
    assert rec.verdict == "EXIT"                  # same-sector weight not strictly lower


def test_no_switch_without_exit():
    sig = AdvisorSignals(symbol="OLDCO", sector="automobile", close=110.0,
                         atr_stop_pct=12.0, unrealised_pnl_pct=10.0,
                         holding_age_days=100, confidence=0.5)
    rec = decide(sig, _holding(), "balanced",
                 shelf_ideas=[_idea(conviction=0.95)],
                 sector_weights={"automobile": 60.0, "pharma": 10.0})
    assert rec.verdict == "HOLD"


def test_backward_compatible_three_arg_call():
    rec = decide(_exit_signals(), _holding(), "balanced")
    assert rec.verdict == "EXIT"


def test_strongest_qualifying_idea_wins_and_dropped_ignored():
    ideas = [_idea("A", "pharma", 0.70),
             _idea("B", "fmcg", 0.85),
             ShelfIdea(symbol="C", sector="metals", added="2026-07-01",
                       conviction=0.99, status="dropped")]
    rec = decide(_exit_signals(confidence=0.5), _holding(), "balanced",
                 shelf_ideas=ideas,
                 sector_weights={"automobile": 60.0, "pharma": 5.0, "fmcg": 5.0})
    assert rec.switch_candidate == "B"


def test_switch_in_digest_escalations():
    h = _holding()
    rec = AdviceRecord(date="2026-07-09", user_id="u", symbol="OLDCO",
                       verdict="SWITCH", close=80.0, unrealised_pnl_pct=-15.0,
                       stop_pct=12.0, switch_candidate="NEWCO")
    digest = build_digest("u", date(2026, 7, 9), [rec],
                          Portfolio(user_id="u", holdings=[h]), {"OLDCO": 80.0})
    assert digest["escalations"] == ["OLDCO"]


# -- a switch must move you somewhere you are not already (2026-08-20) -------

def test_symbol_already_held_is_never_the_switch_destination():
    """"Switch OLDCO -> NEWCO" when NEWCO is already in the portfolio is not a
    switch, it is a top-up: it concentrates the book instead of rotating it,
    and the underweight-sector test that justified the call was computed on a
    sector the portfolio already owns."""
    rec = decide(_exit_signals(confidence=0.5), _holding(), "balanced",
                 shelf_ideas=[_idea("NEWCO", "pharma", 0.75)],
                 sector_weights={"automobile": 60.0, "pharma": 10.0},
                 held_symbols={"OLDCO", "NEWCO"})
    assert rec.verdict == "EXIT" and rec.switch_candidate == ""


def test_next_best_unheld_idea_wins_when_the_strongest_is_held():
    rec = decide(_exit_signals(confidence=0.5), _holding(), "balanced",
                 shelf_ideas=[_idea("HELD", "pharma", 0.95),
                              _idea("FREE", "fmcg", 0.80)],
                 sector_weights={"automobile": 60.0, "pharma": 5.0, "fmcg": 5.0},
                 held_symbols={"OLDCO", "HELD"})
    assert rec.verdict == "SWITCH" and rec.switch_candidate == "FREE"


def test_a_holding_is_never_switched_into_itself():
    """Needs no held_symbols from the caller — the reviewed symbol is known."""
    rec = decide(_exit_signals(confidence=0.5), _holding(), "balanced",
                 shelf_ideas=[_idea("OLDCO", "pharma", 0.95)],
                 sector_weights={"automobile": 60.0, "pharma": 5.0})
    assert rec.verdict == "EXIT" and rec.switch_candidate == ""


def test_digest_row_keeps_the_switch_destination():
    """The digest is what the brief reads. Dropping switch_candidate here is
    why "Needs attention" could say "TATAMOTORS Switch" and never name what to
    switch into."""
    h = _holding()
    rec = AdviceRecord(date="2026-07-09", user_id="u", symbol="OLDCO",
                       verdict="SWITCH", close=80.0, unrealised_pnl_pct=-15.0,
                       stop_pct=12.0, switch_candidate="NEWCO",
                       narrative="Stop went with the thesis.")
    digest = build_digest("u", date(2026, 7, 9), [rec],
                          Portfolio(user_id="u", holdings=[h]), {"OLDCO": 80.0})
    assert digest["holdings"][0]["switch_candidate"] == "NEWCO"


def test_digest_reason_falls_back_to_triggers_when_narration_failed():
    """`narrative` is an LLM field and empties out whenever narration fails —
    the deterministic triggers are always there."""
    h = _holding()
    rec = AdviceRecord(date="2026-07-09", user_id="u", symbol="OLDCO",
                       verdict="EXIT", close=80.0, unrealised_pnl_pct=-15.0,
                       stop_pct=12.0, narrative="", triggers=["stop_breach"])
    digest = build_digest("u", date(2026, 7, 9), [rec],
                          Portfolio(user_id="u", holdings=[h]), {"OLDCO": 80.0})
    assert "stop was breached" in digest["holdings"][0]["reason"]
