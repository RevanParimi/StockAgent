"""
PR-007: the plain explanation of every trade, every holding row and the
review's buying, drafted once and stored beside the audit text.

**Display only.** The ledger's `reason` and `note`, the advice narrative, the
digest's own `reason` and `deployment` record are not changed, and no buy,
sell, size or grade reads anything written here.

**Who writes what** (core/portfolio/plain_words.py): code writes what was
done, the rule that fired and where the money went, from the records
themselves. For a **purchase**, one call to the reasoning tier
(`advisor.narrate_model`) may add one sentence about the company, taken from
the investment case (else the analysis known when it was bought), and one on
what would prove it wrong. The answer is checked (`check_company_sentence`);
one that breaks a rule is dropped whole and the template stands. A **sale**
makes no call: beside the rule that sold it, it quotes the case's own recorded
sentence, so a model can never supply a cause for a sale. The review's buying
and the holding rows are code only: their counts and rules come from the
records, and no check could prove a model's summary of them true.

**Once.** One row per trade (`txn:<txn_id>`) and per review
(`review:<date>`) in data/portfolio/<user>/explanations.jsonl; a re-run
drafts nothing that has a row, and no page view drafts anything. One user's
rows are read from that user's own folder only (FIX-005), and every input is
that user's records or public company facts.

**Never blocks.** Every trade is drafted on its own; a failure costs that
trade its model sentence at most. After `TIME_BUDGET_S` of a run, the rest
are templates.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Callable

from filelock import FileLock

from core.config import settings
from core.intelligence.rl.nse_calendar import IST, session_close_at
from core.portfolio import plain_words as words

logger = logging.getLogger(__name__)

CALLER = "plain_reasons"
CALL_TIMEOUT_S = 45
TIME_BUDGET_S = 180          # model drafting per user and run; past it, templates
MAX_TOKENS = 400
FACT_CHARS = 1600            # one input's text in the prompt
EXPLAINED_SIDES = ("BUY", "SELL")

SYSTEM_TRADE = (
    "You write for a reader who knows nothing about finance. You are given recorded facts "
    "about one Indian company. Use only those facts. Each answer is ONE short sentence "
    "about the company itself. Never mention buying, selling, an investor, \"we\" or "
    "\"our\", or why anyone traded: the app says that itself. Give no advice. Copy any "
    "number exactly as the facts write it, with its unit, or leave it out. No jargon, no "
    "codes in capitals, and never these words: envelope, ATR, regime, agent, data gate, "
    "reversion prior, conviction streak.")

# -- The store ---------------------------------------------------------------------------

def txn_key(txn_id: str) -> str:
    return f"txn:{txn_id}"


def review_key(day: str) -> str:
    return f"review:{day}"


class ExplanationStore:
    """One user's explanations, append-only; the newest row of a key wins."""

    def __init__(self, user_id: str, base_dir: str | None = None) -> None:
        self.user_id = user_id
        self._dir = Path(base_dir or settings.PORTFOLIO_DATA_DIR) / user_id
        self.path = self._dir / "explanations.jsonl"

    def load(self) -> dict[str, dict]:
        if not self.path.exists():
            return {}
        out: dict[str, dict] = {}
        for n, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                key = row["key"]
                if not isinstance(row["parts"], dict):
                    raise ValueError("no parts")
            except (ValueError, KeyError, TypeError) as exc:
                logger.warning("[explain] %s line %d unreadable: %s", self.path, n, exc)
                continue
            if row.get("user_id") == self.user_id:          # FIX-005, belt and braces
                out[key] = row
        return out

    def put(self, row: dict) -> dict:
        row = {**row, "user_id": self.user_id}
        self._dir.mkdir(parents=True, exist_ok=True)
        with FileLock(str(self.path) + ".lock", timeout=30):
            with self.path.open("a", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        return row


def shown(row: dict) -> dict:
    """What a screen is sent of a stored row: the four parts and who wrote
    the company sentence."""
    return {**row["parts"], "source": row.get("source", "template")}


# -- Seams (tests answer these; no test reaches the model or the network) ----------------

def _call_model(system: str, user: str) -> str:
    """One reasoning-tier JSON call, recorded like every other."""
    from services.clients.llm_client import JSON_MODE_EXTRA_BODY, get_llm_client, record_llm_call
    client = get_llm_client()
    if hasattr(client, "with_options"):
        client = client.with_options(max_retries=0)      # a slow provider costs one timeout
    model = settings.ADVISOR_NARRATE_MODEL
    t0 = time.time()
    try:
        resp = client.chat.completions.create(
            model=model, temperature=0.2, max_tokens=MAX_TOKENS, timeout=CALL_TIMEOUT_S,
            response_format={"type": "json_object"}, extra_body=JSON_MODE_EXTRA_BODY,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}])
    except Exception:
        record_llm_call(CALLER, model, 0, 0, int((time.time() - t0) * 1000), False)
        raise
    usage = getattr(resp, "usage", None)
    record_llm_call(CALLER, model, getattr(usage, "prompt_tokens", 0) or 0,
                    getattr(usage, "completion_tokens", 0) or 0,
                    int((time.time() - t0) * 1000), True)
    return resp.choices[0].message.content or ""


def _nifty_move(start: date, end_: date) -> float | None:
    """The NIFTY 50's move in percent from `start`'s close to `end_`'s, or
    None when it cannot be read."""
    try:
        from core.audit.benchmark import BenchmarkSeries
        series = BenchmarkSeries()
        a, b = series.close_on(start), series.close_on(end_)
        return (b / a - 1.0) * 100.0 if a > 0 else None
    except Exception as exc:
        logger.info("[explain] Nifty move %s..%s unavailable: %s", start, end_, exc)
        return None


def _company_inputs(symbol: str, as_of: datetime, ideas) -> object:
    """The analysis and the shelf idea known at `as_of`, which are all a
    trade with no case is told from. Not `cases.read_inputs`: its dossier read
    opens the prediction store, which creates a stock's folder."""
    from core.portfolio.cases import build_bundle
    records: list = []
    try:
        from services.data.stores.score_store import ScoreStore
        records = ScoreStore().get_records(symbol)
    except Exception as exc:
        logger.warning("[explain] analyses unread for %s: %s", symbol, exc)
    return build_bundle(symbol, as_of, records=records, ideas=ideas)


# -- What a holding's review row is told with ---------------------------------------------

@dataclass
class Context:
    """What the run knew about one holding before it traded."""
    holding: object | None = None          # the Holding before any trade of this run
    rec: object | None = None              # its AdviceRecord
    signals: object | None = None          # its AdvisorSignals
    evidence: dict | None = None           # ExitEvidence.model_dump()


def _per_share_dividends(holding) -> float:
    qty = float(getattr(holding, "adj_qty", 0.0) or 0.0)
    return float(getattr(holding, "dividends_received", 0.0) or 0.0) / qty if qty > 0 else 0.0


def holding_facts(ctx: Context, row: dict, portfolio, exit_rule: str) -> dict:
    """The facts a holding's row is worded with, each from the run's records."""
    rec, signals = ctx.rec, ctx.signals
    # The holding as the run left it (a top-up moves its average cost, so the
    # stop the next review reads), else as the review saw it.
    symbol = str(row.get("symbol") or "")
    holding = next((h for h in getattr(portfolio, "holdings", []) or []
                    if h.symbol == symbol), ctx.holding)
    manual = getattr(portfolio, "cash_deployable", None) is None
    facts: dict = {
        "manual": manual,
        "autopilot": bool(getattr(portfolio, "autopilot", False)) and not manual,
        "position_cap": float(settings.ADVISOR_MAX_POSITION_PCT),
        "sector_cap": float(settings.ADVISOR_MAX_SECTOR_PCT),
        "wait_sessions": int(settings.ADVISOR_MIN_HOLD_SESSIONS),
        "exit_rule": exit_rule,
    }
    if rec is not None:
        facts["close"] = rec.close
        facts["regime_unavailable"] = rec.regime_unavailable
        facts["bought_on_other"] = rec.bought_on_other
        if holding is not None and holding.adj_avg_price > 0:
            facts["stop_price"] = words.stop_price(holding.adj_avg_price, rec.stop_pct,
                                                   _per_share_dividends(holding))
    if signals is not None:
        peak = getattr(signals, "peak_close_since_entry", None)
        if peak and rec is not None:
            facts["peak_price"] = float(peak)
            facts["trail_price"] = round(float(peak) * (1 - rec.stop_pct / 100.0), 2)
        accuracy = getattr(signals, "direction_accuracy_7d", None)
        if accuracy is not None:
            facts["calls_right_pct"] = accuracy * 100.0
    evidence = ctx.evidence
    if evidence and rec is not None:
        broken = words.case_broken_parts(evidence, rec.close)
        facts["broken"] = broken
        level = float(evidence.get("invalidation_level") or 0.0)
        if level > 0 and exit_rule == "evidence":
            facts["level"] = level
        held = evidence.get("sessions_held")
        if (broken and exit_rule == "evidence" and "case_broken" not in rec.triggers
                and held is not None and held < settings.ADVISOR_MIN_HOLD_SESSIONS):
            facts["broken_waiting"] = broken
    if row.get("top_up_skipped"):
        facts["top_up_skipped"] = row["top_up_skipped"]
    if row.get("not_reviewed"):
        facts["not_reviewed_plain"] = words.not_reviewed_plain(row["not_reviewed"])
    return facts


def plain_rows(digest: dict, contexts: dict[str, Context], portfolio, exit_rule: str) -> None:
    """Add `plain` to each digest row: its four parts, templates only. A row
    that cannot be worded gets none, and the screen shows its audit reason."""
    for row in digest.get("holdings", []):
        symbol = row.get("symbol", "")
        try:
            ctx = contexts.get(symbol) or Context()
            rec = ctx.rec
            value = words.holding_parts(
                symbol, row.get("verdict", "NO_DATA"),
                triggers=getattr(rec, "triggers", ()), notes=row.get("notes") or (),
                pnl_pct=row.get("pnl_pct"), switch_to=row.get("switch_candidate", ""),
                facts=holding_facts(ctx, row, portfolio, exit_rule))
            problem = words.check_parts(value)
            if problem:
                logger.warning("[explain] %s row not worded: %s", symbol, problem)
                continue
            row["plain"] = {**value, "source": "template"}
        except Exception as exc:
            logger.warning("[explain] %s row not worded (non-fatal): %s", symbol, exc)


# -- The company's facts -------------------------------------------------------------------

def case_for(case_store, symbol: str, opened: str):
    """The newest version of the case of the holding of `symbol` bought on
    `opened`, else None: never the case of an earlier holding of the same
    stock, which was a different purchase for different reasons."""
    if case_store is None or not opened:
        return None
    found = [c for c in case_store.versions(symbol) if c.opened_on == opened]
    return max(found, key=lambda c: c.version, default=None)


@dataclass
class CompanyFacts:
    why_lines: list[str]            # why it was owned: the case, else the analysis
    risk_lines: list[str]           # what would prove that wrong
    template_why: str = ""          # the fallback sentence, "" when none is clean
    template_risk: str = ""
    case_version: int = 0
    event_refs: tuple = ()          # the case's event inputs ("E1", ...)
    # "case" (written when bought), "later" (a case written after the buy) or
    # "analysis" (no case: the analysis known when it was bought).
    origin: str = "case"

    def source(self) -> str:
        return "\n".join(self.why_lines + self.risk_lines)


_NO_THESIS = "No thesis was written"


def _plain_first(text: str) -> str:
    """The first sentence of analysis text when it may be shown as it is."""
    sentence = words.first_sentence(text)
    if not sentence or sentence.startswith(_NO_THESIS) or sentence.endswith("…"):
        return ""
    return words.clean(sentence)


def company_facts(case, bundle=None) -> CompanyFacts:
    """The company facts of one trade: the investment case's own words (the
    whole thesis is behind its pillars), else the inputs a case would have
    been written from (the analysis's full thesis, not the shelf's cut copy)."""
    why: list[str] = []
    risk: list[str] = []
    if case is not None:
        if case.one_line:
            why.append(f"In one line: {case.one_line}")
        for pillar in case.pillars:
            why.append(f"Reason: {pillar.claim}")
            why += [f"Evidence: {e.fact}" for e in pillar.evidence]
        if case.expectation.text:
            why.append(f"Expected: {case.expectation.text}")
        risk = [f"Would prove it wrong: {t}" for t in case.invalidation.business]
        template_why = _plain_first(case.one_line) or next(
            (s for s in (_plain_first(p.claim) for p in case.pillars) if s), "")
        template_risk = next((s for s in (_plain_first(t) for t in case.invalidation.business)
                              if s), "")
        return CompanyFacts([w[:FACT_CHARS] for w in why], [r[:FACT_CHARS] for r in risk],
                            template_why, template_risk, case.version,
                            tuple(e.ref for e in case.inputs if e.kind == "event"),
                            "later" if case.written == "after_purchase" else "case")
    if bundle is not None:
        text = bundle.text("A1") or bundle.text("S1") or ""
        thesis = next((ln.split(":", 1)[1].strip() for ln in text.splitlines()
                       if ln.startswith("thesis:")), "")
        if thesis and thesis != "(none written)":
            why.append(f"Analysis thesis: {thesis}"[:FACT_CHARS])
        why += [ln[:FACT_CHARS] for ln in text.splitlines() if ln.startswith("driver:")]
        risk = [ln[:FACT_CHARS] for ln in text.splitlines() if ln.startswith("risk:")]
        template_why = _plain_first(thesis)
        return CompanyFacts(why, risk, template_why,
                            _plain_first(risk[0].split(":", 1)[1]) if risk else "",
                            origin="analysis")
    return CompanyFacts([], [])


# -- A trade -------------------------------------------------------------------------------

def opened_on(ledger: list, symbol: str, upto) -> str:
    """The day the position that `upto` belongs to was opened: the first BUY
    since the symbol was last flat, in ledger order; "" when the ledger read
    holds none."""
    first = ""
    for txn in ledger:
        if txn.symbol == symbol and txn.side == "BUY" and not first:
            first = txn.date
        if txn.txn_id == upto.txn_id:
            return first
        if (txn.symbol == symbol and txn.side == "SELL"
                and (txn.holding_qty_after or 0.0) <= 1e-9):
            first = ""
    return first


def _pnl_clause(txn) -> str:
    if txn.pnl_pct is None:
        return ""
    gain = txn.realized_pnl
    if abs(gain) < 0.5:
        return ", about what was paid, before costs"
    word = "a profit" if gain > 0 else "a loss"
    return f", {word} of {words.money(abs(gain))} ({abs(txn.pnl_pct):.1f}%) before costs"


def _sell_facts(txn, ctx: Context) -> dict:
    rec = ctx.rec
    facts: dict = {}
    if rec is not None:
        facts["bought_on_other"] = rec.bought_on_other
        if txn.cost_basis:
            # The rupee price at which the stop fired: the trade's own cost
            # basis, with the dividends the sale carried.
            dividends = max(0.0, txn.realized_pnl - (txn.price - txn.cost_basis) * txn.qty)
            facts["stop_price"] = words.stop_price(
                txn.cost_basis, rec.stop_pct, dividends / txn.qty if txn.qty else 0.0)
    if ctx.signals is not None and rec is not None:
        peak = getattr(ctx.signals, "peak_close_since_entry", None)
        if peak:
            facts["peak_price"] = float(peak)
            facts["trail_price"] = round(float(peak) * (1 - rec.stop_pct / 100.0), 2)
    if ctx.evidence:
        facts["broken"] = words.case_broken_parts(ctx.evidence, txn.price)
    return facts


# How a sale introduces the reason it was bought: only a case written at the
# purchase may be called what was thought then.
_SALE_CASE_PREFIX = {
    "case": "When we bought it, the case was: ",
    "later": "The reason recorded after we bought it was: ",
    "analysis": "The analysis at the time we bought it said: ",
}


def _stop_after_add(txn, ctx: Context) -> float | None:
    """The stop price on the average cost the top-up leaves, when the run's
    holding and advice are known."""
    held, rec = ctx.holding, ctx.rec
    if held is None or rec is None or held.adj_qty + txn.qty <= 0:
        return None
    total = held.adj_qty + txn.qty
    average = (held.adj_avg_price * held.adj_qty + txn.price * txn.qty) / total
    return words.stop_price(average, rec.stop_pct,
                            float(held.dividends_received or 0.0) / total)


@dataclass
class Template:
    parts: dict            # the four parts, code's words only
    kind: str              # "sell" | "trim" | "deploy" | "switch" | "add"
    why_prefix: str        # how the company sentence is introduced after the rule
    facts: CompanyFacts


def trade_template(txn, *, ctx: Context, facts: CompanyFacts, case, siblings: list,
                   opened: str, nifty: float | None,
                   exit_rule: str = "evidence") -> Template:
    """The code's four parts for one autopilot trade. The first sentence of
    `why` names the rule that fired, from the trade's own records."""
    when = words.day(txn.date)
    qty = words.shares(txn.qty)
    at = words.price(txn.price)
    if txn.side == "SELL":
        sell = _sell_facts(txn, ctx)
        whole = (txn.holding_qty_after or 0.0) <= 1e-9
        did = (f"We sold all {qty} of {txn.symbol} at {at} (review of {when}){_pnl_clause(txn)}."
               if whole else
               f"We sold {qty} of {txn.symbol} at {at} (review of {when}){_pnl_clause(txn)}, "
               f"and kept {words.shares(txn.holding_qty_after)}.")
        if nifty is not None and opened:
            did += (f" Between {words.day(opened)} and {when} the Nifty 50 index moved "
                    f"{nifty:+.1f}%.")
        why = words.sell_why(txn.triggers, sell, part=not whole)
        proceeds = txn.value - (txn.costs.total if txn.costs else 0.0)
        switch_to = getattr(ctx.rec, "switch_candidate", "") if txn.verdict == "SWITCH" else ""
        from core.portfolio.autopilot import switch_skip_reason
        skipped = switch_skip_reason(txn.note)
        if txn.verdict == "SWITCH" and not switch_to:
            # A trade with no advice record: read the destination off its rows.
            leg = next((t for t in siblings if t.side == "BUY"
                        and t.advice_ref == txn.advice_ref), None)
            switch_to = leg.symbol if leg else skipped.split(":", 1)[0].strip()
        leg = next((t for t in siblings if t.side == "BUY" and t.advice_ref == txn.advice_ref
                    and t.symbol == switch_to), None)
        spent = (leg.value + (leg.costs.total if leg.costs else 0.0)) if leg else None
        nxt = words.sale_next(proceeds=proceeds, switch_to=switch_to, bought=leg is not None,
                              spent=spent, skip_reason=skipped)
        if whole:
            wrong = words.NO_REBUY
        else:
            wrong = words.rest_wrong_if(sell.get("stop_price"))
        return Template(words.parts(did, why, wrong, nxt), "sell" if whole else "trim",
                        _SALE_CASE_PREFIX[facts.origin], facts)

    value = words.money(txn.value)
    wait = int(settings.ADVISOR_MIN_HOLD_SESSIONS)
    stop = level = None
    if case is not None:
        stop = case.invalidation.stop_price
        level = case.invalidation.price
    nxt = words.REVIEW_NEXT
    if case is not None and case.expectation.target:
        horizon = (f" within about {case.expectation.horizon_months} months"
                   if case.expectation.horizon_months else "")
        nxt += (f" The research expects about {words.price(case.expectation.target)}{horizon}: "
                "a view, not a promise.")
    if txn.verdict == "ADD":
        add_facts: dict = {}
        accuracy = getattr(ctx.signals, "direction_accuracy_7d", None)
        if accuracy is not None:
            add_facts["calls_right_pct"] = accuracy * 100.0
        n = int(round(txn.qty))
        did = (f"We bought {n:,} more share{'s' if n != 1 else ''} of {txn.symbol} at {at} "
               f"(review of {when}), and now hold {words.shares(txn.holding_qty_after)}.")
        return Template(words.parts(did, words.add_why(add_facts),
                                    words.holding_wrong_if(stop=_stop_after_add(txn, ctx),
                                                           level=level,
                                                           wait_sessions=wait, traded=True,
                                                           exit_rule=exit_rule), nxt),
                        "add", "Why we own it: ", facts)
    did = f"We bought {qty} of {txn.symbol} at {at} (review of {when}), about {value}."
    cheaper = "below entry band" in (txn.note or "")
    wrong = words.holding_wrong_if(stop=stop, level=level, wait_sessions=wait,
                                   traded=True, exit_rule=exit_rule)
    if txn.verdict == "SWITCH":
        origin = (txn.advice_ref.split("|") + ["", ""])[1]
        # The buy leg's triggers are the SOLD stock's: never this buy's reason.
        why = words.switch_in_why(origin or "another stock", cheaper_than_planned=cheaper)
        return Template(words.parts(did, why, wrong, nxt), "switch", "The case: ", facts)
    return Template(words.parts(did, words.deploy_why(cheaper_than_planned=cheaper), wrong, nxt),
                    "deploy", "The case: ", facts)


def trade_prompt(txn, facts: CompanyFacts, *, needs_risk: bool) -> str:
    keys = ('{"reason": "<one sentence: what about the company was the reason to own it>"'
            + (', "risk": "<one sentence: what in the business would show that reason is '
               'wrong>"}' if needs_risk else "}"))
    lines = [f"Company: {txn.symbol}", "", "Why it was owned:", *facts.why_lines]
    if needs_risk and facts.risk_lines:
        lines += ["", "What would prove that wrong:", *facts.risk_lines]
    return "\n".join(lines) + f"\n\nAnswer with JSON: {keys}"


def _answer(raw: str) -> dict:
    text = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.DOTALL).strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("the answer is not a JSON object")
    return data


def draft_company(txn, facts: CompanyFacts, *, needs_risk: bool,
                  call: Callable[[str, str], str]) -> tuple[dict, str]:
    """({"reason", "risk"}, "") when the model's whole answer passes the
    checks; ({}, why not) otherwise."""
    try:
        data = _answer(call(SYSTEM_TRADE, trade_prompt(txn, facts, needs_risk=needs_risk)))
    except (ValueError, TypeError) as exc:
        return {}, f"unreadable answer: {exc}"
    except Exception as exc:
        return {}, f"model call failed: {exc}"
    source = facts.source()
    keys = ["reason"] + (["risk"] if needs_risk and facts.risk_lines else [])
    for key in keys:
        problem = words.check_company_sentence(data.get(key), source, key)
        if problem:
            return {}, problem
    return {k: " ".join(str(data[k]).split()) for k in keys}, ""


def compose(template: Template, sentences: dict) -> dict:
    """The stored four parts: code's words, then at most one company sentence
    in `why` and, for a buy, one in `wrong_if`. `sentences` is the model's
    checked answer or the template's own."""
    parts = dict(template.parts)
    reason = sentences.get("reason", "")
    if reason:
        parts["why"] = f"{parts['why']} {template.why_prefix}{words.end(reason)}"
    risk = sentences.get("risk", "")
    if risk and template.kind in ("deploy", "switch", "add"):
        parts["wrong_if"] = f"{parts['wrong_if']} A warning sign in the business: {words.end(risk)}"
    return parts


def _fallback_sentences(facts: CompanyFacts) -> dict:
    return {k: v for k, v in (("reason", facts.template_why), ("risk", facts.template_risk))
            if v}


def explain_trade(txn, *, ctx: Context, case, bundle, siblings: list, opened: str,
                  nifty: float | None, call: Callable[[str, str], str] | None,
                  exit_rule: str = "evidence") -> dict:
    """One trade's stored row. `call` None means templates only."""
    facts = company_facts(case, bundle)
    template = trade_template(txn, ctx=ctx, facts=facts, case=case, siblings=siblings,
                              opened=opened, nifty=nifty, exit_rule=exit_rule)
    sentences, why_not, source = {}, "", "template"
    needs_risk = template.kind in ("deploy", "switch", "add")
    if txn.side == "SELL":
        # The card's hard review: no model supplies a cause for a sale.
        why_not = "a sale quotes the recorded case; no model call"
    elif call is None:
        why_not = "model drafting off or out of time"
    elif not facts.why_lines:
        why_not = "no company facts recorded"
    else:
        sentences, why_not = draft_company(txn, facts, needs_risk=needs_risk, call=call)
        if sentences:
            source = "model"
    parts = compose(template, sentences or _fallback_sentences(facts))
    if words.check_parts(parts):                     # the template's own words stand alone
        logger.warning("[explain] %s %s: %s; company sentence left out", txn.side, txn.symbol,
                       words.check_parts(parts))
        parts, source = dict(template.parts), "template"
    return {
        "key": txn_key(txn.txn_id), "kind": "trade", "txn_id": txn.txn_id, "date": txn.date,
        "symbol": txn.symbol, "side": txn.side, "advice_ref": txn.advice_ref,
        "parts": parts, "source": source, "fallback_reason": why_not,
        "model": settings.ADVISOR_NARRATE_MODEL if source == "model" else "",
        "case_version": facts.case_version, "event_refs": list(facts.event_refs),
        "created_at": datetime.now(IST).isoformat(),
    }


# -- The review's buying -------------------------------------------------------------------

# deployment.py's outcome codes as plain clauses: (for one idea, for several).
_OUTCOME_CLAUSE = {
    "band": ("was priced above the range we planned to pay",
             "were priced above the range we planned to pay"),
    "invalidated": ("had fallen to where its research would no longer hold",
                    "had fallen to where their research would no longer hold"),
    "sold": ("had been sold recently and waits for new research",
             "had been sold recently and wait for new research"),
    "verdict": ("no longer had research that supports a buy",
                "no longer had research that supports a buy"),
    "gate": ("had data we could not fully check", "had data we could not fully check"),
    "price": ("had no closing price for the day", "had no closing price for the day"),
    "before_dive": ("had no price newer than its research",
                    "had no price newer than their research"),
    "surveillance": ("was not cleared by the exchange's watch list",
                     "were not cleared by the exchange's watch list"),
    "size": ("could not take even one share within our limits on money",
             "could not take even one share within our limits on money"),
    "other_company": ("had research about a different company",
                      "had research about a different company"),
    "held": ("was already owned", "were already owned"),
    "ledger": ("needs its record checked", "need their records checked"),
    "waiting": ("passed every check but has to wait for another day",
                "passed every check but have to wait for another day"),
}
_ABOVE = re.compile(r"^\s*([\d.]+)% above entry band")


def held_back_clause(ideas: list[dict]) -> str:
    """"3 ideas were priced above the range we planned to pay (by 4.0% to
    12.1%), and 1 idea was already owned."; "" when every idea was bought."""
    counts: dict[str, int] = {}
    above: list[float] = []
    for idea in ideas:
        code = idea.get("outcome")
        if code == "bought" or code not in _OUTCOME_CLAUSE:
            continue
        counts[code] = counts.get(code, 0) + 1
        m = _ABOVE.match(str(idea.get("why") or "")) if code == "band" else None
        if m:
            above.append(float(m.group(1)))
    clauses = []
    for code, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        one, many = _OUTCOME_CLAUSE[code]
        text = f"1 idea {one}" if n == 1 else f"{n} ideas {many}"
        if code == "band" and above:
            low, high = f"{min(above):.1f}", f"{max(above):.1f}"
            text += f" (by {low}%)" if low == high else f" (by {low}% to {high}%)"
        clauses.append(text)
    if not clauses:
        return ""
    if len(clauses) == 1:
        return f"{clauses[0]}."
    return f"{', '.join(clauses[:-1])}, and {clauses[-1]}."


_IDEAS_WRONG = ("We buy more once a researched idea is priced within the range we planned to "
                "pay and passes every check.")
_MARKET_WRONG = ("We buy again once the market's condition allows it and an idea passes every "
                 "check.")
# The rule that stopped the day's buying: (a mark in deployment.stop_reason's
# or target's own words, the lead, what would change it). In test order: "regime"
# is in several reasons, so the more exact marks come first.
_STOPS = (
    ("target reached", "We had reached the share of money we wanted in stocks.",
     "We buy more once the share in stocks is below the goal again."),
    ("the maximum of", "We already hold the most stocks we allow.",
     "We buy a new stock only after we sell one we hold."),
    ("the daily limit of", "We buy at most {n} new stocks a day.",
     "Ideas still waiting can be bought at a later review if they still pass every check."),
    ("cash held on purpose", "The market's condition calls for holding cash, so no new stock "
     "was bought.", _MARKET_WRONG),
    ("no target set", "No goal is set for the market's current condition, so no new stock was "
     "bought.", _MARKET_WRONG),
    ("regime", "We could not read the market's condition for the day, so no new stock was "
     "bought.", _MARKET_WRONG),
    ("cash floor", "No money was free beyond the cash we keep aside.",
     "We buy again once there is money beyond the cash we keep aside."),
    ("no further qualifying idea", "No other idea passed all our checks.", _IDEAS_WRONG),
)


def _stop(dep: dict) -> tuple[str, str]:
    """(the lead, what would change it) from the record's first reason."""
    first = str((dep.get("reasons") or [""])[0])
    for mark, lead, wrong in _STOPS:
        if mark in first:
            limit = re.search(r"the daily limit of (\d+)", first)
            return lead.format(n=limit.group(1) if limit else "a few"), wrong
    return "The buying stopped under our limits.", _IDEAS_WRONG


def review_parts(dep: dict, day: str) -> dict:
    """The four parts of one day's deployment record, code only."""
    when = words.day(dep.get("date") or day)
    bought = list(dep.get("bought") or [])
    if dep.get("error"):
        return words.parts(f"At the review of {when} nothing new was bought.",
                           "The buying step did not finish.",
                           "Buying resumes once the step runs to the end again.",
                           "The next review follows the next trading day's close.")
    did = (f"At the review of {when} we bought {len(bought)} new "
           f"stock{'s' if len(bought) != 1 else ''}: {', '.join(bought)}."
           if bought else f"At the review of {when} we bought nothing new.")
    lead, wrong = _stop(dep)
    held_back = held_back_clause(dep.get("ideas") or [])
    standing = []
    if isinstance(dep.get("holdings_after"), (int, float)) and dep.get("target_holdings"):
        standing.append(f"we hold {dep['holdings_after']} of the {dep['target_holdings']} "
                        "holdings we aim for")
    # No goal is in force on a day nothing may open (target_pct 0): none is told.
    if isinstance(dep.get("invested_after_pct"), (int, float)) and (dep.get("target_pct") or 0) > 0:
        standing.append(f"{dep['invested_after_pct']:.1f}% of the money is in stocks against "
                        f"a goal of {dep['target_pct']:.1f}%")
    nxt = (words.end(("Now " + ", and ".join(standing)).strip()) + " " if standing else "")
    nxt += ("We wait rather than chase."
            if not bought and any(i.get("outcome") == "band" for i in dep.get("ideas") or [])
            else "The next review follows the next trading day's close.")
    return words.parts(did, f"{lead} {held_back}".strip(), wrong, nxt)


def explain_review(dep: dict, day: str) -> dict:
    return {
        "key": review_key(day), "kind": "review", "date": day,
        "parts": review_parts(dep, day), "source": "template", "fallback_reason": "",
        "model": "", "created_at": datetime.now(IST).isoformat(),
    }


# -- A run ----------------------------------------------------------------------------------

def explain_run(user_id: str, review_date: date, *, base_dir: str, txns: list,
                contexts: dict[str, Context], digest: dict | None, ledger: list | None = None,
                ideas: list | None = None, case_store=None,
                clock: Callable[[], float] = time.monotonic,
                budget_s: float = TIME_BUDGET_S, model: bool = True,
                siblings: list | None = None,
                exit_rule: str = "evidence") -> dict[str, dict]:
    """Draft and store the explanations of a run's autopilot trades and of the
    day's buying. Returns {key: row} for each, stored before or now. Never
    raises for one trade. `siblings` is the run's trades when `txns` is only
    some of them (the backfill)."""
    store = ExplanationStore(user_id, base_dir)
    have = store.load()
    started = clock()
    out: dict[str, dict] = {}

    def caller():
        if not model or clock() - started >= budget_s:
            return None
        return _call_model

    for txn in txns:
        if txn.side not in EXPLAINED_SIDES or txn.source != "autopilot":
            continue
        key = txn_key(txn.txn_id)
        if key in have:
            out[key] = have[key]
            continue
        try:
            # A SWITCH's buy leg carries the SOLD stock's advice: it is
            # worded from its own rows, never from that holding's context.
            ctx = (Context() if txn.verdict == "SWITCH" and txn.side == "BUY"
                   else contexts.get(txn.symbol) or Context())
            # The purchase the trade belongs to: the holding's own buy day,
            # else the ledger's. A new position's is the trade's day.
            opened = (str(getattr(ctx.holding, "buy_date", "") or "")[:10]
                      or opened_on(ledger or txns, txn.symbol, txn))
            try:
                case = case_for(case_store, txn.symbol, opened)
            except Exception as exc:
                logger.warning("[explain] case unread for %s: %s", txn.symbol, exc)
                case = None
            bundle = None
            if case is None and opened:
                try:
                    # What was known when it was bought: a later analysis (the
                    # one that turned to sell it, say) is never "why we bought".
                    bundle = _company_inputs(
                        txn.symbol, session_close_at(date.fromisoformat(opened)), ideas or [])
                except Exception as exc:
                    logger.warning("[explain] inputs unread for %s: %s", txn.symbol, exc)
            nifty = None
            if txn.side == "SELL" and opened and opened < txn.date:
                nifty = _nifty_move(date.fromisoformat(opened), date.fromisoformat(txn.date))
            row = explain_trade(txn, ctx=ctx, case=case, bundle=bundle,
                                siblings=siblings if siblings is not None else txns,
                                opened=opened, nifty=nifty, call=caller(),
                                exit_rule=exit_rule)
            out[key] = store.put(row)
        except Exception as exc:
            logger.warning("[explain] %s %s not explained (non-fatal): %s", txn.side,
                           txn.symbol, exc)
    dep = (digest or {}).get("deployment")
    if dep:
        day = review_date.isoformat()
        key = review_key(day)
        if key in have:
            out[key] = have[key]
        else:
            try:
                out[key] = store.put(explain_review(dep, day))
            except Exception as exc:
                logger.warning("[explain] review of %s not explained (non-fatal): %s", day, exc)
    return out


def use_trade_words(digest: dict, drafted: dict[str, dict]) -> bool:
    """A row whose stock traded this run says what the trade said, so the
    digest and the brief say the same as the alert and the history: the sale
    for a trim, the purchase for a top-up or for a stock bought today (a row
    with no review of its own yet). True when a row changed."""
    changed = False
    by_side = {(r.get("symbol"), r.get("side")): r for r in drafted.values()
               if r.get("kind") == "trade"}
    for row in digest.get("holdings", []):
        verdict = row.get("verdict")
        side = ("SELL" if verdict in ("TRIM", "EXIT", "SWITCH") else
                "BUY" if verdict == "ADD" and not row.get("top_up_skipped") else
                "BUY" if verdict == "NO_DATA" and not row.get("not_reviewed") else "")
        trade = by_side.get((row.get("symbol"), side)) if side else None
        if trade and "plain" in row:
            row["plain"] = shown(trade)
            changed = True
    return changed


# -- What the screens are sent ---------------------------------------------------------------

def attach_transactions(rows: list[dict], explanations: dict[str, dict]) -> None:
    """Add `plain` to each transaction row that has one."""
    for row in rows:
        found = explanations.get(txn_key(str(row.get("txn_id") or "")))
        if found:
            row["plain"] = shown(found)
