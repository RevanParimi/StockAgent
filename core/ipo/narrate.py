"""PI Prospect P3 — the narrator (plan 2026-09-21 / IPO-4b).

The explainer: the `IPO-5a` content — who the promoters are, the revenue and
profit trajectory, valuation against peers, what the proceeds are for, who
took anchor, the book by category, the concerns the documents raised — as a
few paragraphs of prose. It is written from STRUCTURED FINDINGS ONLY, and
the LLM narrates them; it never decides.

Three guards make that a property of the code path rather than of the
model's obedience:

  1. The verdict is never passed in. `narration_facts()` is built from the
     research (`IpoSubstance`), the scored book (`HypeReading.features`) and
     the NSE row. The lean, the band, the quadrant and the two indices are
     not in the block, so the model cannot quote them; the prompt's
     prohibition is belt over braces.
  2. Every NUMBER in the prose must appear in the facts. A model that
     computes a growth rate, a ratio or a total has produced a figure with no
     source, and the whole note is rejected — provenance travels with every
     claim, and a narration is the one place a number could be born without
     one. Rounding is tolerated; arithmetic is not.
  3. A fixed vocabulary of verdict and advice words rejects the note, unless
     the word is itself in the facts (a red flag that says "sell" is the
     document's word, not the model's). The same list carries the arithmetic
     stated in WORDS — "doubled", "halved" — which guard 2 cannot see
     because it produces no digits, and which is a computed claim all the
     same.

A rejected or failed narration falls back to `render_template()`, a
deterministic paragraph from the same facts, so a narration is never missing
because a model was. Both routes get the same code-appended "Sources:" line
and the research-view framing — the sources are never at the model's mercy,
and the model never sees a URL at all (the block it reads carries source
COUNTS; a URL slug like `price-band-set-at-rs-140-148` is not a sourced
claim, and stripping the URLs is what keeps it from becoming one).

The narration is stored beside the verdict row and is excluded from the
store's dedup rule (a re-worded note is not a new reading). The deep dive
narrates only when a row will actually be written, and reuses the previous
row's note when the facts digest has not moved — so an issue costs at most
two notes: one at T-1 and one when the book turns final, which is a change
the note itself states. The evenings after that dedup to nothing.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from typing import Any, Mapping
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from core.ipo.extract import IpoSubstance, Sourced
from core.ipo.hype import HypeReading
from core.ipo.substance import SubstanceReading

logger = logging.getLogger(__name__)

_CALLER = "ipo_narrate"

FRAMING = "Research view from sourced documents and official exchange figures — not advice."

# The model's own vocabulary — words that can only come from the verdict or
# from an opinion, never from a sourced fact. Word-boundaried, case-blind.
FORBIDDEN_TERMS: tuple[str, ...] = (
    "quiet compounder", "genuine star", "froth", "frothy", "quadrant", "verdict", "lean",
    "hype index", "substance index", "hit-rate", "hit rate",
    "subscribe", "apply for", "should apply", "worth applying", "avoid", "buy", "sell",
    "recommend", "recommended", "recommendation",
    "listing gain", "listing gains", "listing pop", "pop", "expected return", "expected returns",
    "upside", "downside", "target price", "price target",
    "attractive", "expensive", "cheap", "compelling", "risky", "overvalued", "undervalued",
    # Arithmetic in words: a computation with no digits for the number guard
    # to catch, and no source behind it either.
    "doubled", "tripled", "quadrupled", "halved", "times higher", "times lower",
    "fold increase", "fold rise",
)
_FORBIDDEN_RE = re.compile(r"\b(" + "|".join(re.escape(t) for t in FORBIDDEN_TERMS) + r")\b",
                           re.IGNORECASE)
_NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
_BOOK_ROWS: tuple[tuple[str, str], ...] = (
    ("total_x", "overall"), ("qib_x", "QIB"), ("fii_x", "of which FIIs"),
    ("dom_fi_x", "of which domestic FIs"), ("mutual_fund_x", "of which mutual funds"),
    ("nii_x", "NII"), ("retail_x", "retail"),
)


class IpoNarration(BaseModel):
    text: str = ""                       # the note, sources line and framing included
    source: str = ""                     # "llm" | "template" | "" (nothing to narrate)
    model: str = ""                      # the model asked, even when it was rejected
    urls: list[str] = Field(default_factory=list)   # every source behind the facts
    facts_digest: str = ""               # sha256[:16] of the facts — reuse key
    fallback_reason: str = ""            # why the template was used, if it was


# ─────────────────────────── the facts ────────────────────────────────────

def _sourced(s: Sourced | None) -> dict[str, Any] | None:
    if s is None or s.value is None or not s.source_url:
        return None
    return {"value": s.value, "status": s.status or "reported",
            "sources": list(s.sources or [s.source_url])}


def _f(x: Any) -> float | None:
    try:
        return None if x is None else float(x)
    except (TypeError, ValueError):
        return None


def _book_status(state: str) -> str:
    if state in ("closed", "listed"):
        return "closed — final figures"
    if state == "open":
        return "open — interim figures, the book was still taking bids"
    return state or "unknown"


def narration_facts(research: IpoSubstance | None, hype: HypeReading | None,
                    substance: SubstanceReading | None, row: Mapping[str, Any] | None, *,
                    symbol: str, close_date: str, state: str = "") -> dict[str, Any]:
    """The structured findings block. Every number in it has a source: the
    research fields carry their URLs, the issue and book fields are the
    exchange's own. Nothing from the verdict is here, by construction.

    `substance` is accepted for its `captured` block (the sub-row multiples
    the ledger carries) but nothing scored — no feature, component or index —
    is read off either reading.
    """
    research = research or IpoSubstance()
    row = row or {}
    feats = (hype.features if hype else {}) or {}
    captured = (substance.captured if substance else {}) or {}
    facts: dict[str, Any] = {
        "company": str(row.get("company") or research.company or symbol),
        "symbol": symbol,
        "close_date": close_date,
    }

    issue: dict[str, Any] = {}
    for key in ("issue_start", "issue_end"):
        if row.get(key):
            issue[key] = str(row[key])
    for key in ("issue_price", "issue_size_cr"):
        if _f(row.get(key)) is not None:
            issue[key] = _f(row[key])
    ofs = _f(row.get("ofs_share"))
    if ofs is None:
        ofs = _f(captured.get("ofs_share"))
    if ofs is not None:
        issue["ofs_share_of_issue"] = ofs
    if issue:
        issue["source"] = "NSE"
        facts["issue"] = issue

    for field in ("revenue_cr", "pat_cr"):
        series = [{"fy": s.as_of, **d} for s in getattr(research, field)
                  if (d := _sourced(s)) is not None]
        if series:
            facts[field] = series
    for field in ("ebitda_margin_pct", "issue_pe"):
        src = research.ebitda_margin if field == "ebitda_margin_pct" else research.issue_pe
        if (d := _sourced(src)) is not None:
            facts[field] = d
    peers = [{"name": p.label, **d} for p in research.peer_pe
             if p.label and (d := _sourced(p)) is not None]
    if peers:
        facts["peer_pe"] = peers
    for field in ("promoter", "parent_track"):
        if (d := _sourced(getattr(research, field))) is not None:
            facts[field] = {"text": d["value"], "status": d["status"], "sources": d["sources"]}
    for field in ("anchor_names", "use_of_proceeds", "red_flags"):
        items = [{"text": d["value"], "sources": d["sources"]}
                 for s in getattr(research, field) if (d := _sourced(s)) is not None]
        if items:
            facts[field] = items

    book: dict[str, Any] = {}
    for key, _label in _BOOK_ROWS:
        val = _f(feats.get(key))
        if val is None and key in ("fii_x", "dom_fi_x", "mutual_fund_x"):
            val = _f(captured.get(key))
        if val is not None:
            book[key] = val
    if _f(feats.get("cutoff_share")) is not None:
        book["retail_bids_at_cutoff_share"] = _f(feats["cutoff_share"])
    if book:
        book["as_of"] = str((hype.as_of if hype else "") or "")[:10]
        book["status"] = _book_status(state or (hype.state if hype else ""))
        book["source"] = "NSE"
        facts["subscription"] = book
    gmp = _f(feats.get("gmp_pct"))
    if gmp is not None:
        facts["grey_market_premium_pct"] = {"value": gmp,
                                           "note": "unofficial, from grey-market trackers"}
    return facts


_IDENTITY = frozenset({"company", "symbol", "close_date"})


def has_findings(facts: Mapping[str, Any]) -> bool:
    """False when the block holds nothing but the issue's name — a note about
    nothing is not written, and the verdict row carries an empty narration."""
    return any(k not in _IDENTITY and k != "issue" for k in facts)


def facts_digest(facts: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(facts, sort_keys=True, default=str).encode("utf-8")
                          ).hexdigest()[:16]


def facts_urls(facts: Mapping[str, Any]) -> list[str]:
    """Every source URL in the block, first appearance first, no repeats."""
    out: list[str] = []
    seen: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "sources" and isinstance(v, list):
                    for u in v:
                        if isinstance(u, str) and u and u not in seen:
                            seen.add(u)
                            out.append(u)
                else:
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(facts)
    return out


def _domain(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def domains_of(urls: list[str]) -> list[str]:
    out: list[str] = []
    for u in urls:
        d = _domain(u)
        if d and d not in out:
            out.append(d)
    return out


def for_model(facts: Mapping[str, Any]) -> dict[str, Any]:
    """The block the model reads: identical, with every `sources` list
    replaced by its count. The model needs to know one site said it or three
    did; it does not need the URLs, and a URL is the one place a number with
    no sourced claim behind it could enter the prompt."""
    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            return {k: (len(v) if k == "sources" and isinstance(v, list) else walk(v))
                    for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node
    return walk(facts)


# ─────────────────────────── the guards ───────────────────────────────────

def _numbers_in(text: str) -> list[float]:
    out: list[float] = []
    for tok in _NUM_RE.findall(text or ""):
        try:
            out.append(float(tok.replace(",", "")))
        except ValueError:
            continue
    return out


def _forms(v: float) -> set[float]:
    """The ways a faithful writer may render one figure: as given, rounded
    to 2/1/0 decimals, and — for a share in 0..1 — as a percentage. The
    prose regex reads no sign, so a loss of -12.5 must admit 12.5."""
    v = abs(v)
    forms = {v, round(v, 2), round(v, 1), float(round(v))}
    if 0 < v <= 1:
        pct = 100.0 * v
        forms |= {pct, round(pct, 2), round(pct, 1), float(round(pct))}
    return forms


def allowed_numbers(facts: Mapping[str, Any]) -> set[float]:
    """Every number a faithful note may contain: each numeric fact in its
    rounded forms, each number that appears inside a text fact (a red flag
    quoting Rs 400 crore of debt), each fiscal year with its two-digit form,
    the parts of each date, and the length of each list (\"three years\",
    \"5 anchors\")."""
    out: set[float] = set()

    def walk(node: Any) -> None:
        if isinstance(node, bool):
            return
        if isinstance(node, (int, float)):
            out.update(_forms(float(node)))
        elif isinstance(node, str):
            for n in _numbers_in(node):
                out.add(n)
                if 1990 <= n <= 2100 and n == int(n):
                    out.add(float(int(n) % 100))
        elif isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            out.add(float(len(node)))
            for v in node:
                walk(v)
    walk(for_model(facts))
    return out


def check_narration(text: str, facts: Mapping[str, Any]) -> str:
    """'' when the prose is admissible, else the reason it is not.

    Numbers: every number in the prose must be one of `allowed_numbers`
    (to two decimals). Vocabulary: a forbidden term rejects the note unless
    the facts' own text contains it — then it is the document's word."""
    allowed = allowed_numbers(facts)
    for n in _numbers_in(text):
        if not any(abs(n - a) < 0.005 for a in allowed):
            return f"number not in facts: {n:g}"
    facts_text = json.dumps(for_model(facts), ensure_ascii=False).lower()
    for m in _FORBIDDEN_RE.finditer(text or ""):
        term = m.group(1).lower()
        if not re.search(r"\b" + re.escape(term) + r"\b", facts_text):
            return f"forbidden term: {term!r}"
    return ""


def _to_last_sentence(text: str) -> str:
    """A truncated note cut back to its last complete sentence."""
    cut = max(text.rfind(". "), text.rfind(".\n"), text.rfind("."), text.rfind("!"), text.rfind("?"))
    return text[:cut + 1].strip() if cut > 0 else ""


# ─────────────────────────── the template ─────────────────────────────────

def _fmt(v: float) -> str:
    if abs(v) >= 100:
        s = f"{v:,.0f}"
    elif abs(v) >= 10:
        s = f"{v:,.1f}"
    else:
        s = f"{v:,.2f}"
    return s.rstrip("0").rstrip(".") if "." in s else s


def _pct(v: float) -> str:
    return _fmt(100.0 * v) + "%"


def _status_note(items: list[dict[str, Any]]) -> str:
    return "sources agree" if all(i.get("status") == "corroborated" for i in items) else "one source"


def render_template(facts: Mapping[str, Any]) -> str:
    """The deterministic fallback: the same facts as plain sentences. Every
    figure is rendered by `_fmt`, so the note passes `check_narration` by
    construction — a test holds that line."""
    paras: list[str] = []
    issue = facts.get("issue") or {}
    head = f"{facts.get('company', '')} ({facts.get('symbol', '')}) — issue closes {facts.get('close_date', '')}."
    bits = []
    if "issue_price" in issue:
        bits.append(f"Issue price Rs {_fmt(issue['issue_price'])}")
    if "issue_size_cr" in issue:
        bits.append(f"issue size Rs {_fmt(issue['issue_size_cr'])} cr")
    if "ofs_share_of_issue" in issue:
        bits.append(f"offer for sale {_pct(issue['ofs_share_of_issue'])} of the issue")
    if bits:
        head += " " + "; ".join(bits) + " (NSE)."
    paras.append(head)

    who = []
    if "promoter" in facts:
        who.append(f"Promoters: {facts['promoter']['text']} ({_status_note([facts['promoter']])}).")
    if "parent_track" in facts:
        who.append(f"Group record: {facts['parent_track']['text']} ({_status_note([facts['parent_track']])}).")
    if who:
        paras.append(" ".join(who))

    fin = []
    for field, label in (("revenue_cr", "Revenue from operations"), ("pat_cr", "Profit after tax")):
        if field in facts:
            run = ", ".join(f"{s['fy']} Rs {_fmt(s['value'])} cr" for s in facts[field])
            fin.append(f"{label}: {run} ({_status_note(facts[field])}).")
    if "ebitda_margin_pct" in facts:
        fin.append(f"EBITDA margin {_fmt(facts['ebitda_margin_pct']['value'])}% "
                   f"({_status_note([facts['ebitda_margin_pct']])}).")
    if fin:
        paras.append(" ".join(fin))

    val = []
    if "issue_pe" in facts:
        val.append(f"Issue P/E {_fmt(facts['issue_pe']['value'])} ({_status_note([facts['issue_pe']])}).")
    if "peer_pe" in facts:
        val.append("Listed peers' P/E: " + ", ".join(
            f"{p['name']} {_fmt(p['value'])}" for p in facts["peer_pe"]) + ".")
    if val:
        paras.append(" ".join(val))

    use = []
    if "use_of_proceeds" in facts:
        use.append("Stated use of proceeds: " + "; ".join(i["text"] for i in facts["use_of_proceeds"]) + ".")
    if "anchor_names" in facts:
        use.append("Anchor investors named: " + ", ".join(i["text"] for i in facts["anchor_names"]) + ".")
    if use:
        paras.append(" ".join(use))

    book = facts.get("subscription") or {}
    if book:
        rows = [f"{label} {_fmt(book[key])}x" for key, label in _BOOK_ROWS if key in book]
        line = f"Subscription (NSE, as of {book.get('as_of', '')}, book {book.get('status', '')}): " \
               + "; ".join(rows)
        if "retail_bids_at_cutoff_share" in book:
            line += f"; {_pct(book['retail_bids_at_cutoff_share'])} of retail bids at cut-off"
        paras.append(line + ".")
    if "grey_market_premium_pct" in facts:
        paras.append(f"Grey-market premium {_fmt(facts['grey_market_premium_pct']['value'])}% "
                     f"(unofficial).")

    if "red_flags" in facts:
        paras.append("Concerns raised in the documents read: "
                     + "; ".join(i["text"] for i in facts["red_flags"]) + ".")
    return "\n\n".join(paras)


# ─────────────────────────── the model ────────────────────────────────────

def _llm_narration(facts: Mapping[str, Any], *, client: Any, model: str | None,
                   ) -> tuple[str, str, str]:
    """(prose, model, reason). Prose is '' when the call failed, returned
    nothing, or failed a guard — the reason says which."""
    from core.config import settings
    from core.config.prompts.shared.ipo_narrate import (
        IPO_NARRATE_SYSTEM_PROMPT, IPO_NARRATE_USER_TEMPLATE)
    from services.clients.llm_client import JSON_MODE_EXTRA_BODY, get_llm_client, record_llm_call

    model = model or settings.LLM_MODEL_BULK
    max_words = int(getattr(settings, "IPO_NARRATE_MAX_WORDS", 220))
    max_tokens = int(getattr(settings, "IPO_NARRATE_MAX_TOKENS", 600))
    started = time.time()
    try:
        client = client or get_llm_client()
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": IPO_NARRATE_SYSTEM_PROMPT.format(max_words=max_words)},
                {"role": "user", "content": IPO_NARRATE_USER_TEMPLATE.format(
                    company=facts.get("company", ""), symbol=facts.get("symbol", ""),
                    close_date=facts.get("close_date", ""),
                    facts=json.dumps(for_model(facts), indent=1, ensure_ascii=False))},
            ],
            temperature=0.0,            # a rendering of given facts, not a sample
            max_tokens=max_tokens,
            # Reasoning off: the note is a restatement, and reasoning tokens
            # would spend the cap the word limit was sized for.
            extra_body=JSON_MODE_EXTRA_BODY,
        )
        choice = resp.choices[0]
        raw = (choice.message.content or "").strip()
        truncated = getattr(choice, "finish_reason", None) == "length"
        usage = getattr(resp, "usage", None)
        record_llm_call(_CALLER, model, getattr(usage, "prompt_tokens", 0) or 0,
                        getattr(usage, "completion_tokens", 0) or 0,
                        int((time.time() - started) * 1000), True)
    except Exception as exc:
        logger.warning("[%s] narration failed for %s (non-fatal): %s",
                       _CALLER, facts.get("symbol", ""), exc)
        try:
            record_llm_call(_CALLER, model, 0, 0, int((time.time() - started) * 1000), False)
        except Exception:
            pass
        return "", model, f"llm error: {str(exc)[:160]}"
    if truncated:
        logger.warning("[%s] response TRUNCATED at %d tokens for %s — kept to the last sentence",
                       _CALLER, max_tokens, facts.get("symbol", ""))
        raw = _to_last_sentence(raw)
    if not raw:
        return "", model, "empty response"
    problem = check_narration(raw, facts)
    if problem:
        logger.warning("[%s] narration REJECTED for %s (%s) — template used",
                       _CALLER, facts.get("symbol", ""), problem)
        return "", model, problem
    return raw, model, ""


# ─────────────────────────── the whole note ───────────────────────────────

def compose(body: str, urls: list[str]) -> str:
    """Body + the code-owned trailer. The sources line and the framing are
    never the model's to write or omit."""
    doms = domains_of(urls)
    trailer = (f"Sources: {', '.join(doms)}.\n" if doms else "") + FRAMING
    return body.rstrip() + "\n\n" + trailer


def narrate(research: IpoSubstance | None, hype: HypeReading | None,
            substance: SubstanceReading | None, row: Mapping[str, Any] | None, *,
            symbol: str, close_date: str, state: str = "",
            client: Any = None, model: str | None = None,
            previous: IpoNarration | None = None) -> IpoNarration:
    """The note for one issue. Never raises.

    `previous` is the narration on the newest stored row for this key: when
    its facts digest matches, it is returned as-is and no model is called —
    the same facts read the same way, and a nightly re-read must not re-earn
    its prose.
    """
    try:
        facts = narration_facts(research, hype, substance, row,
                                symbol=symbol, close_date=close_date, state=state)
        if not has_findings(facts):
            return IpoNarration()
        digest = facts_digest(facts)
        urls = facts_urls(facts)
        if previous is not None and previous.text and previous.facts_digest == digest:
            return previous.model_copy(deep=True)

        from core.config import settings
        body, used_model, reason = "", "", "narration disabled"
        if getattr(settings, "IPO_NARRATE_ENABLED", True):
            body, used_model, reason = _llm_narration(facts, client=client, model=model)
        source = "llm" if body else "template"
        if not body:
            body = render_template(facts)
        return IpoNarration(text=compose(body, urls), source=source, model=used_model,
                            urls=urls, facts_digest=digest,
                            fallback_reason="" if source == "llm" else reason)
    except Exception as exc:
        logger.warning("[%s] narrator failed for %s (non-fatal): %s", _CALLER, symbol, exc)
        return IpoNarration()
