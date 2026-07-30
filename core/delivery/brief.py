"""
Compass Phase C — Morning Brief (spec §7): 08:50 IST, right after the 08:45
pre-open shock check. Deterministic assembly from existing artifacts; ONE
BULK-tier narration call for the headline (fallback text on any failure).
Research tone, never "advice" (spec §2).
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import date, datetime, timezone
from pathlib import Path

from core.config import settings
from core.delivery.alerts import AlertEvent, emit_alerts
from core.delivery.channels import deliver
from core.discovery.ipo_tracker import upcoming_lockin_alerts
from core.intelligence.rl.nse_calendar import is_trading_day
from core.portfolio.store import PortfolioStore, active_user_ids
from services.data.fetchers.corporate_events import (
    load_events_calendar,
    next_results_event,
)
from services.data.fetchers.ipo import load_ipo_cache

logger = logging.getLogger(__name__)

# -- plain-language maps + pure formatting helpers (redesign 2026-07-27) -----
# Regime label -> (plain word, one-line gloss). Unknown labels degrade to
# (label.title(), "") in the renderer.
_REGIME_PLAIN: dict[str, tuple[str, str]] = {
    "MACRO_CRISIS":      ("Crisis", "a volatile market and outflows together — the system is at its most defensive."),
    "RISK_OFF":          ("Cautious", "the system reads elevated risk right now and is trading defensively."),
    "MOMENTUM_EXTENDED": ("Overextended", "a strong run has left the market overbought, so mean-reversion risk is up."),
    "RISK_ON":           ("Constructive", "a calm market with inflows — the system is comfortable leaning in."),
    "OVERSOLD":          ("Oversold", "the market has sold off sharply; beaten-down names may be due a bounce."),
    "NORMAL":            ("Steady", "conditions are normal; the system is trading as usual."),
}

# Holding verdicts are opaque to newcomers -> plain words (NEEDS ATTENTION only).
_VERDICT_PLAIN: dict[str, str] = {
    "EXIT": "Consider exiting", "TRIM": "Trim back", "ADD": "Add more",
    "HOLD": "Hold", "SWITCH": "Switch", "WAIT_FOR_LTCG": "Hold for tax",
}

# Sentence end = punctuation followed by whitespace (decimal-safe: "547.86" has
# no space after the dot, so it is not treated as a sentence boundary).
_SENT_END = re.compile(r"[.!?]\s")


def _pct(conviction) -> str:
    """0.654 -> '65%'. Bad input -> ''."""
    try:
        return f"{round(float(conviction) * 100)}%"
    except (TypeError, ValueError):
        return ""


def _trim_words(text: str, maxlen: int) -> str:
    """Collapse whitespace; trim to <= maxlen at a word boundary + '…' if cut."""
    t = " ".join((text or "").split())
    if len(t) <= maxlen:
        return t
    return t[:maxlen].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def _clean_headline(text: str, maxlen: int) -> str:
    """Length safety-net for an overnight headline (spec §4.2)."""
    return _trim_words(text, maxlen)


def _first_sentence(thesis: str, maxlen: int) -> str:
    """First sentence of a thesis (decimal-safe), capped at maxlen. '' if empty."""
    t = " ".join((thesis or "").split())
    if not t:
        return ""
    m = _SENT_END.search(t)
    sent = t[: m.start() + 1].strip() if m else t
    return _trim_words(sent, maxlen)


def _fmt_date(iso: str) -> str:
    try:
        return date.fromisoformat(iso).strftime("%a %d %b")
    except Exception:
        return iso


def _norm_text(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", (s or "").lower()).strip()


def _salient_tokens(headline: str, stopwords: frozenset) -> set[str]:
    """Distinctive-entity set for near-duplicate detection: slash-split (NRI/OCI ->
    two tokens), keep alnum, drop stopwords + short non-numeric tokens, crude
    singularise trailing 's'. Generic actors/verbs (rbi, boost, raise…) live in the
    stoplist so two stories don't cluster just for sharing them."""
    s = re.sub(r"[^a-z0-9 ]", " ", (headline or "").lower().replace("/", " "))
    out: set[str] = set()
    for t in s.split():
        if t.endswith("s") and len(t) > 3:
            t = t[:-1]
        if t in stopwords or (len(t) < 3 and not t.isdigit()):
            continue
        out.add(t)
    return out


def _dedup_overnight(items: list[dict], threshold: float, max_items: int,
                     min_shared: int = 0, stopwords: frozenset = frozenset()) -> list[dict]:
    """Collapse near-duplicate stories and keep the longest headline per cluster.
    Two items merge when they share a headline prefix, Jaccard>=threshold, OR (when
    min_shared>0) share >= min_shared salient entities. First-seen order, capped."""
    kept: list[dict] = []
    kept_norm: list[str] = []
    kept_tok: list[set] = []
    kept_sal: list[set] = []
    for it in items:
        norm = _norm_text(it["headline"])
        toks = set(norm.split())
        if not toks:
            continue
        sal = _salient_tokens(it["headline"], stopwords) if min_shared else set()
        dup = None
        for i, kn in enumerate(kept_norm):
            inter = len(toks & kept_tok[i])
            union = len(toks | kept_tok[i]) or 1
            entity_hit = min_shared and len(sal & kept_sal[i]) >= min_shared
            if norm in kn or kn in norm or (inter / union) >= threshold or entity_hit:
                dup = i
                break
        if dup is None:
            kept.append(it); kept_norm.append(norm); kept_tok.append(toks); kept_sal.append(sal)
        elif len(it["headline"]) > len(kept[dup]["headline"]):
            kept[dup] = it; kept_norm[dup] = norm; kept_tok[dup] = toks; kept_sal[dup] = sal
    return kept[:max_items]


def _dedup_ipos(rows: list[dict], max_items: int) -> list[dict]:
    """Dedup by symbol; a 'current' row beats 'upcoming'/'past'. First-seen order."""
    rank = {"current": 0, "upcoming": 1, "past": 2}
    best: dict[str, dict] = {}
    seq: list[str] = []
    for r in rows:
        sym = r.get("symbol", "")
        if not sym:
            continue
        if sym not in best:
            best[sym] = r; seq.append(sym)
        elif rank.get(r.get("status", ""), 9) < rank.get(best[sym].get("status", ""), 9):
            best[sym] = r
    return [best[s] for s in seq][:max_items]


def _ipo_demand(w: dict) -> str:
    """Human-readable subscription demand line for one IPO row."""
    total, qib, retail = w.get("total_x"), w.get("qib_x"), w.get("retail_x")
    if total is None and qib is None and retail is None:
        return "demand data pending"
    parts: list[str] = []
    if total is not None:
        parts.append(f"{total:g}× overall")
    extra = []
    if qib is not None:
        extra.append(f"QIB {qib:g}×")
    if retail is not None:
        extra.append(f"retail {retail:g}×")
    if extra:
        parts.append("(" + ", ".join(extra) + ")")
    return " ".join(parts) if parts else "demand data pending"


def _ipo_lean(row: dict) -> tuple[str, str]:
    """The tool's OWN demand-based research view of an IPO -> (label, reason).

    Demand-only: the IPO feed carries no valuation/earnings data, so this never
    claims a fundamental/P-E view. Never personal advice (spec §1)."""
    total, qib, retail = row.get("total_x"), row.get("qib_x"), row.get("retail_x")
    if total is None and qib is None and retail is None:
        return ("data pending", "subscription not yet reported")
    t, q = (total or 0.0), (qib or 0.0)
    if t >= settings.DELIVERY_BRIEF_IPO_STRONG_DEMAND_X or q >= settings.DELIVERY_BRIEF_IPO_STRONG_QIB_X:
        return ("STRONG DEMAND",
                "Heavy demand — historically tends to list well, though never guaranteed.")
    if t < settings.DELIVERY_BRIEF_IPO_SOFT_DEMAND_X and q < settings.DELIVERY_BRIEF_IPO_SOFT_DEMAND_X:
        return ("SOFT DEMAND", "Light subscription so far — muted interest.")
    return ("MODERATE DEMAND", "Steady subscription interest.")


def _resolve_sector(ticker: str) -> str:
    """Seam over SectorRegistry so tests can inject (ticker -> sector key)."""
    from backend.sectors.registry import SectorRegistry
    return SectorRegistry.resolve(ticker)


def _load_ticker_dossier(ticker: str, sector: str):
    """Seam over PredictionStore.load_dossier so tests can inject."""
    from core.intelligence.rl.stores.prediction_store import PredictionStore
    return PredictionStore(ticker, sector=sector).load_dossier()


def _earnings_watch(symbol: str) -> str:
    """Latest open-guidance one-liner from the ticker's dossier, else ''.
    Best-effort — any failure (no sector/dossier/guidance) yields ''. Never raises."""
    try:
        sector = _resolve_sector(symbol)
        dossier = _load_ticker_dossier(symbol, sector)
        if dossier is None:
            return ""
        open_g = [g for g in getattr(dossier, "guidance", []) or []
                  if getattr(g, "status", "") == "open"]
        if not open_g:
            return ""
        return _trim_words(getattr(open_g[-1], "guidance", "") or "",
                           settings.DELIVERY_BRIEF_EARNINGS_WATCH_MAXLEN)
    except Exception as exc:
        logger.debug("[brief] earnings watch failed for %s (non-fatal): %s", symbol, exc)
        return ""


def _indent(text: str, width: int = 2) -> str:
    """Wrap prose to ~74 cols with a fixed left indent (email/push friendly)."""
    import textwrap
    pad = " " * width
    return textwrap.fill(" ".join((text or "").split()), width=74,
                         initial_indent=pad, subsequent_indent=pad)


_PROMPT = """You are the narration layer of a personal stock-research tool.
Write a 2-4 sentence morning headline (research tone; NEVER the word "advice")
summarising the portfolio state and what matters today.

Portfolio: {portfolio}
Escalations flagged yesterday: {escalations}
Market regime: {regime}
Overnight HIGH-severity items (numbered):
{overnight}
Earnings within 3 sessions: {earnings}
New discovery-shelf ideas: {adds}

Also produce "overnight_notes": one short line (<=12 words) per overnight item, in the
SAME numbered order, on why it matters to an Indian-equity investor. Empty list if none.

Respond with JSON: {{"headline": "<2-4 sentences>", "overnight_notes": ["<line 1>", ...]}}"""


# -- section collectors (each non-fatal, monkeypatchable) -------------------

def _read_regime() -> dict | None:
    try:
        path = Path(settings.PREDICTION_DATA_DIR) / "_regime_state.json"
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            return {"label": raw.get("label", "NORMAL"),
                    "calm_streak": raw.get("calm_streak", 0)}
    except Exception as exc:
        logger.warning("[brief] regime read failed (non-fatal): %s", exc)
    return None


def _overnight_items(max_items: int | None = None) -> list[dict]:
    try:
        from services.background.macro_news_cache import MacroNewsCache
        mi = max_items if max_items is not None else settings.DELIVERY_BRIEF_MAX_OVERNIGHT
        raw = MacroNewsCache().get_high_severity(hours_back=24)
        items: list[dict] = []
        for i in raw:
            # Prefer the clean one-sentence LLM summary; the raw title is often
            # a source-truncated snippet ("…Middle East con"). Title is fallback.
            text = (i.get("summary") or i.get("title") or "").strip()
            if not text:
                continue
            items.append({
                "headline": _clean_headline(text, settings.DELIVERY_BRIEF_OVERNIGHT_MAXLEN),
                "severity": i.get("severity", "HIGH"),
            })
        return _dedup_overnight(
            items, settings.DELIVERY_BRIEF_OVERNIGHT_DEDUP_THRESHOLD, mi,
            min_shared=settings.DELIVERY_BRIEF_OVERNIGHT_DEDUP_MIN_SHARED,
            stopwords=frozenset(settings.DELIVERY_BRIEF_OVERNIGHT_STOPWORDS))
    except Exception as exc:
        logger.warning("[brief] macro feed read failed (non-fatal): %s", exc)
        return []


def _shelf_events_since(since_iso: str) -> list[dict]:
    try:
        path = Path(settings.DISCOVERY_DATA_DIR) / "shelf_events.jsonl"
        if not path.exists():
            return []
        out = []
        for line in path.read_text(encoding="utf-8").splitlines()[-200:]:
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get("ts", "") >= since_iso and rec.get("event") in ("added", "promoted"):
                out.append({"event": rec["event"], "symbol": rec.get("symbol", ""),
                            "detail": rec.get("detail", "")})
        return out[-5:]
    except Exception as exc:
        logger.warning("[brief] shelf events read failed (non-fatal): %s", exc)
        return []


def _enrich_discovery_adds(adds: list[dict]) -> list[dict]:
    """Join each discovery add to its shelf idea, attaching the tool's own
    verdict/conviction + a one-line reason from the idea's thesis. Non-fatal:
    an unknown symbol stays a bare row (renders as a plain bullet)."""
    if not adds:
        return adds
    ideas: dict[str, object] = {}
    try:
        from core.discovery.shelf import ShelfStore
        for idea in ShelfStore().load().ideas:
            ideas[str(getattr(idea, "symbol", "")).upper()] = idea
    except Exception as exc:
        logger.debug("[brief] shelf read for idea enrichment failed (non-fatal): %s", exc)
    out: list[dict] = []
    for a in adds:
        row = dict(a)
        idea = ideas.get(str(a.get("symbol", "")).upper())
        if idea is not None:
            row["verdict"] = getattr(idea, "verdict", None)
            row["conviction"] = getattr(idea, "conviction", None)
            row["reason"] = _first_sentence(
                getattr(idea, "thesis", "") or "", settings.DELIVERY_BRIEF_IDEA_REASON_MAXLEN)
        out.append(row)
    return out


def _earnings_soon(symbols: list[str], on: date) -> list[dict]:
    try:
        calendar = load_events_calendar()
        out = []
        for sym in symbols:
            ev = next_results_event(sym, on, calendar)
            if ev is not None and (date.fromisoformat(ev.date) - on).days <= 3:
                out.append({"symbol": sym, "date": ev.date})
        return out
    except Exception as exc:
        logger.warning("[brief] earnings scan failed (non-fatal): %s", exc)
        return []


def _ipo_watch(max_items: int | None = None) -> list[dict]:
    try:
        cache = load_ipo_cache()
        mi = max_items if max_items is not None else settings.DELIVERY_BRIEF_MAX_IPOS
        rows = cache.get("current", []) + cache.get("upcoming", [])
        out = [{
            "symbol": r.get("symbol", ""), "company": r.get("company", ""),
            "status": r.get("status", ""), "qib_x": r.get("qib_x"),
            "retail_x": r.get("retail_x"), "total_x": r.get("total_x"),
            "issue_price": r.get("issue_price"),
        } for r in rows]
        return _dedup_ipos(out, mi)
    except Exception as exc:
        logger.warning("[brief] ipo watch failed (non-fatal): %s", exc)
        return []


def _narrate_brief(brief: dict) -> tuple[str, list[str]]:
    """ONE BULK call. Returns (headline, overnight_notes). Deterministic
    fallback on any failure = (fallback headline, []). No extra LLM calls —
    the overnight relevance notes ride the same request."""
    fallback = _fallback_headline(brief)
    started = time.time()
    try:
        from services.clients.llm_client import (
            JSON_MODE_EXTRA_BODY, get_llm_client, record_llm_call,
            salvage_truncated_json,
        )
        p = brief.get("portfolio") or {}
        overnight_lines = "\n".join(
            f"{idx}. {i['headline']}" for idx, i in enumerate(brief["overnight"], 1)) or "none"
        resp = get_llm_client().chat.completions.create(
            model=settings.LLM_MODEL_BULK,
            messages=[{"role": "user", "content": _PROMPT.format(
                portfolio=(f"value ₹{p.get('portfolio_value', 0):,.0f} "
                           f"({p.get('total_pnl_pct', 0.0):+.1f}%)") if p else "empty",
                escalations=", ".join(f["symbol"] for f in brief["advisor_flags"]) or "none",
                regime=(brief.get("regime") or {}).get("label", "unknown"),
                overnight=overnight_lines,
                earnings=", ".join(f"{e['symbol']} {e['date']}"
                                   for e in brief["earnings_soon"]) or "none",
                adds=", ".join(a["symbol"] for a in brief["discovery_adds"]) or "none",
            )}],
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=400,
            response_format={"type": "json_object"},
            extra_body=JSON_MODE_EXTRA_BODY,
        )
        raw = resp.choices[0].message.content or ""
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            data = salvage_truncated_json(raw)
        if not isinstance(data, dict):
            data = {}
        usage = getattr(resp, "usage", None)
        record_llm_call("morning_brief", settings.LLM_MODEL_BULK,
                        getattr(usage, "prompt_tokens", 0),
                        getattr(usage, "completion_tokens", 0),
                        int((time.time() - started) * 1000), True)
        raw_notes = data.get("overnight_notes", [])
        notes = [str(n).strip() for n in raw_notes] if isinstance(raw_notes, list) else []
        return (str(data.get("headline", "")).strip() or fallback, notes)
    except Exception as exc:
        logger.warning("[brief] narration failed (non-fatal): %s", exc)
        try:
            from services.clients.llm_client import record_llm_call
            record_llm_call(
                "morning_brief", settings.LLM_MODEL_BULK, 0, 0,
                int((time.time() - started) * 1000), False,
            )
        except Exception:
            pass
        return (fallback, [])


def _fallback_headline(brief: dict) -> str:
    p = brief.get("portfolio") or {}
    parts = []
    if p:
        parts.append(f"Portfolio ₹{p.get('portfolio_value', 0):,.0f} "
                     f"({p.get('total_pnl_pct', 0.0):+.1f}% overall).")
    esc = [f["symbol"] for f in brief.get("advisor_flags", [])]
    if esc:
        parts.append(f"Flags to review: {', '.join(esc)}.")
    regime = (brief.get("regime") or {}).get("label")
    if regime and regime != "NORMAL":
        parts.append(f"Regime: {regime}.")
    return " ".join(parts) or "No portfolio activity to report."


# -- builder + renderer + runner --------------------------------------------

def build_morning_brief(
    user_id: str, on: date, store: PortfolioStore | None = None
) -> dict:
    store = store or PortfolioStore(user_id=user_id)
    digest = store.load_latest_digest()
    portfolio = None
    advisor_flags: list[dict] = []
    held: list[str] = []
    if digest:
        portfolio = {k: digest.get(k) for k in
                     ("date", "portfolio_value", "total_pnl_pct", "escalations")}
        portfolio["portfolio_value"] = digest.get("portfolio_value", 0.0)
        held = [r["symbol"] for r in digest.get("holdings", [])]
        advisor_flags = [
            {"symbol": r["symbol"], "verdict": r["verdict"],
             "reason": r.get("reason", ""), "notes": r.get("notes", [])}
            for r in digest.get("holdings", [])
            if r.get("verdict") not in ("HOLD", "NO_DATA")
        ]

    prev = store.load_latest_brief()
    since = prev.get("generated_at", "") if prev else ""

    # Lock-in flags cover held + watchlist + active shelf names (spec §7:
    # "lock-in expiry on shelf name").
    watched: set[str] = set(held)
    try:
        watched |= {w.symbol for w in store.load().watchlist}
    except Exception:
        pass
    try:
        from core.discovery.shelf import ShelfStore
        watched |= {i.symbol for i in ShelfStore().load().ideas if i.status == "active"}
    except Exception as exc:
        logger.debug("[brief] shelf read for lock-in scan failed (non-fatal): %s", exc)

    brief = {
        "date": on.isoformat(),
        "user_id": user_id,
        "kind": "morning_brief",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "portfolio": portfolio,
        "advisor_flags": advisor_flags,
        "regime": _read_regime(),
        "overnight": _overnight_items(),
        "earnings_soon": _earnings_soon(held, on),
        "discovery_adds": _enrich_discovery_adds(_shelf_events_since(since)),
        "ipo_watch": _ipo_watch(),
        "lockin_flags": [
            e.model_dump() for e in upcoming_lockin_alerts(on, symbols=watched or None)
        ],
    }
    # Earnings "why": attach a best-effort dossier watch-line per held earnings.
    for e in brief["earnings_soon"]:
        e["watch"] = _earnings_watch(e.get("symbol", ""))

    # Headline + overnight relevance notes ride one narration call. Tolerate a
    # plain-str return (older monkeypatched callers/tests) as headline-only.
    narrated = _narrate_brief(brief)
    if isinstance(narrated, tuple):
        brief["headline"], overnight_notes = narrated
    else:
        brief["headline"], overnight_notes = narrated, []
    for idx, item in enumerate(brief["overnight"]):
        if idx < len(overnight_notes) and overnight_notes[idx]:
            item["note"] = overnight_notes[idx]
    return brief


def render_brief_text(brief: dict) -> str:
    """Sectioned, plain-English plain-text brief (redesign 2026-07-27).

    Renders identically in email, web-push, and the in-app Inbox. Each section
    auto-hides when empty. Never raises.
    """
    bar = "═" * 42
    L: list[str] = []
    try:
        hdr = date.fromisoformat(brief.get("date", "")).strftime("%d %b %Y")
    except Exception:
        hdr = brief.get("date", "")
    L += [bar, f"  MORNING BRIEF · {hdr}", bar, ""]

    headline = (brief.get("headline") or "").strip()
    if headline:
        L += ["SUMMARY", _indent(headline), ""]

    p = brief.get("portfolio")
    if p:
        pnl = p.get("total_pnl_pct", 0.0) or 0.0
        direction = "up" if pnl >= 0 else "down"
        flags = brief.get("advisor_flags", []) or []
        note = ("Nothing needs your attention today." if not flags
                else f"{len(flags)} holding(s) flagged — see below.")
        L += ["YOUR PORTFOLIO",
              f"  ₹{p.get('portfolio_value', 0):,.0f} — {direction} {abs(pnl):.1f}% since inception.",
              f"  {note}", ""]

    flags = brief.get("advisor_flags", []) or []
    if flags:
        L.append("NEEDS ATTENTION")
        for f in flags:
            verb = _VERDICT_PLAIN.get(f.get("verdict", ""), f.get("verdict", ""))
            reason = f.get("reason", "")
            L.append(f"  • {f['symbol']}  {verb}" + (f" — {reason}" if reason else ""))
        L.append("")

    regime = (brief.get("regime") or {}).get("label")
    if regime:
        word, gloss = _REGIME_PLAIN.get(regime, (regime.title(), ""))
        L += ["MARKET CONDITIONS",
              f"  {word} ({regime})" + (f" — {gloss}" if gloss else ""), ""]

    overnight = brief.get("overnight", []) or []
    if overnight:
        L.append("OVERNIGHT — HIGH-IMPACT NEWS")
        for i in overnight:
            L.append(f"  • {i['headline']}")
            note = (i.get("note") or "").strip()
            if note:
                L.append(f"      Why it matters: {note}")
        L.append("")

    earnings = brief.get("earnings_soon", []) or []
    if earnings:
        L.append("EARNINGS THIS WEEK   (your holdings)")
        for e in earnings:
            L.append(f"  • {e['symbol']}  — {_fmt_date(e['date'])}")
            watch = (e.get("watch") or "").strip()
            tail = f"watch: {watch}" if watch else "results & guidance are the next catalyst."
            L.append(f"      You hold this — {tail}")
        L.append("")

    adds = (brief.get("discovery_adds", []) or [])[: settings.DELIVERY_BRIEF_MAX_IDEAS]
    if adds:
        L += ["IDEAS THE TOOL IS RESEARCHING   (its own view — not personal advice)",
              "  The scanner flagged these; the tool rated each and is paper-testing the",
              "  thesis. Confidence = how strongly it backs its own call."]
        for a in adds:
            verdict, pct = a.get("verdict"), _pct(a.get("conviction"))
            head = f"  • {a['symbol']}"
            if verdict and pct:
                head += f"   {verdict} · {pct}"
            elif verdict:
                head += f"   {verdict}"
            L.append(head)
            if a.get("reason"):
                L.append(f"      {a['reason']}")
        L.append("")

    ipos = brief.get("ipo_watch", []) or []
    if ipos:
        L += ["IPOs OPEN NOW   (the tool's research view — not advice)",
              "  × = times the issue was subscribed; high QIB/overall = institutional interest."]
        for w in ipos:
            lean, reason = _ipo_lean(w)
            if lean == "data pending":
                L.append(f"  • {w['symbol']}  {w.get('company', '')}  ·  Lean: data pending — {reason}")
            else:
                L.append(f"  • {w['symbol']}  {w.get('company', '')}")
                L.append(f"      Lean: {lean} · {_ipo_demand(w)}")
                L.append(f"      {reason}")
        L.append("")

    lockin = brief.get("lockin_flags", []) or []
    if lockin:
        L.append("LOCK-IN EXPIRIES")
        L += [f"  • {lf['symbol']} {lf['kind']} on {lf['expiry']} — supply risk, not a signal"
              for lf in lockin]
        L.append("")

    L += ["─" * 42, "Research tool — information only, never personal advice."]
    return "\n".join(L).strip()


def run_morning_brief(on: date | None = None) -> dict:
    """Scheduler Job 13 / POST /delivery/run-brief entry point. Never raises."""
    on = on or date.today()
    if not is_trading_day(on):
        return {"status": "not_trading_day"}
    users = active_user_ids() or [settings.PORTFOLIO_DEFAULT_USER_ID]
    built = 0
    for user_id in users:
        try:
            store = PortfolioStore(user_id=user_id)
            brief = build_morning_brief(user_id, on, store=store)
            store.save_brief(brief)
            deliver(f"Morning brief — {on}", render_brief_text(brief),
                    url="/#/inbox/brief", user_id=user_id, kind="brief")
            if brief["lockin_flags"]:
                emit_alerts(
                    [AlertEvent(date=on.isoformat(), kind="lockin_expiry",
                                symbol=lf["symbol"],
                                message=f"{lf['kind']} lock-in expires {lf['expiry']} "
                                        "— supply risk, not a signal",
                                severity="warning")
                     for lf in brief["lockin_flags"]],
                    user_id=user_id, title=f"Lock-in expiries — {on}",
                )
            built += 1
        except Exception as exc:
            logger.warning("[brief] build failed for %s (non-fatal): %s", user_id, exc)
    return {"status": "completed", "users": built, "date": on.isoformat()}
