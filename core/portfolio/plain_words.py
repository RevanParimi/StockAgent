"""
PR-007: the plain words for every buy, sell and hold. Pure: no I/O, no clock.

Each explanation has four short parts, `{did, why, wrong_if, next}`: what we
did, why, what would change our mind, what happens next. **Code writes what
happened and the rule that fired.** The first sentence of `why` names that
rule in an investor's words, before any context, so a sale by the safety
limit is never told as a sale for weak results. A model may add to a purchase
only, never to a sale (core/portfolio/explain.py): one sentence about the
company and one warning sign, checked here (`check_company_sentence`): it
never speaks of our action, and every number in it, written as digits or as a
word, is a number of the inputs it was given.

This text is for display. The ledger's `reason` and `note`, the advice
narrative and the digest's deployment record stay as they are: they remain
the audit text, and no buy, sell, size or grade reads anything here.

**Banned words** (`banned_in`): the machine words a reader cannot use: trigger
and note codes, verdict codes in capitals, market-mood codes, "envelope",
"ATR", "reversion prior", "conviction streak", "data gate", "rationale
hash", "agent" and "market regime". Every template here is free of them, whatever
facts it is given: a fact that carries one is left out (`clean`).
"""
from __future__ import annotations

import re
from datetime import date

from core.portfolio.cases import figures, ungrounded
from core.portfolio.sizing import inr

PARTS = ("did", "why", "wrong_if", "next")
MAX_SENTENCES = 2
MAX_SENTENCE_CHARS = 280

# -- Banned words ----------------------------------------------------------------

_BANNED = (
    ("envelope", r"(?i)\benvelopes?\b"),
    ("ATR", r"(?i)\bATR\b"),
    ("reversion prior", r"(?i)\breversion\s+prior\b"),
    ("conviction streak", r"(?i)\bconviction\s+streak\b"),
    ("data gate", r"(?i)\bdata[\s_-]*gate\b"),
    ("rationale hash", r"(?i)\brationale[\s_-]*hash\b"),
    ("agent", r"(?i)\bagents?\b"),
    ("market regime", r"(?i)\bmarket\s+regimes?\b"),
    # The market-mood codes, in the capitals the machine writes them in
    # ("a new tax regime" is plain English).
    ("market code", r"\b(?:NORMAL|RISK[_ ](?:ON|OFF)|MACRO[_ ]CRISIS|MOMENTUM[_ ]EXTENDED|OVERSOLD)\b"),
    # Verdict codes, in the capitals the machine writes them in. "We add more"
    # is plain English; "ADD" is a code.
    ("verdict code", r"\b(?:EXIT|TRIM|SWITCH|DEPLOY|HOLD|ADD|NO_DATA|BUY|SELL|NEUTRAL|STRONG BUY|STRONG SELL)\b"),
    # Any CODE_LIKE_THIS or code_like_this: market moods, notes, triggers.
    ("code", r"\b[A-Za-z]+(?:_[A-Za-z0-9]+)+\b"),
)


def banned_in(text: str) -> list[str]:
    """The banned words `text` uses, by name; [] when it uses none."""
    return [name for name, pattern in _BANNED if re.search(pattern, text or "")]


def clean(text: str, fallback: str = "") -> str:
    """`text` when it uses no banned word, else `fallback`."""
    text = " ".join(str(text or "").split())
    return text if text and not banned_in(text) else fallback


# -- Small formatting --------------------------------------------------------------

def price(value: float) -> str:
    """A share price with Indian grouping: ₹5,420.00, ₹1,27,140.50."""
    rupees = f"{float(value):.2f}"
    whole, paise = rupees.split(".")
    sign = "-" if whole.startswith("-") else ""
    digits = whole.lstrip("-")
    grouped = inr(int(digits))[1:]
    return f"{sign}₹{grouped}.{paise}"


def money(value: float) -> str:
    """A rupee amount, no paise: ₹3,00,000."""
    return inr(value)


def day(value) -> str:
    """"12 Nov 2026"; the input as written when it is not a date."""
    try:
        d = value if isinstance(value, date) else date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return str(value or "")
    return f"{d.day} {d.strftime('%b %Y')}"


def shares(qty: float) -> str:
    n = int(round(qty))
    return f"{n:,} share{'s' if n != 1 else ''}"


_ABBREVIATION = re.compile(r"(?:^|\s|\()(?:Rs|No|Pvt|Ltd|Co|Corp|Bros|Inc|Mr|Ms|Dr|St|vs|approx|e\.g|i\.e)\.$",
                           re.IGNORECASE)


def sentences(text: str) -> list[str]:
    """`text` as sentences. A full stop inside a figure (₹547.86) ends none,
    nor does the one of "Rs." or "Ltd."."""
    text = " ".join(str(text or "").split())
    out: list[str] = []
    for piece in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9₹\"'“(])", text):
        if out and _ABBREVIATION.search(out[-1]):
            out[-1] = f"{out[-1]} {piece}"
        elif piece:
            out.append(piece)
    return out


def first_sentence(text: str, limit: int = MAX_SENTENCE_CHARS) -> str:
    found = sentences(text)
    if not found:
        return ""
    out = found[0]
    if len(out) > limit:
        out = out[:limit].rsplit(" ", 1)[0].rstrip(",;:") + " …"
    return out if out[-1:] in ".!?…" else out + "."


def end(text: str) -> str:
    """`text` ending in one full stop."""
    text = str(text or "").strip().rstrip(".;, ")
    return f"{text}." if text else ""


def stop_price(cost: float, stop_pct: float, dividends_per_share: float = 0.0) -> float:
    """The price at or below which the stop fires, in the rupees of `cost`:
    the advisor sells when P&L against cost, dividends counted, reaches
    −stop_pct%. Rounded to the paisa."""
    return round(cost * (1.0 - stop_pct / 100.0) - dividends_per_share, 2)


# -- Why a rule fired --------------------------------------------------------------

def case_broken_parts(evidence: dict | None, close: float) -> list[dict]:
    """The reasons the case broke, each with its own facts, from an exit
    evidence record (`ExitEvidence.model_dump()`). The same three tests, in
    the same order, as `advisor.case_broken_reasons`: a high negative event
    from an NSE source, an actionable sell research verdict, or a close at or
    below the invalidation level. {"kind": "event"|"verdict"|"level", ...}."""
    from core.portfolio.advisor import CASE_EVENT_SOURCES, SELL_RESEARCH_VERDICTS
    if not evidence:
        return []
    out: list[dict] = []
    for event in evidence.get("negative_events") or []:
        if event.get("source") not in CASE_EVENT_SOURCES:
            continue
        out.append({"kind": "event", "day": str(event.get("published_at") or "")[:10],
                    "what": str(event.get("what") or "").strip()})
    verdict = str(evidence.get("research_verdict") or "").strip().upper()
    if verdict in SELL_RESEARCH_VERDICTS:
        from core.discovery.candidates import _ist_day
        ran = _ist_day(evidence.get("research_run_at") or "")
        out.append({"kind": "verdict", "verdict": verdict,
                    "day": ran.isoformat() if ran else ""})
    level = float(evidence.get("invalidation_level") or 0.0)
    if level > 0 and close <= level:
        at_dive = float(evidence.get("invalidation_level_at_dive") or 0.0)
        out.append({"kind": "level", "close": float(close), "level": level,
                    "at_dive": at_dive})
    return out


def broken_phrase(part: dict) -> str:
    """One broken reason as a clause ("the company reported ... on 5 Nov")."""
    if part["kind"] == "event":
        what = clean(first_sentence(part.get("what", "")).rstrip("."),
                     "bad news about the company")
        when = f" on {day(part['day'])}" if part.get("day") else ""
        return f"bad news came out{when}: {what}"
    if part["kind"] == "verdict":
        word = "a strong sell" if part["verdict"] == "STRONG SELL" else "a sell"
        when = f" on {day(part['day'])}" if part.get("day") else ""
        return f"our latest research on it{when} rated it {word}"
    text = (f"it closed at {price(part['close'])}, at or below {price(part['level'])}, the "
            "price at which we had said the reason to own it would no longer hold")
    at_dive = part.get("at_dive") or 0.0
    if at_dive and abs(at_dive - part["level"]) > 0.005:
        text += f" ({price(at_dive)} when we set it, before a bonus or share split)"
    return text


def _join(clauses: list[str]) -> str:
    return "; and ".join(c for c in clauses if c)


def sell_rule_clauses(triggers, facts: dict) -> list[str]:
    """One clause per selling rule that fired, the advisor's order, in plain
    words. `facts`: stop_price, peak_price, trail_price, broken (the
    `case_broken_parts`), bought_on_other (the advisor's sentence). A figure
    not in `facts` is simply not named."""
    out: list[str] = []
    for code in triggers or []:
        if code == "switch_candidate_available":
            continue                              # where the money went, not why we sold
        if code == "bought_on_other_analysis":
            other = clean(facts.get("bought_on_other") or "")
            out.append("we had bought it using research about a different company"
                       + (f" ({other})" if other else "")
                       + ", so there was never a real reason to own this one")
        elif code == "stop_breach":
            at = facts.get("stop_price")
            out.append("the price fell to or below our safety limit"
                       + (f" of {price(at)}" if at else "")
                       + ", the most we let a holding lose")
        elif code == "trailing_stop_breach":
            peak, line = facts.get("peak_price"), facts.get("trail_price")
            text = "after rising, it fell back further than we allow from its highest price"
            if peak and line:
                text += (f" since we bought it ({price(peak)}), through our safety line of "
                         f"{price(line)}")
            out.append(text)
        elif code == "case_broken":
            broken = [broken_phrase(p) for p in facts.get("broken") or []]
            out.append("the reason we owned it broke"
                       + (f": {_join(broken)}" if broken else ""))
        elif code == "thesis_break":
            out.append("the reason we owned it no longer held, and our price forecast "
                       "pointed down")
        elif code == "shock_reforecast":
            out.append("a sudden shock made us redo our price forecast, and the new one "
                       "points down")
        elif code == "crisis_regime_bearish":
            out.append("the whole market is in a severe downturn and our price forecast for "
                       "it points down")
        elif code == "trim_profit_confidence_decline":
            out.append("it had made a good profit and we had become less sure how much "
                       "further it could rise")
        elif code == "trim_profit_reversion_elevated":
            out.append("it had made a good profit and a fall back after the long rise had "
                       "become more likely")
        else:
            out.append("one of our selling rules was met")
    return out


def sell_why(triggers, facts: dict, *, part: bool = False) -> str:
    """The first sentence of a sale's why: the rules that fired."""
    clauses = sell_rule_clauses(triggers, facts) or ["one of our selling rules was met"]
    lead = "We sold part of it because " if part else "We sold because "
    return end(lead + _join(clauses))


# -- What an add rests on --------------------------------------------------------

def add_why(facts: dict) -> str:
    text = "We bought more because our price forecast for it points up"
    right = facts.get("calls_right_pct")
    if right is not None:
        text += f" and {right:.0f}% of its recent daily calls were right"
    else:
        text += " and its recent daily calls have mostly been right"
    return end(text)


def deploy_why(*, cheaper_than_planned: bool = False) -> str:
    where = ("below the price range we planned to pay, so cheaper than planned"
             if cheaper_than_planned else "within the price range we planned to pay")
    return end("We bought it because its research rates it a buy, it passed our checks, "
               f"and its price was {where}")


def switch_in_why(origin: str, *, cheaper_than_planned: bool = False) -> str:
    where = (" at less than we planned to pay" if cheaper_than_planned else "")
    return end(f"We bought it{where} to replace {origin}, which we sold the same day: it "
               "rated more strongly and sits in a part of the market where we held less")


# -- Where the money went ----------------------------------------------------------

# The executor's reasons a buy did not happen, in the order they are tested:
# (pattern, plain words). Matched against the reason alone, never the symbol or
# the money around it.
_SKIP_PLAIN = (
    (r"^identity:", "we could not confirm that its price was its own"),
    (r"surveillance report", "the exchange's watch list did not clear it"),
    (r"above entry band", "its price was above the range we planned to pay"),
    (r"entry band", "it had no planned price range on record, so it needs fresh research"),
    (r"invalidation", "its price had fallen to where its research would no longer hold"),
    (r"^sold |sold by the autopilot",
     "we had sold it recently and are waiting for new research"),
    (r"not a BUY|no verdict|stored no verdict|kept no verdict|analysis is of",
     "its research did not support a buy"),
    (r"is before the (?:deep dive|analysis)|after the close of|undated bar|has no time"
     r"|no price for|no close|close is from bar",
     "no suitable closing price was available"),
    (r"data gate", "we could not fully check its data"),
    (r"position cap|cap on|cash floor",
     "a limit on how much we put in one place left no room"),
    (r"less than one share", "the money was not enough for even one share"),
    (r"ledger|reconciliation", "its record needs a check"),
)


def _bare_reason(reason: str) -> str:
    """The reason itself: without the "SYMBOL: " a skipped switch's note opens
    with, the money it ends with, or a top-up's "top-up skipped: "."""
    text = str(reason or "").strip()
    text = re.sub(r"^top-up skipped:\s*", "", text)
    text = re.sub(r"^(?!identity:)[A-Z0-9&_.-]{1,20}:\s*", "", text)
    return re.sub(r";\s*₹[\d,]+ stays in cash\s*$", "", text)


def plain_skip(reason: str) -> str:
    """The executor's reason a buy was skipped, in plain words. The date of
    the exchange's report is kept: it says how current that refusal is."""
    bare = _bare_reason(reason)
    for pattern, plain in _SKIP_PLAIN:
        flags = 0 if pattern.startswith("^identity") else re.IGNORECASE
        if re.search(pattern, bare, flags):
            dated = re.search(r"surveillance report of (\d{4}-\d{2}-\d{2})", bare)
            return f"{plain} (its report of {day(dated.group(1))})" if dated else plain
    return "it did not pass our buying checks"


def sale_next(*, proceeds: float | None, switch_to: str = "", bought: bool = False,
              spent: float | None = None, skip_reason: str = "") -> str:
    """Where a sale's money went. `spent` is what a switch's buy took, its
    costs included: a buy capped by a limit, or rounded down to whole shares,
    leaves the rest in cash."""
    amount = f" of {money(proceeds)}" if proceeds else ""
    if switch_to:
        if bought:
            left = (proceeds - spent) if proceeds and spent is not None else 0.0
            if left >= 1.0:
                return (f"We used {money(spent)} of the money to buy {switch_to}; the other "
                        f"{money(left)} stays in cash.")
            return f"We used the money{amount} to buy {switch_to}."
        why = plain_skip(skip_reason) if skip_reason else "it could not be bought"
        return (f"We meant to move the money into {switch_to} but did not: {why}. "
                f"The money{amount} stays in cash.")
    return f"The money{amount} goes back to cash, where a later buy that passes our checks can use it."


NO_REBUY = ("We would only buy it back after new research, done after this sale, rates it "
            "a buy again.")
# A holding row's advice to sell: nothing has been sold by it.
ADVICE_NO_REBUY = ("Once it is sold, we would only advise buying it back after new research, "
                   "done after the sale, rates it a buy again.")


def rest_wrong_if(rest_stop: float | None) -> str:
    limit = f" of {price(rest_stop)}" if rest_stop else ""
    return (f"We still hold the rest, and would sell it if the price falls to our safety "
            f"limit{limit} or the reason to own it breaks.")


def holding_wrong_if(*, stop: float | None, level: float | None, wait_sessions: int,
                     traded: bool = False, exit_rule: str = "evidence") -> str:
    """What would make us sell (`traded`, a trade's own words) or make the
    review advise it: a portfolio without the autopilot is never traded. The
    news and level tests are the evidence rule's; under the legacy rule
    (`exit_rule`), the price-path test is named instead."""
    limit = f" of about {price(stop)}" if stop else ""
    subject = "We would sell" if traded else "We would advise selling"
    if exit_rule != "evidence":
        return (f"{subject} if the price falls to the safety limit{limit}, or if the reason "
                "to own it stops holding while our price forecast points down.")
    # The rule's three tests, and the wait that holds all three back
    # (advisor.case_broken_fires); the safety limit never waits.
    broke = ["bad news in the company's own filings", "a fresh sell view from our research"]
    if level:
        broke.append(f"a close at or below {price(level)}")
    listed = f"{', '.join(broke[:-1])} or {broke[-1]}"
    return (f"{subject} if the price falls to the safety limit{limit}, or if the reason to "
            f"own it breaks: {listed} (these count only once it has been held "
            f"{wait_sessions} trading days).")


REVIEW_NEXT = "We check it again after each trading day's close."
TRADE_NEXT = "Any trade this leads to shows in your trade history."
YOUR_CALL_NEXT = "Whether to trade is your decision; this is research, not an order."


def parts(did: str, why: str, wrong_if: str, nxt: str) -> dict:
    return {"did": did.strip(), "why": why.strip(),
            "wrong_if": wrong_if.strip(), "next": nxt.strip()}


# -- Notes on a holding ------------------------------------------------------------

def regime_unavailable_plain(sentence: str) -> str:
    """FIX-024's "market regime unavailable for 2026-10-30: India VIX did not
    answer" in plain words, naming the day and why; never calling the market
    calm or normal."""
    m = re.match(r"\s*market regime unavailable for (\d{4}-\d{2}-\d{2}):\s*(.*)$",
                 sentence or "", re.IGNORECASE)
    if not m:
        return "we could not read the market's condition on the review day"
    why = clean(m.group(2).strip().rstrip("."))
    return (f"we could not read the market's condition for {day(m.group(1))}"
            + (f" ({why})" if why else ""))


# The order notes are told in, when a holding has several.
NOTE_ORDER = ("IDENTITY", "WAIT_FOR_LTCG", "REGIME_UNAVAILABLE", "DATA_GATE",
              "ENVELOPE_AFTER_CLOSE", "EARNINGS_GAP_PROTECTION", "POSITION_LARGE",
              "SECTOR_CONCENTRATION_HIGH")


def note_sentence(code: str, facts: dict) -> str:
    """One annotation on a holding as one plain sentence, "" for one we do not
    tell. `facts`: manual (a portfolio with no cash on record, SA-050 R4: it
    is told its weight among its holdings, and nothing about buying),
    position_cap, sector_cap, regime_unavailable."""
    manual = bool(facts.get("manual"))
    pos, sec = facts.get("position_cap"), facts.get("sector_cap")
    cap = f"{pos:g}%" if pos else "our limit"
    sector_cap = f"{sec:g}%" if sec else "our limit"
    if code == "POSITION_LARGE":
        if manual:
            return f"It is over {cap} of your holdings."
        return f"It is over {cap} of your whole portfolio, so no more of it will be bought."
    if code == "SECTOR_CONCENTRATION_HIGH":
        if manual:
            return f"Its sector is over {sector_cap} of your holdings."
        return (f"Its sector is over {sector_cap} of your whole portfolio, so no more of "
                "that sector will be bought.")
    if code == "WAIT_FOR_LTCG":
        return ("We would normally take some profit now, but waiting a little longer means "
                "the gain is taxed at the lower long-term rate.")
    if code == "EARNINGS_GAP_PROTECTION":
        # FIX-031 R1: the exchange's calendar keeps no announcement time.
        return ("Results are due within a few days, going by the exchange's calendar as "
                "read when the review ran, so the date may have been announced after that "
                "day's close.")
    if code == "REGIME_UNAVAILABLE":
        return end("No more was bought because "
                   + regime_unavailable_plain(facts.get("regime_unavailable") or ""))
    if code == "ENVELOPE_AFTER_CLOSE":
        return ("No more was bought: only a price forecast made after the review day's "
                "close would have supported it.")
    if code == "DATA_GATE":
        return ("No buying or switching was allowed because the price or forecast behind "
                "it could not be checked.")
    if code == "IDENTITY":
        return ("Nothing will be done with it for now, because its market price cannot be "
                "confirmed as this holding's own: its listing changed or is unclear.")
    return ""


def notes_sentence(notes, facts: dict) -> str:
    """Every note of a holding in one sentence, "" for none."""
    codes = sorted(set(notes or []),
                   key=lambda c: NOTE_ORDER.index(c) if c in NOTE_ORDER else len(NOTE_ORDER))
    told = [note_sentence(c, facts).rstrip(".") for c in codes]
    told = [t for t in told if t]
    if not told:
        return ""
    rest = "".join(f"; also, {t[:1].lower()}{t[1:]}" for t in told[1:])
    return f"{told[0]}{rest}."


def _move(pnl_pct: float | None) -> str:
    if pnl_pct is None:
        return ""
    if abs(pnl_pct) < 0.05:
        return "It is level with what was paid"
    word = "up" if pnl_pct > 0 else "down"
    return f"It is {word} {abs(pnl_pct):.1f}% on what was paid"


def holding_parts(symbol: str, verdict: str, *, triggers=(), notes=(),
                  pnl_pct: float | None = None, switch_to: str = "",
                  facts: dict | None = None) -> dict:
    """The four parts of one holding's review row. The words say what the
    review concluded, never that a trade was made: a portfolio without the
    autopilot gets advice only, and a trade has its own words
    (explain.trade_parts). `facts`: see `sell_rule_clauses` and
    `note_sentence`; also autopilot, close, level, wait_sessions,
    broken_waiting (reasons that broke while the holding is too new),
    top_up_skipped, not_reviewed_plain."""
    facts = dict(facts or {})
    stop = facts.get("stop_price")
    wait = facts.get("wait_sessions") or 10
    unless = lambda: holding_wrong_if(stop=stop, level=facts.get("level"),  # noqa: E731
                                      wait_sessions=wait,
                                      exit_rule=facts.get("exit_rule") or "evidence")
    if "IDENTITY" in (notes or []):
        return parts(f"We kept {symbol} unchanged.", note_sentence("IDENTITY", facts),
                     "The review acts again once the price is confirmed as this holding's.",
                     "It needs to be sorted out by hand first.")
    nxt = TRADE_NEXT if facts.get("autopilot") else YOUR_CALL_NEXT
    if verdict in ("EXIT", "SWITCH"):
        did = (f"The review says to sell {symbol} and move the money into {switch_to}."
               if verdict == "SWITCH" and switch_to else f"The review says to sell {symbol}.")
        clauses = sell_rule_clauses(triggers, facts) or ["one of our selling rules was met"]
        return parts(did, end("Selling is advised because " + _join(clauses)),
                     ADVICE_NO_REBUY, nxt)
    if verdict == "TRIM":
        clauses = sell_rule_clauses(triggers, facts) or ["one of our selling rules was met"]
        return parts(f"The review says to sell part of {symbol} and keep the rest.",
                     end("Taking some profit is advised because " + _join(clauses)),
                     unless(),
                     nxt)
    if verdict == "ADD":
        why = add_why(facts).replace("We bought more because", "Buying more is supported because")
        if facts.get("top_up_skipped"):
            why = f"{why} No shares were bought, because {plain_skip(facts['top_up_skipped'])}."
        else:
            extra = notes_sentence(notes, facts)
            if extra:
                why = f"{why} {extra}"
        return parts(f"The review supports buying more of {symbol}.", why,
                     unless(),
                     nxt)
    if verdict == "HOLD":
        move = _move(pnl_pct)
        waiting = [broken_phrase(p) for p in facts.get("broken_waiting") or []]
        if waiting:
            body = (f"a reason to doubt it has appeared ({_join(waiting)}), but such reasons "
                    f"count only once it has been held {wait} trading days")
        elif "WAIT_FOR_LTCG" in (notes or []):
            # A profit-taking rule did fire; the tax note below says why it waits.
            body = "a reason to take some profit has appeared"
        else:
            body = "none of our selling rules has been met"
            if stop and facts.get("close") and facts["close"] > stop:
                body += f", and it is above the safety limit of about {price(stop)}"
        why = end(f"{move}; {body}" if move else body[:1].upper() + body[1:])
        extra = notes_sentence(notes, facts)
        if extra:
            why = f"{why} {extra}"
        return parts(f"We kept {symbol} unchanged.", why,
                     unless(),
                     REVIEW_NEXT)
    why = (end("It has not been reviewed: " + facts["not_reviewed_plain"])
           if facts.get("not_reviewed_plain") else "It had no review on this day.")
    return parts(f"{symbol} was not reviewed.", why,
                 "Nothing about it can change until it is reviewed.",
                 "It is reviewed once it is on the daily review list.")


def not_reviewed_plain(why: str) -> str:
    """FIX-028's "no daily review or forecast: <detail>" in plain words."""
    if re.search(r"cap\b|limit|full", why or "", re.IGNORECASE):
        m = re.search(r"\b(\d+)\b", why or "")
        limit = f" (limit {m.group(1)})" if m else ""
        return f"the daily review list is full{limit}, so it has no daily review or forecast yet"
    return "it has no daily review or forecast yet"


# -- The model's company sentence, checked ------------------------------------------

# Our voice, or an account of why we acted: code alone says those. "us" only in
# lower case, so "the US market" stays plain English.
_OUR_ACTION = re.compile(
    r"\b(?:[Ww]e|[Ww]e've|[Ww]e're|[Oo]ur|[Oo]urs|us)\b"
    r"|(?i:\bsold\s+(?:it\s+)?because\b|\bbought\s+(?:it\s+)?because\b"
    r"|\bstop[\s-]?loss\b|\bsafety\s+(?:limit|line)\b|\bthe\s+stop\b)")
_STOP_PERCENT = re.compile(
    r"(?i)(?:\d+(?:\.\d+)?\s*(?:%|per\s*cent|percent)[^.]{0,20}\bstop\b)"
    r"|(?:\bstop\b[^.]{0,30}?\d+(?:\.\d+)?\s*(?:%|percent|per\s*cent))")

# Numbers written as words. "one" is left out ("one of the largest"), as are
# thousand, lakh and crore, which the figure check reads as a figure's unit.
_NUMBER_WORDS = {
    "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90, "hundred": 100, "dozen": 12,
}
# A size said as a ratio ("doubled", "threefold") must be the facts' own word.
_RATIO_WORD = re.compile(r"(?i)\b(?:doubl\w*|tripl\w*|quadrupl\w*|halv\w*|half|twice|thrice"
                         r"|\w+fold)\b")


def ungrounded_words(text: str, source: str) -> list[str]:
    """The numbers `text` writes as words that `source` does not have, as the
    same word or as that number in digits."""
    digits = {value for value, unit, _ in figures(source) if not unit}
    have = source.lower()
    out = []
    for word, value in _NUMBER_WORDS.items():
        if (re.search(rf"(?i)\b{word}s?\b", text)
                and not re.search(rf"\b{word}s?\b", have) and value not in digits):
            out.append(word)
    out += [m for m in _RATIO_WORD.findall(text) if m.lower() not in have]
    return out


def check_company_sentence(text, source: str, where: str) -> str:
    """"" when `text` may be shown as the model's sentence about the company,
    else the first broken rule: one sentence of text, not too long, no banned
    word, no word of our own action or of why we acted (code says that), no
    stop given as a percentage, and every number, in digits or in words, one
    of `source`'s. It proves a number is the facts', not that the sentence
    uses it truthfully."""
    if not isinstance(text, str) or not text.strip():
        return f"{where} is missing"
    text = " ".join(text.split())
    if len(sentences(text)) > 1:
        return f"{where} is more than one sentence"
    if len(text) > MAX_SENTENCE_CHARS:
        return f"{where} is too long"
    bad = banned_in(text)
    if bad:
        return f"{where} uses a banned word: {bad[0]}"
    if _STOP_PERCENT.search(text):
        return f"{where} gives a stop as a percentage"
    if _OUR_ACTION.search(text):
        return f"{where} speaks of our action, which only code may say"
    missing = ungrounded(text, source) or ungrounded_words(text, source)
    if missing:
        return f"{where} has a figure no input has: {missing[0]}"
    return ""


def check_parts(value: dict) -> str:
    """"" when a four-part explanation keeps the contract: each part at most
    two sentences, none with a banned word; else the first broken rule."""
    for key in PARTS:
        text = value.get(key)
        if not isinstance(text, str) or not text.strip():
            return f"{key} is missing"
        if banned_in(text):
            return f"{key} uses a banned word: {banned_in(text)[0]}"
        if len(sentences(text)) > MAX_SENTENCES:
            return f"{key} has more than {MAX_SENTENCES} sentences"
    return ""
