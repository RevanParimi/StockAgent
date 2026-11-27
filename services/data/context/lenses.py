"""
services/data/context/lenses.py
===============================
PR-032: industry lenses, the first slice of the adopted lenses design (spec
2026-09-26 §4.1, in SA-026's file shape; SA-026 itself stays paused).

**A lens** is one small data file per industry group, `config/lenses/<id>.yaml`:

    id: cement
    display: Cement
    industries: ["Building Materials"]     # the Yahoo industry labels it covers
    kpis: [realisation per tonne, ...]     # what moves this industry's profits
    news_terms: "volumes realisation prices capacity"
    sector_query: "India cement prices demand ... news {month} {year}"
    policy_query: "{company_name} cement capacity expansion results {year}"
    macro_drivers: [coal and petcoke prices, ...]

Lenses are written offline and reviewed (`scripts/lenses/draft_lens.py` drafts
one from a fixed brief); only committed files are read, never a model at run
time, so the same stock on the same day gets the same searches.

**Which lens** (`LensSet.lens_for`), from the stock's Yahoo industry label (the
peers step's profile, so no extra lookup):

- a label a lens lists -> that lens (`kind` "lens", recorded as its id);
- a label no lens lists -> the **default lens** (`kind` "default"): its sector
  search is worded from the label itself;
- no label -> `kind` "none": today's general-path wording.

**The general path only.** The bundle builder asks for a lens when the graph
is "generic" and `lenses.enabled` is true (default false). The four sector
paths never read one. What a choice changes (`None` = today's wording):

| Search          | lens                      | default                    | none          |
|-----------------|---------------------------|----------------------------|---------------|
| company news    | `news_terms`              | today's                    | today's       |
| sector news     | `sector_query`            | built from the label       | today's       |
| macro news      | the lens's macro drivers  | `DEFAULT_MACRO_QUERY`      | `DEFAULT_MACRO_QUERY` |
| page extract    | `policy_query`            | today's                    | today's       |

Today's macro wording names the graph ("India generic sector macro ...");
with the setting on, no general-path query does. The number of calls does not
change.

**The analyst is told the industry**: `industry_block` is a short text the
bundle puts above its sections. It is not a section: no status, no health
count, not essential.

**Checked when loaded** (`load_lenses`; the server's startup logs it): every
required field present and of its type, ids unique and equal to the file
name, no label in two lenses, and only the allowed placeholders in a query.
A broken set raises `LensError`; `active_lenses` then logs it as an error
and returns None, so every bundle keeps today's wording.
"""
from __future__ import annotations

import logging
import os
import re
import string
import threading
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

_RELDIR = Path("config") / "lenses"
_ENV_DIR = "LENS_DIR"

KIND_LENS = "lens"
KIND_DEFAULT = "default"
KIND_NONE = "none"

# Today's general-path macro search named the graph ("India generic sector
# ..."). The default lens, and a stock with no label, search this instead.
DEFAULT_MACRO_QUERY = "India economy inflation RBI rupee crude oil news {Month} {Year}"
# The default lens's sector search, worded from the Yahoo label itself.
DEFAULT_SECTOR_QUERY = "India {industry} industry demand prices policy news {month} {year}"

_ID = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
_REQUIRED = ("id", "display", "industries", "kpis", "news_terms", "sector_query",
             "policy_query", "macro_drivers")
# Fields a later card (SA-026) may add are allowed; these are the ones read here.
_PLACEHOLDERS = {
    "sector_query": {"month", "year"},
    "policy_query": {"company_name", "ticker", "year"},
    "news_terms": set(),
}
_MAX_ITEMS = 8           # kpis and macro drivers: a short list, not a manual
_MAX_TEXT = 160          # one KPI, driver or term string
_MAX_QUERY = 200
BLOCK_MAX_CHARS = 900


class LensError(ValueError):
    """A lens file, or the set of them, is malformed."""


@dataclass(frozen=True)
class Lens:
    id: str
    display: str
    industries: tuple[str, ...]
    kpis: tuple[str, ...]
    news_terms: str
    sector_query: str
    policy_query: str
    macro_drivers: tuple[str, ...]


@dataclass(frozen=True)
class LensChoice:
    """The lens one general-path bundle used, and the label it came from."""

    kind: str                      # KIND_LENS | KIND_DEFAULT | KIND_NONE
    industry: str = ""             # the Yahoo label; "" for KIND_NONE
    lens: Lens | None = None       # set for KIND_LENS only

    @property
    def record(self) -> str:
        """What provenance and the coverage line record: the lens's id,
        "default" or "none"."""
        return self.lens.id if self.lens is not None else self.kind

    # -- the four searches; None keeps today's wording ---------------------

    def company_news_terms(self) -> str | None:
        return self.lens.news_terms if self.lens is not None else None

    def sector_query(self, today: date) -> str | None:
        month, year = today.strftime("%B"), today.year
        if self.lens is not None:
            return self.lens.sector_query.format(month=month, year=year)
        if self.kind == KIND_DEFAULT:
            return DEFAULT_SECTOR_QUERY.format(industry=self.industry, month=month, year=year)
        return None

    def macro_query(self, today: date) -> str:
        """Never None: today's macro wording names the graph."""
        month, year = today.strftime("%B"), today.year
        if self.lens is not None:
            drivers = " ".join(self.lens.macro_drivers)
            return f"India {drivers} economy news {month} {year}"
        return DEFAULT_MACRO_QUERY.format(Month=month, Year=year)

    def policy_query(self, company_name: str, ticker: str, today: date) -> str | None:
        if self.lens is None:
            return None
        return self.lens.policy_query.format(company_name=company_name, ticker=ticker,
                                             year=today.year)

    # -- what the analyst is told ------------------------------------------

    def block(self) -> str:
        """The industry block above the bundle's sections; "" with no label."""
        if self.kind == KIND_NONE or not self.industry:
            return ""
        tail = ("Judge the stock on these where the bundle has evidence. "
                "A number the bundle does not contain stays unknown.")
        if self.lens is None:
            text = (f"Industry: {self.industry} (Yahoo's label; no lens is written for it "
                    "yet). Judge the stock on what usually moves this industry's profits "
                    "where the bundle has evidence. A number the bundle does not contain "
                    "stays unknown.")
        else:
            lens = self.lens
            text = (f"Industry: {lens.display} (Yahoo: {self.industry}). "
                    f"What usually moves this industry's profits: {'; '.join(lens.kpis)}. "
                    f"Macro items that matter: {'; '.join(lens.macro_drivers)}. {tail}")
        return text[:BLOCK_MAX_CHARS]


@dataclass(frozen=True)
class LensSet:
    lenses: tuple[Lens, ...]
    path: str = ""
    _by_label: dict = field(default_factory=dict, compare=False, repr=False)

    def lens_for(self, industry: str | None) -> LensChoice:
        """The lens for a Yahoo industry label (module docstring)."""
        label = str(industry or "").strip()
        if not label:
            return LensChoice(KIND_NONE)
        lens = self._by_label.get(label.casefold())
        if lens is None:
            return LensChoice(KIND_DEFAULT, label)
        return LensChoice(KIND_LENS, label, lens)

    def covered_labels(self) -> list[str]:
        return sorted(label for lens in self.lenses for label in lens.industries)


# ---------------------------------------------------------------------------
# Loading and checking
# ---------------------------------------------------------------------------

def lens_dir() -> Path:
    """LENS_DIR, else config/lenses in the working directory (/app in the
    image), else next to this package's repo root."""
    override = os.getenv(_ENV_DIR)
    if override:
        return Path(override)
    candidate = Path.cwd() / _RELDIR
    if candidate.is_dir():
        return candidate
    for parent in Path(__file__).resolve().parents:
        candidate = parent / _RELDIR
        if candidate.is_dir():
            return candidate
    return Path.cwd() / _RELDIR


def _text(name: str, field_name: str, value, limit: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LensError(f"{name}: {field_name} must be a non-empty string")
    value = " ".join(value.split())
    if len(value) > limit:
        raise LensError(f"{name}: {field_name} is longer than {limit} characters")
    return value


def _items(name: str, field_name: str, value, limit: int = _MAX_ITEMS) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise LensError(f"{name}: {field_name} must be a non-empty list")
    if len(value) > limit:
        raise LensError(f"{name}: {field_name} has {len(value)} items, at most {limit}")
    return tuple(_text(name, f"{field_name}[{i}]", v, _MAX_TEXT) for i, v in enumerate(value))


def _placeholders(name: str, field_name: str, template: str) -> None:
    allowed = _PLACEHOLDERS[field_name]
    try:
        parsed = list(string.Formatter().parse(template))
    except ValueError as exc:
        raise LensError(f"{name}: {field_name} is not a valid template: {exc}") from None
    for _literal, placeholder, spec, conversion in parsed:
        if placeholder is None:
            continue
        if placeholder not in allowed or spec or conversion:
            raise LensError(
                f"{name}: {field_name} uses {{{placeholder}}}; allowed: "
                + (", ".join(f"{{{p}}}" for p in sorted(allowed)) or "none"))


def parse_lens(raw, name: str) -> Lens:
    """One lens from a file's parsed YAML; `name` is the file's stem."""
    if not isinstance(raw, dict):
        raise LensError(f"{name}: the file must hold a mapping")
    missing = [k for k in _REQUIRED if k not in raw]
    if missing:
        raise LensError(f"{name}: missing {', '.join(missing)}")
    lens_id = raw["id"]
    if not isinstance(lens_id, str) or not _ID.match(lens_id):
        raise LensError(f"{name}: id must be lower-case letters, digits and _ ({lens_id!r})")
    if lens_id != name:
        raise LensError(f"{name}: id {lens_id!r} differs from the file name")
    news_terms = _text(name, "news_terms", raw["news_terms"], _MAX_QUERY)
    sector_query = _text(name, "sector_query", raw["sector_query"], _MAX_QUERY)
    policy_query = _text(name, "policy_query", raw["policy_query"], _MAX_QUERY)
    _placeholders(name, "news_terms", news_terms)
    _placeholders(name, "sector_query", sector_query)
    _placeholders(name, "policy_query", policy_query)
    for field_name, query in (("sector_query", sector_query), ("policy_query", policy_query),
                              ("news_terms", news_terms)):
        if re.search(r"\bgeneric\b", query, re.IGNORECASE):
            raise LensError(f"{name}: {field_name} names the graph (\"generic\")")
    return Lens(
        id=lens_id,
        display=_text(name, "display", raw["display"], 60),
        industries=_items(name, "industries", raw["industries"], limit=16),
        kpis=_items(name, "kpis", raw["kpis"]),
        news_terms=news_terms,
        sector_query=sector_query,
        policy_query=policy_query,
        macro_drivers=_items(name, "macro_drivers", raw["macro_drivers"], limit=4),
    )


def load_lenses(directory: Path | str | None = None) -> LensSet:
    """Every `*.yaml` in the lens directory, checked. Raises `LensError` on a
    malformed file, a label in two lenses or a missing directory."""
    import yaml

    folder = Path(directory) if directory is not None else lens_dir()
    if not folder.is_dir():
        raise LensError(f"no lens directory at {folder}")
    lenses: list[Lens] = []
    by_label: dict[str, Lens] = {}
    for path in sorted(folder.glob("*.yaml")):
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise LensError(f"{path.stem}: unreadable: {exc}") from None
        lens = parse_lens(raw, path.stem)
        for label in lens.industries:
            key = label.casefold()
            if key in by_label:
                raise LensError(f'label "{label}" is in two lenses: '
                                f"{by_label[key].id} and {lens.id}")
            by_label[key] = lens
        lenses.append(lens)
    if not lenses:
        raise LensError(f"no lens files in {folder}")
    return LensSet(tuple(lenses), str(folder), by_label)


# ---------------------------------------------------------------------------
# The setting, and the set the bundle reads
# ---------------------------------------------------------------------------

_memo: dict[str, tuple[float, LensSet | None, str | None]] = {}
_memo_lock = threading.Lock()


def lenses_enabled() -> bool:
    """`lenses.enabled` in config.yaml (default false: today's wording)."""
    try:
        from backend.shared.config.settings.loader import cfg
        return bool(cfg("lenses.enabled", fallback=False))
    except Exception as exc:
        logger.debug("[lenses] lenses.enabled unreadable, off: %s", exc)
        return False


def _dir_stamp(folder: Path) -> float:
    try:
        return max([folder.stat().st_mtime]
                   + [p.stat().st_mtime for p in folder.glob("*.yaml")])
    except OSError:
        return -1.0


def checked_lenses() -> tuple[LensSet | None, str | None]:
    """(the set, None), or (None, why) when it does not load. Kept per
    process until a file changes; never raises."""
    folder = lens_dir()
    stamp = _dir_stamp(folder)
    key = str(folder)
    with _memo_lock:
        hit = _memo.get(key)
        if hit is not None and hit[0] == stamp:
            return hit[1], hit[2]
        try:
            found, why = load_lenses(folder), None
        except LensError as exc:
            found, why = None, str(exc)
            logger.error("[lenses] the lens files do not load, so every bundle keeps "
                         "today's wording: %s", why)
        _memo[key] = (stamp, found, why)
        return found, why


def active_lenses() -> LensSet | None:
    """The set a general-path bundle reads: None when `lenses.enabled` is off
    or the files do not load."""
    if not lenses_enabled():
        return None
    return checked_lenses()[0]


def startup_line() -> str:
    """The server's startup check, as one line: the setting, and the set's
    size or why it does not load."""
    found, why = checked_lenses()
    state = "on" if lenses_enabled() else "off"
    if found is None:
        return f"lenses.enabled {state}; lens files NOT loaded: {why}"
    return (f"lenses.enabled {state}; {len(found.lenses)} lenses covering "
            f"{len(found.covered_labels())} Yahoo industries ({found.path})")


def coverage(dives, lens_set: LensSet | None = None) -> dict:
    """The week's general-path dives by the lens their industry has: counts
    of lens / default / none, and the industries without a lens, most dives
    first. A dive is general-path when its `graph` is "generic". Reads the
    dive's own Yahoo label; works whether or not the setting is on."""
    found = lens_set if lens_set is not None else checked_lenses()[0]
    out = {"dives": 0, "lens": 0, "default": 0, "none": 0, "lacking": {},
           "enabled": lenses_enabled(), "loaded": found is not None}
    if found is None:
        return out
    for d in dives or ():
        if str(getattr(d, "graph", "") or "") != "generic":
            continue
        out["dives"] += 1
        choice = found.lens_for(getattr(d, "industry", ""))
        out[choice.kind] += 1
        if choice.kind == KIND_DEFAULT:
            out["lacking"][choice.industry] = out["lacking"].get(choice.industry, 0) + 1
    out["lacking"] = dict(sorted(out["lacking"].items(), key=lambda kv: (-kv[1], kv[0])))
    return out


def coverage_line(summary: dict | None) -> str:
    """'general-path dives 7: lens 5, default 1, no label 1; no lens yet:
    Medical Care Facilities (1); lenses.enabled off' for the scheduler's log."""
    s = summary or {}
    if not s.get("loaded", False):
        return "lens files not loaded"
    lacking = s.get("lacking") or {}
    gap = ("; no lens yet: " + ", ".join(f"{k} ({v})" for k, v in lacking.items())
           if lacking else "")
    state = "on" if s.get("enabled") else "off"
    return (f"general-path dives {s.get('dives', 0)}: lens {s.get('lens', 0)}, "
            f"default {s.get('default', 0)}, no label {s.get('none', 0)}{gap}; "
            f"lenses.enabled {state}")
