"""
Compass Phase A — daily corp-action sync (spec §4.1 corp-action invariant).

Adjusts adj_avg_price / adj_qty / dividends_received BEFORE any advisor rule
runs. Without this, a 1:1 bonus looks like a −50% crash and fires a false
EXIT. Raw qty/avg_buy_price are NEVER mutated. Idempotent via applied-action
keys stored on the holding.

PR-009: the sync also returns what NSE listed for each held symbol
(`ActionRecord`), so the evidence exit rule can carry a shelf idea's
invalidation level, set in the rupees of its deep dive, into the review
day's price basis. FIX-016: the exit rule's grading reads the same record for
a sold stock, with the rows no ratio converts (`basis_changes`).

FIX-017: the sync applies only the ratios that record reads in full, so the
sync and the grading read every row alike, and asks NSE under its own code.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime

from backend.shared.schemas.portfolio import AppliedCorpAction, Holding
from core.portfolio.store import PortfolioStore
from services.data.fetchers.corporate_events import fetch_corp_actions

logger = logging.getLogger(__name__)

_BONUS_RE = re.compile(r"bonus[^0-9]*?(\d+)\s*:\s*(\d+)", re.I)
# FIX-017: a face-value split's two values, read after the word that names the split and with
# no other number between: "Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 2/-
# Per Share", and NSE's older short wordings "Fv Splt Frm Rs 10 To Re 1" (JSWSTEEL 2017) and
# "Face Value Split Rs.10/- To Re.1/- Per Share" (SBIN 2014).
_NAMES_SPLIT_RE = re.compile(r"split|splt|sub-?\s*division", re.I)
_SPLIT_RE = re.compile(
    r"(?:split|splt|sub-?\s*division)[^0-9]{0,40}?r[se]\.?\s*(\d+(?:\.\d+)?)"
    r"[^0-9]{0,40}?\bto\s+r[se]\.?\s*(\d+(?:\.\d+)?)", re.I
)
_DIV_RE = re.compile(r"dividend[^0-9]*(\d+(?:\.\d+)?)", re.I)
# FIX-016: rows that change the price basis by an amount the row does not give. A demerger
# or a scheme moves part of the company's value elsewhere; a consolidation, a capital
# reduction or a rights issue changes the price by a ratio this parser does not read.
# First match names the kind. A buy back, a dividend or a meeting leaves the basis alone.
_BASIS_CHANGE_KINDS = (
    ("demerger", re.compile(r"de[\s-]?merger|spin[\s-]?off|hive[\s-]?off", re.I)),
    ("scheme of arrangement", re.compile(r"\bsch(?:eme)?\b|amalgamation|\bmerger", re.I)),
    ("consolidation", re.compile(r"consolidat", re.I)),
    ("capital reduction",
     re.compile(r"capital\s+reduction|reduction\s+(?:of|in)\s+(?:share\s+)?capital"
                r"|return\s+of\s+capital", re.I)),
    ("rights issue", re.compile(r"\brights?\b|\brhs\b", re.I)),
)
# FIX-016 rework 3: the record fails closed. NSE words one action many ways ("Fv Splt Frm Rs 10
# To Re 1", "Bonus Preference Shares 21:1"), so a row is judged by every word in it. It is a
# ratio only when each word is one of an equity bonus or a face-value split, or of a part that
# leaves the price basis alone; neutral only when each word is one of such a part. Any other
# row is not read, and grading gives no result across it. The words are those of NSE's lists
# for the configured symbols, read in October 2026.
_NEUTRAL_WORDS = frozenset({
    # dividends, in NSE's spellings
    "dividend", "div", "divided", "interim", "final", "fin", "special", "spl", "int", "second",
    # meetings and votes
    "annual", "general", "meeting", "agm", "egm", "extra", "ordinary", "e", "voting",
    # buy backs, interest and redemption
    "buy", "back", "buyback", "interest", "payment", "redemption",
    # amounts, dates, NSE's notes on a revised row, and joining words
    "rs", "re", "per", "share", "shares", "sh", "equity", "and", "of", "plus", "including",
    "record", "date", "dates", "book", "closure", "purpose", "revised",
    "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
})
# A registrar change, removed before the words are read ("change" and "transfer" alone are not
# neutral words).
_NEUTRAL_PHRASE_RE = re.compile(r"change\s+in\s+registrar(?:\s+and\s+transfer\s+agent)?", re.I)
_RATIO_WORDS = {
    "bonus": frozenset({"bonus", "issue", "eq"}),
    "split": frozenset({"face", "value", "split", "sub", "division", "from", "to",
                        "fv", "splt", "frm"}),
}
# Words that name a change in the share count (a bonus or a face-value change), read or not.
_SHARE_COUNT_RE = re.compile(r"bonus|split|splt|sub-?\s*div|\bfv\b|face\s*value", re.I)
_WORD_RE = re.compile(r"[a-z]+")

_NSE_DATE_FMTS = ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d")


def _parse_date(raw: str) -> str | None:
    raw = (raw or "").strip()
    for fmt in _NSE_DATE_FMTS:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _row_desc(row: dict) -> str:
    for key in ("subject", "desc", "purpose"):
        v = row.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _row_ex_date(row: dict) -> str | None:
    for key in ("exDate", "ex_date", "date", "exdate"):
        v = row.get(key)
        if isinstance(v, str) and v.strip():
            return _parse_date(v.strip())
    return None


def basis_change_kind(desc: str) -> str:
    """The kind of price-basis change a row names that no ratio in it
    converts ("" when it names none): demerger, scheme of arrangement,
    consolidation, capital reduction or rights issue."""
    return next((kind for kind, pattern in _BASIS_CHANGE_KINDS if pattern.search(desc)), "")


def _words(text: str) -> set[str]:
    return set(_WORD_RE.findall(_NEUTRAL_PHRASE_RE.sub(" ", text).lower()))


def _share_count_parts(desc: str) -> list[tuple[str, float, str]] | None:
    """(kind, ratio, the words that state it) of the bonus and the split a
    row names, the bonus first. None when it names one whose ratio it does
    not state in a form read here: a bonus with no "new:held" ratio, a split
    with no two face values, or a ratio that adds no shares (a "split" from
    Rs 1 to Rs 10 is a consolidation)."""
    parts: list[tuple[str, float, str]] = []
    if "bonus" in desc.lower():
        m = _BONUS_RE.search(desc)
        if not m:
            return None
        new, held = float(m.group(1)), float(m.group(2))
        if not (new > 0 and held > 0):
            return None
        parts.append(("bonus", (new + held) / held, m.group(0)))
    if _NAMES_SPLIT_RE.search(desc):
        m = _SPLIT_RE.search(desc)
        if not m:
            return None
        old_fv, new_fv = float(m.group(1)), float(m.group(2))
        if not (new_fv > 0 and old_fv > new_fv):
            return None
        parts.append(("split", old_fv / new_fv, m.group(0)))
    return parts


def _read_ratios(desc: str, action: AppliedCorpAction | None,
                 beside_change: bool) -> tuple[AppliedCorpAction, ...]:
    """The ratios a row states for equity shares, read in full: one for an
    equity bonus or a face-value split, two for a row naming both (FIX-017:
    "Bonus 1:1/Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs
    2/- Per Share", BAJFINANCE 2016, is ×2 and ×5, a tenth of the price). The
    first keeps the row's key (`parse_action`'s, so a row applied before is
    known by it), the second adds "|split". Every word must be of an equity
    bonus or a face-value split or of a neutral part; beside a change no ratio
    converts, only the words that state the ratios are read: that change
    already leaves the row's day without a result. Else (): "Bonus Preference
    Shares 21:1" is not 22 equity shares for one."""
    if action is None or action.kind not in ("bonus", "split"):
        return ()
    parts = _share_count_parts(desc)
    if not parts:
        return ()
    text = " ".join(said for _kind, _ratio, said in parts) if beside_change else desc
    if not _words(text) <= _NEUTRAL_WORDS.union(*(_RATIO_WORDS[k] for k, _r, _s in parts)):
        return ()
    return tuple(action.model_copy(update={"kind": kind, "ratio": ratio,
                                           "key": action.key if i == 0
                                           else f"{action.key}|{kind}"})
                 for i, (kind, ratio, _said) in enumerate(parts))


def parse_action(row: dict) -> AppliedCorpAction | None:
    """Parse one raw NSE actions() row into an AppliedCorpAction: its bonus,
    else its split, else its dividend. Returns None for unrecognised or
    non-financial rows (AGM/EGM/rights…). The first amount found, not yet a
    reading: `action_record` decides which bonus and split rows are ratios of
    equity shares (FIX-017: the holding sync applies only those)."""
    desc = _row_desc(row)
    ex_date = _row_ex_date(row)
    if not desc or not ex_date:
        return None

    low = desc.lower()
    symbol = str(row.get("symbol", "")).upper()
    key = f"{symbol}|{ex_date}|{desc[:40]}"
    today_iso = date.today().isoformat()

    m = _BONUS_RE.search(low)
    if m:
        new, base = float(m.group(1)), float(m.group(2))
        if base > 0:
            return AppliedCorpAction(
                key=key, ex_date=ex_date, kind="bonus", desc=desc,
                ratio=(new + base) / base, applied_on=today_iso,
            )
    if _NAMES_SPLIT_RE.search(low):
        m = _SPLIT_RE.search(low)
        if m:
            old_fv, new_fv = float(m.group(1)), float(m.group(2))
            if new_fv > 0:
                return AppliedCorpAction(
                    key=key, ex_date=ex_date, kind="split", desc=desc,
                    ratio=old_fv / new_fv, applied_on=today_iso,
                )
    if "dividend" in low:
        m = _DIV_RE.search(low)
        if m:
            after = low[m.end(1):].lstrip()
            if after.startswith("%"):
                # AUD-046: percent-of-face-value quote ("Dividend 150%") —
                # booking it as ₹/share would inflate P&L and could suppress a
                # legitimate EXIT. Needs the face value to convert; skip.
                logger.warning(
                    "[corp_actions] percent-of-face-value dividend skipped "
                    "(needs face value, AUD-046): %s", desc[:80],
                )
                return None
            return AppliedCorpAction(
                key=key, ex_date=ex_date, kind="dividend", desc=desc,
                dividend_per_share=float(m.group(1)), applied_on=today_iso,
            )
    if _SHARE_COUNT_RE.search(desc):
        logger.warning(
            "[corp_actions] unparseable split/bonus row (manual review needed): %s", desc[:80]
        )
    return None


@dataclass(frozen=True)
class ActionRecord:
    """What NSE listed for one symbol in one sync (PR-009).

    `actions`: its bonus and split rows, parsed and read in full
    (`_read_ratios`; a row naming a bonus and a split gives both, FIX-017).
    The holding sync applies these and no other share-count change.
    `covers_from`: the earliest ex-date of any row it
    returned, whatever the kind, so every bonus or split with a later ex-date
    is in `actions` or `unparsed`; "" when it returned no dated row (NSE's
    answer, or a failed fetch: `fetch_corp_actions` returns [] for both).
    `rows` (FIX-018): how many rows it returned, dated or not, so 0 with an
    answer read by `read_corp_actions` means NSE lists nothing for the symbol.
    `unparsed`: ex-dates of rows naming a bonus or a face-value change that
    are not read as a ratio: one that could not be parsed, a bonus of other
    securities ("Bonus Preference Shares 21:1"), or one in words the record
    does not know ("Agm/Div-Rs.2/Fv Rs10tors5").
    `basis_changes` (FIX-016): (ex-date, kind) of rows that change the price
    basis by an amount they do not give (`basis_change_kind`), whatever else
    the row also says, and of any other row with a word that is not of a
    neutral part, as a corporate action of no known kind (rework 3)."""
    actions: tuple[AppliedCorpAction, ...] = ()
    covers_from: str = ""
    unparsed: tuple[str, ...] = ()
    basis_changes: tuple[tuple[str, str], ...] = ()
    rows: int = 0


def action_record(rows: list[dict], symbol: str) -> ActionRecord:
    """The ActionRecord of one symbol's raw NSE actions() rows. A row
    without an ex-date is not read."""
    actions, unparsed, changes, days = [], [], [], []
    for row in rows:
        ex = _row_ex_date(row)
        if ex is None:
            continue
        days.append(ex)
        desc = _row_desc(row)
        kind = basis_change_kind(desc)
        ratios = _read_ratios(desc, parse_action(dict(row, symbol=symbol)), bool(kind))
        words = _words(desc)
        if ratios:
            actions.extend(ratios)
        elif _SHARE_COUNT_RE.search(desc):
            unparsed.append(ex)
        elif not kind and not (words and words <= _NEUTRAL_WORDS):
            kind = f"corporate action of no known kind ({desc[:60]!r})"
        if kind:
            changes.append((ex, kind))
    return ActionRecord(actions=tuple(actions), covers_from=min(days) if days else "",
                        unparsed=tuple(sorted(unparsed)),
                        basis_changes=tuple(sorted(set(changes))), rows=len(rows))


def apply_actions_to_holding(
    holding: Holding, actions: list[AppliedCorpAction | None], today: date
) -> tuple[int, list[tuple[AppliedCorpAction, float]]]:
    """Apply every unapplied action with buy_date < ex_date <= today.
    Mutates the holding in place. Returns (number applied, dividend events)
    where each dividend event is (action, cash credit) — the caller books the
    credit to cash and the transactions ledger (AUD-045)."""
    applied_keys = {a.key for a in holding.applied_actions}
    # FIX-017: one bonus and one split per ex-date, whichever row states it. A row NSE rewords
    # ("Bonus 1:10 (Revised)") has a new key and is the same bonus.
    applied_steps = {(a.ex_date, a.kind) for a in holding.applied_actions
                     if a.kind in ("bonus", "split")}
    valid = sorted((a for a in actions if a is not None), key=lambda a: a.ex_date)
    count = 0
    div_events: list[tuple[AppliedCorpAction, float]] = []
    for action in valid:
        if action.key in applied_keys:
            continue
        ex = date.fromisoformat(action.ex_date)
        if ex <= date.fromisoformat(holding.buy_date) or ex > today:
            continue
        if action.kind in ("bonus", "split") and (action.ex_date, action.kind) in applied_steps:
            logger.info("[corp_actions] %s: the %s ex %s is already applied under another row; "
                        "not applied twice (%s)", holding.symbol, action.kind, action.ex_date,
                        action.desc[:60])
            continue
        if action.kind in ("bonus", "split") and action.ratio > 0:
            applied_steps.add((action.ex_date, action.kind))
            holding.adj_avg_price = holding.adj_avg_price / action.ratio
            holding.adj_qty = holding.adj_qty * action.ratio
        elif action.kind == "dividend":
            credit = holding.adj_qty * action.dividend_per_share
            holding.dividends_received += credit
            div_events.append((action, round(credit, 2)))
        holding.applied_actions.append(action)
        applied_keys.add(action.key)
        count += 1
        logger.info(
            "[corp_actions] %s: applied %s (%s) ex=%s ratio=%.3f dps=%.2f",
            holding.symbol, action.kind, action.desc[:60], action.ex_date,
            action.ratio, action.dividend_per_share,
        )
    return count, div_events


def sync_reading(holding: Holding, rows: list[dict], record: ActionRecord,
                 today: date) -> tuple[list[AppliedCorpAction], list[str]]:
    """FIX-017: what the sync may apply to `holding` from NSE's `rows`, and a
    named line for each share-count row after its buy, by `today`, that
    leaves its quantity and average price unchanged.

    Applied: the bonus and split ratios `record` reads in full (the exit
    rule's grading reads the same), one per ex-date and kind, and each row
    `parse_action` reads as a dividend in rupees. Never applied: a row the
    record cannot read (a bonus of preference shares, debentures or NCRPS, a
    split with no face values), and a day with two ratios of one kind.
    Named, never reversed: a bonus or split the holding applied under an
    earlier reading that NSE's list, reaching back to it, no longer gives."""
    buy, last = str(holding.buy_date)[:10], today.isoformat()
    by_step: dict[tuple[str, str], list[AppliedCorpAction]] = {}
    for a in record.actions:
        by_step.setdefault((a.ex_date, a.kind), []).append(a)
    steps, gaps = [], []
    for (ex, kind), found in sorted(by_step.items()):
        ratios = sorted({a.ratio for a in found})
        if len(ratios) == 1:
            steps.append(found[0])
        elif buy < ex <= last:
            gaps.append(f"NSE lists two {kind} ratios ex {ex} ({ratios[0]:g} and "
                        f"{ratios[-1]:g}); neither is applied")
    for ex in record.unparsed:
        if buy < ex <= last:
            said = " / ".join(sorted({_row_desc(r)[:60] for r in rows if _row_ex_date(r) == ex
                                      and _SHARE_COUNT_RE.search(_row_desc(r))}))
            gaps.append(f"NSE lists a split or bonus on {ex} that could not be read "
                        f"({said!r}); the quantity and average price are unchanged")
    if record.covers_from:
        for a in holding.applied_actions:
            if (a.kind in ("bonus", "split") and record.covers_from <= a.ex_date <= last
                    and (a.ex_date, a.kind) not in by_step):
                gaps.append(f"the {a.kind} ex {a.ex_date} (×{a.ratio:g}) was applied under an "
                            "earlier reading, and NSE's row no longer reads as one; the "
                            "quantity and average price keep it until corrected by hand")
    dividends = [a for a in (parse_action(dict(r, symbol=holding.symbol)) for r in rows)
                 if a is not None and a.kind == "dividend"]
    return steps + dividends, gaps


def sync_corp_actions(store: PortfolioStore, today: date, fetch=fetch_corp_actions) -> dict:
    """Daily sync for every holding of one user. Non-fatal per symbol —
    pipeline errors are telemetry, never training signal.

    Two phases (AUD-001): network fetches run OUTSIDE the store lock (seconds
    per symbol), then apply + dividend cash credit + save run in one short
    critical section against a FRESH load. Dividends credit cash_deployable
    and append a DIV ledger row when cash accounting is on (AUD-045).

    FIX-017: NSE is asked for the code the close is read under
    (`symbol_resolver.nse_symbol`: the registry alias CANARABANK is listed as
    CANBK), and only `sync_reading`'s actions are applied, so the sync and the
    exit rule's grading read every row alike.

    The result's `records` maps each symbol whose fetch did not raise to its
    ActionRecord (PR-009); `gaps` maps a symbol to the named lines of
    `sync_reading`, each also logged as a data-health warning."""
    from datetime import datetime, timezone

    from backend.shared.data.fetchers.symbol_resolver import nse_symbol

    # Phase 1 — network, lock-free, keyed by symbol from a snapshot.
    snapshot = store.load()
    actions_by_symbol: dict[str, list] = {}
    records: dict[str, ActionRecord] = {}
    gaps: dict[str, list[str]] = {}
    for holding in snapshot.holdings:
        try:
            rows = fetch(nse_symbol(holding.symbol, today))
            record = action_record(rows, holding.symbol)
            actions, lines = sync_reading(holding, rows, record, today)
        except Exception as exc:
            logger.warning(
                "[corp_actions] sync failed for %s (non-fatal): %s", holding.symbol, exc
            )
            continue
        records[holding.symbol] = record
        actions_by_symbol[holding.symbol] = actions
        for line in lines:
            logger.warning("[corp_actions] data health: %s: %s", holding.symbol, line)
        if lines:
            gaps[holding.symbol] = lines
    if not any(actions_by_symbol.values()):
        return {"applied": 0, "symbols": [], "records": records, "gaps": gaps}

    # Phase 2 — locked apply + credit + save on fresh state.
    from core.portfolio.autopilot import make_txn_id   # lazy: avoids import cycle
    from backend.shared.schemas.portfolio import TransactionRecord

    with store.locked():
        portfolio = store.load()
        total, touched, div_txns = 0, [], []
        for holding in portfolio.holdings:
            actions = actions_by_symbol.get(holding.symbol)
            if not actions:
                continue
            n, div_events = apply_actions_to_holding(holding, actions, today)
            if n:
                total += n
                touched.append(holding.symbol)
            for action, credit in div_events:
                if portfolio.cash_deployable is None or credit <= 0:
                    continue
                cash_before = portfolio.cash_deployable
                portfolio.cash_deployable = round(cash_before + credit, 2)
                div_txns.append(TransactionRecord(
                    txn_id=make_txn_id(portfolio.user_id, action.ex_date,
                                       holding.symbol, "DIV", action.key),
                    date=action.ex_date,
                    ts=datetime.now(timezone.utc).isoformat(),
                    user_id=portfolio.user_id, symbol=holding.symbol,
                    side="DIV", qty=0.0, price=action.dividend_per_share,
                    value=round(credit, 2), cash_before=round(cash_before, 2),
                    cash_after=portfolio.cash_deployable,
                    holding_qty_after=holding.adj_qty, realized_pnl=0.0,
                    source="autopilot", note=f"dividend: {action.desc[:40]}"))
        if total:
            existing = {t.txn_id for t in store.load_transactions(limit=2000)}
            for t in div_txns:
                if t.txn_id not in existing:
                    store.append_transaction(t)
            try:
                store.save(portfolio)
            except Exception as exc:
                logger.error(
                    "[corp_actions] portfolio save failed after %d applied actions (non-fatal): %s",
                    total, exc,
                )
                return {"applied": 0, "symbols": [], "save_failed": True, "records": records,
                        "gaps": gaps}
        return {"applied": total, "symbols": touched, "records": records, "gaps": gaps}
