"""
FIX-026 — the deep dive's own analysis names a stock's sector key.

A stock's sector key decides SA-050's 30% sector cap, the shelf's per-sector
cap, the graph its later analyses run and the prediction-store directory its
forecasts are written under. A wrong key works both ways: "generic" lumps
unrelated stocks under one cap, and one sector under two keys passes it twice.

**How a key is named.** The deep dive asks its one analysis call (the unified
analyst, no extra call) for one key from the configured list
(`configured_sectors`: config/sector_toggles.json, the registry's list), with
Yahoo Finance's sector and industry as evidence. The answer is checked by
membership in that list, never by pattern. "generic" counts only as an
explicit "none of ours fits" with a reason.

**Decided once.** A stock that already has a key keeps it, and the answer is
only recorded beside it: the managed record's key (its forecasts live
there), else the registry's ticker map (our configuration), else the key an
earlier analysis named for the idea. Only a stock with none of these takes
the answer. Example: TATAMOTORS is in the ticker map as "automobile"; a dive
answering "logistics" stores "automobile" and records the disagreement.

**Nothing is silently generic.** An empty, malformed or unknown answer
leaves the idea filed under the "generic" graph with source "unnamed" and
the problem recorded. Such an idea is shelved (its paper lane runs, and the
next Saturday's re-dive asks again), but nothing buys it until an analysis
names its key: neither cap can be checked for a stock whose sector is not
known. Example: an answer of "Pharmaceuticals" is not a key, so the idea
waits; next week's answer "pharma" names it.

**The graph before the answer.** The call needs a graph before it can answer.
A stock with a known key runs that key's graph. Otherwise `graph_guess` picks
one of the four native graphs when Yahoo's labels clearly name that industry,
else the generic graph. The guess only chooses the graph: it never becomes a
stored key.

The weekly discovery summary (`summarise`) and the watchdog's `sector_keys`
check name every stock whose key is missing, "generic", disputed or named
without Yahoo's labels.
"""
from __future__ import annotations

from backend.shared.schemas.discovery import SectorReading

GENERIC = "generic"
_ANSWER_CAP = 40
_REASON_CAP = 200

# Problems that leave a stock with no key. "not_a_key" is reported apart
# ("invalid") from the rest ("unnamed").
_PROBLEM_TEXT = {
    "no_answer": "the analysis gave no sector answer",
    "malformed": "the analysis's sector answer was malformed",
    "not_a_key": "the analysis answered {answer!r}, not one of our keys",
    "generic_without_reason": 'the analysis answered "generic" without saying why none fits',
}

# The first guess at a graph for a stock with no key yet: Yahoo industries
# that name one of the native graphs' industries. Not a sector key.
_GRAPH_GUESS_INDUSTRIES: dict[str, tuple[str, ...]] = {
    "automobile": ("Auto Manufacturers", "Auto Parts", "Auto & Truck Dealerships",
                   "Recreational Vehicles", "Farm & Heavy Construction Machinery"),
    "it_sector": ("Information Technology Services", "Software - Application",
                  "Software - Infrastructure"),
    "renewable_energy": ("Solar", "Utilities - Renewable",
                         "Utilities - Independent Power Producers",
                         "Utilities - Regulated Electric", "Utilities - Diversified"),
}


def _cut(value, cap: int = _ANSWER_CAP) -> str:
    return str(value if value is not None else "").strip()[:cap]


def configured_sectors() -> dict[str, str]:
    """{key: display name} for every configured sector key (the registry's
    list, config/sector_toggles.json), "generic" excluded: the list the
    analysis answers from and a stored key is checked against."""
    from backend.sectors.registry import SectorRegistry
    out: dict[str, str] = {}
    for row in SectorRegistry.all_sectors():
        key = str(row.get("sector") or "").strip().lower()
        if key and key != GENERIC:
            out[key] = str(row.get("display") or key)
    return out


def ticker_map_sector(symbol: str) -> str:
    """The registry's ticker map's key for `symbol`, "" when it has none."""
    from backend.sectors.registry import TICKER_SECTOR
    return str(TICKER_SECTOR.get(symbol.strip().upper(), "") or "").strip().lower()


def graph_guess(classification: dict | None) -> str:
    """The graph a stock with no key yet runs under: "automobile",
    "it_sector" or "renewable_energy" when Yahoo's industry is one of theirs,
    "banking_bfsi" for Yahoo's "Financial Services" outside insurance, else
    "generic". Example: industry "Software - Application" runs the IT graph;
    "Drug Manufacturers - General" runs the generic one."""
    c = classification or {}
    industry = str(c.get("industry") or "").strip()
    for graph, industries in _GRAPH_GUESS_INDUSTRIES.items():
        if industry in industries:
            return graph
    if (str(c.get("sector") or "").strip() == "Financial Services"
            and not industry.startswith("Insurance")):
        return "banking_bfsi"
    return GENERIC


def _yahoo_labels(classification: dict | None) -> tuple[str, str]:
    c = classification or {}
    return str(c.get("sector") or "").strip(), str(c.get("industry") or "").strip()


def sector_question(classification: dict | None, keys: dict[str, str]) -> str:
    """The text the deep dive appends to its analysis prompt: name one key
    from `keys` in a SECTOR_ANSWER_KEY block, with Yahoo's labels as
    evidence."""
    from backend.shared.pipeline.unified_analyst import SECTOR_ANSWER_KEY
    sector, industry = _yahoo_labels(classification)
    if sector or industry:
        yahoo = (f'Yahoo Finance classifies it as sector "{sector or "none given"}", '
                 f'industry "{industry or "none given"}"; these labels are evidence, '
                 "not the answer.")
    else:
        yahoo = "Yahoo Finance gives no classification for it."
    listing = "; ".join(f"{k} ({v})" for k, v in sorted(keys.items()))
    return (
        "=== SECTOR KEY ===\n"
        f'Add ONE more top-level block, "{SECTOR_ANSWER_KEY}", after the dimensions: the '
        "sector this company belongs to, chosen from OUR keys below. Judge from the business "
        "the data bundle describes (what it sells, where its revenue comes from). "
        f"{yahoo}\n"
        f"Our keys: {listing}.\n"
        'Answer "generic" only when none of our keys fits, and say why in the reason.\n'
        f'"{SECTOR_ANSWER_KEY}": '
        '{"key": "<one key exactly as written above, or generic>", '
        '"reason": "<one short sentence>", '
        '"yahoo_fits": <true when Yahoo\'s labels describe this business, false when they '
        "do not, null when Yahoo gave none>}\n"
    )


def read_answer(answer, keys: dict[str, str], classification: dict | None) -> SectorReading:
    """The analysis's sector block, checked by membership in `keys`; an
    explicit "generic" needs a reason. Never raises. Examples: {"key":
    "pharma"} names pharma; {"key": "Pharmaceuticals"} is "not_a_key";
    None is "no_answer"; "pharma" (a bare string) is "malformed"."""
    sector, industry = _yahoo_labels(classification)
    gap = not (sector or industry)
    if answer is None:
        return SectorReading(problem="no_answer", yahoo_gap=gap)
    if not isinstance(answer, dict):
        return SectorReading(answer=_cut(answer), problem="malformed", yahoo_gap=gap)
    raw = answer.get("key")
    reason = answer.get("reason")
    reason = _cut(reason, _REASON_CAP) if isinstance(reason, str) else ""
    fits = answer.get("yahoo_fits")
    fits = fits if isinstance(fits, bool) else None
    if raw is None:
        problem, written = "no_answer", ""
    elif not isinstance(raw, str):
        problem, written = "malformed", _cut(raw)
    else:
        written = _cut(raw)
        key = raw.strip().lower()
        if not key:
            problem = "no_answer"
        elif key == GENERIC:
            problem = "" if reason else "generic_without_reason"
        elif key in keys:
            problem = ""
        else:
            problem = "not_a_key"
    return SectorReading(answer=written, reason=reason, yahoo_fits=fits,
                         problem=problem, yahoo_gap=gap)


def key_named(obj, keys: dict[str, str]) -> bool:
    """True when `obj` (a shelf idea or a dive) is filed under a configured
    key other than "generic"."""
    return (str(getattr(obj, "sector", "") or "").strip().lower() in keys)


def known_key(symbol: str, *, managed: dict[str, str], idea, keys: dict[str, str],
              ) -> tuple[str, str]:
    """(key, source) a stock already has, decided before this analysis:
    the managed record's ("managed"), the ticker map's ("ticker_map"), or a
    key an earlier analysis named for its shelf idea ("earlier"); ("", "")
    when none. An idea filed as "generic" may still be named. The managed
    record's key is returned exactly as stored, as `candidates.holding_sector`
    does: it names the directory its forecasts are written under."""
    sym = symbol.strip().upper()
    if managed.get(sym):
        return managed[sym], "managed"
    mapped = ticker_map_sector(sym)
    if mapped:
        return mapped, "ticker_map"
    if idea is not None and key_named(idea, keys):
        return str(idea.sector).strip().lower(), "earlier"
    return "", ""


def decide_key(reading: SectorReading, known: tuple[str, str]) -> tuple[str, SectorReading]:
    """(the key to store, the reading with its source). A known key stays;
    else a named answer is the key; else "generic" with source "unnamed",
    which nothing buys."""
    key, source = known
    if key:
        return key, reading.model_copy(update={"source": source})
    if not reading.problem:
        return reading.answer.strip().lower(), reading.model_copy(update={"source": "analysis"})
    return GENERIC, reading.model_copy(update={"source": "unnamed"})


_DECIDED_BEFORE = ("managed", "ticker_map", "earlier")


def unnamed_why(obj, keys: dict[str, str]) -> str:
    """Why a shelf idea (or a dive) has no sector key, "" when it has one: a
    configured key, "generic" an analysis chose with its reason, or a
    "generic" decided before the analysis (a managed record's). An idea
    shelved before FIX-026 under "generic" counts as unnamed."""
    if key_named(obj, keys):
        return ""
    sector = str(getattr(obj, "sector", "") or "").strip()
    generic = sector.lower() == GENERIC
    r = getattr(obj, "sector_reading", None)
    if not sector:
        return "no sector key"
    if r is not None and (r.source in _DECIDED_BEFORE
                          or (r.source == "analysis" and not r.problem)):
        return "" if generic else f'filed as "{sector}", which is not one of our keys'
    if r is None or not r.problem:
        return ('filed as "generic" before the analysis named sectors' if generic
                else f'filed as "{sector}", which is not one of our keys')
    return _PROBLEM_TEXT.get(r.problem, r.problem).format(answer=r.answer)


def _generic_why(r: SectorReading | None) -> str:
    if r is not None and r.source in _DECIDED_BEFORE:
        return f"kept from the {r.source.replace('_', ' ')}"
    return r.reason if r is not None and r.reason else "none of our keys fits"


def _disagrees(r: SectorReading | None, key: str) -> bool:
    return (r is not None and r.source in ("managed", "ticker_map", "earlier")
            and not r.problem and r.answer.strip().lower() != key)


def describe(obj, keys: dict[str, str]) -> str:
    """One plain line about `obj`'s key for the summary and the watchdog.
    Example: 'ACME pharma; the analysis says Yahoo's labels (Financial
    Services / Banks - Regional) do not fit'."""
    sym = getattr(obj, "symbol", "?")
    key = str(getattr(obj, "sector", "") or "").strip().lower()
    r = getattr(obj, "sector_reading", None)
    why = unnamed_why(obj, keys)
    if why:
        text = f"{sym} has no sector key: {why}"
    elif key == GENERIC:
        text = f"{sym} generic: {_generic_why(r)}"
    else:
        text = f"{sym} {key}"
    labels = " / ".join(x for x in (getattr(obj, "market_sector", ""),
                                    getattr(obj, "industry", "")) if x)
    if r is not None:
        if r.yahoo_fits is False:
            text += f"; the analysis says Yahoo's labels ({labels or 'none'}) do not fit"
        if r.yahoo_gap:
            text += "; Yahoo gave no classification"
        if _disagrees(r, key):
            text += f"; kept from the {r.source.replace('_', ' ')}, the analysis answered {r.answer}"
    return text


def status(obj, keys: dict[str, str]) -> str:
    """"named", "generic", "invalid" (an answer that is not a key) or
    "unnamed" (no key for any other reason)."""
    if unnamed_why(obj, keys):
        r = getattr(obj, "sector_reading", None)
        return "invalid" if r is not None and r.problem == "not_a_key" else "unnamed"
    return GENERIC if not key_named(obj, keys) else "named"


def summarise(dives, keys: dict[str, str] | None = None) -> dict:
    """The week's dives by how their key was named, each stock named:
    named (with Yahoo's labels beside the key), generic, unnamed, invalid,
    disputed (Yahoo's labels do not fit), no_yahoo (Yahoo gave nothing) and
    kept (a key decided before, the analysis answering another)."""
    keys = configured_sectors() if keys is None else keys
    out: dict = {"named": {}, "generic": {}, "unnamed": {}, "invalid": {},
                 "disputed": {}, "no_yahoo": [], "kept": {}}
    for d in dives:
        r = getattr(d, "sector_reading", None)
        kind = status(d, keys)
        key = str(d.sector).strip().lower()
        labels = " / ".join(x for x in (d.market_sector, d.industry) if x) or "no Yahoo labels"
        if kind == "named":
            out["named"][d.symbol] = f"{key} (Yahoo: {labels})"
        elif kind == GENERIC:
            out["generic"][d.symbol] = _generic_why(r)
        else:
            out[kind][d.symbol] = unnamed_why(d, keys)
        if r is None:
            continue
        if r.yahoo_fits is False:
            out["disputed"][d.symbol] = f"{key}; Yahoo: {labels}"
        if r.yahoo_gap:
            out["no_yahoo"].append(d.symbol)
        if _disagrees(r, key):
            out["kept"][d.symbol] = f"{key} ({r.source.replace('_', ' ')}); the analysis answered {r.answer}"
    return out


def counts_line(summary: dict | None) -> str:
    """'named 5, generic 1, unnamed 0, invalid 1, disputed 1, no Yahoo 0,
    kept 2' for the scheduler's log line."""
    s = summary or {}
    names = (("named", "named"), ("generic", "generic"), ("unnamed", "unnamed"),
             ("invalid", "invalid"), ("disputed", "disputed"), ("no_yahoo", "no Yahoo"),
             ("kept", "kept"))
    return ", ".join(f"{label} {len(s.get(k) or ())}" for k, label in names)
