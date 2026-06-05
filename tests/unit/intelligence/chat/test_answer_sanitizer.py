"""Deterministic sanitizer: strips banned data-limitation disclaimer blocks the
model occasionally appends despite the prompt. (Replaces an unreliable LLM
Reflexion gate — see ui_data._sanitize_answer comment.)"""
from services.api.routes.ui_data import _sanitize_answer


def test_strips_critical_note_block():
    txt = ("**TCS ₹2248 (1mo -6.3%, at lows)** — oversold value play.\n"
           "*Sources: ET*\n\n"
           "**Critical Note:** No news from today found; data may be stale.")
    out = _sanitize_answer(txt)
    assert "Critical Note" not in out
    assert "TCS" in out and "Sources: ET" in out


def test_strips_important_note_at_end():
    txt = "Nifty ▼0.6%. Watch FII flows.\n\nImportant Note: always verify with your advisor."
    out = _sanitize_answer(txt)
    assert "Important Note" not in out
    assert "Nifty" in out


def test_keeps_legit_note_word():
    # 'note' inside a normal sentence must NOT be stripped.
    txt = "Note that ASHOKLEY is down 10% this week — a value entry."
    assert _sanitize_answer(txt) == txt


def test_passthrough_clean_answer():
    txt = "**LTTS ₹3312 (1mo -9.6%, at lows)** — value play. No catalyst in today's news."
    assert _sanitize_answer(txt) == txt


def test_never_returns_empty():
    assert _sanitize_answer("Disclaimer: nothing else here") != ""
