"""
Compass Phase C — Morning Brief (spec §7): 08:50 IST, right after the 08:45
pre-open shock check. Deterministic assembly from existing artifacts; ONE
BULK-tier narration call for the headline (fallback text on any failure).
Research tone, never "advice" (spec §2).
"""
from __future__ import annotations

import html as _htmlmod
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

# -- HTML email renderer (clean-fintech, email-safe) — redesign 2026-07-30 -----
_FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
_HTML = {
    "page": "#e9eef3", "card": "#ffffff", "ink": "#0f172a", "body": "#334155",
    "muted": "#64748b", "hair": "#e4e9f0", "hair_soft": "#eef2f7",
    "accent": "#0f766e", "accent_deep": "#115e59", "neg": "#b91c1c", "pos": "#15803d",
    "warn": "#b45309", "hi_bg": "#fdeceb", "hi_ink": "#b91c1c",
    "pill_bg": "#ecfdf5", "pill_bd": "#a7f3d0", "pill_ink": "#0f766e", "kpi": "#f4faf9",
}


def _esc(s) -> str:
    return _htmlmod.escape("" if s is None else str(s))


def _inr(v) -> str:
    """Indian-format rupee, e.g. 556826.57 -> '5,56,827' (no decimals)."""
    try:
        n = int(round(float(v)))
    except (TypeError, ValueError):
        return "0"
    sign, n = ("-" if n < 0 else ""), abs(n)
    s = str(n)
    if len(s) <= 3:
        return sign + s
    head, tail = s[:-3], s[-3:]
    parts: list[str] = []
    while len(head) > 2:
        parts.insert(0, head[-2:]); head = head[:-2]
    parts.insert(0, head)
    return sign + ",".join(parts) + "," + tail


def _dark_css() -> str:
    """Progressive-enhancement dark overrides (clients honoring <style>+media)."""
    return ("@media (prefers-color-scheme:dark){"
            ".sa-page{background:#0a0f1a!important}"
            ".sa-card{background:#111a2b!important;border-color:#233149!important}"
            ".sa-ink{color:#f1f5f9!important}.sa-body{color:#cbd5e1!important}"
            ".sa-muted{color:#94a3b8!important}"
            ".sa-kpi{background:#0e1b22!important;border-color:#233149!important}"
            ".sa-foot{background:#0e1728!important}.sa-div{border-color:#233149!important}"
            ".sa-neg{color:#f87171!important}.sa-pos{color:#4ade80!important}}")


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


def _dedupe_notes(notes: list[str]) -> list[str]:
    """Blank a relevance note that near-duplicates an earlier one (Jaccard>=0.6 on
    normalized tokens) so 'why it matters' lines don't echo across items."""
    out: list[str] = []
    seen: list[set] = []
    for n in notes:
        toks = set(_norm_text(n).split())
        dup = any(toks and s and len(toks & s) / (len(toks | s) or 1) >= 0.6 for s in seen)
        out.append("" if dup else n)
        if not dup and toks:
            seen.append(toks)
    return out


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


def _ipo_window(row: dict, on: date) -> str:
    """Plain-English window line for one IPO row."""
    state = row.get("state", "unknown")
    if state == "open":
        try:
            days = (date.fromisoformat(row.get("issue_end", "")) - on).days
        except ValueError:
            return "open now"
        if days <= 0:
            return "closes today"
        if days == 1:
            return "closes tomorrow"
        return f"closes in {days} days"
    if state == "upcoming":
        try:
            opens = date.fromisoformat(row.get("issue_start", ""))
        except ValueError:
            return "opens soon"
        return f"opens {opens.day} {opens.strftime('%b')}"
    if state == "closed":
        return "bidding closed — awaiting listing"
    return ""


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
    # An issue that has not opened has no bids by definition. Calling that
    # "data pending" reads as a fault in the tool rather than a fact about
    # the calendar, which is exactly how the pre-P0 brief read.
    if row.get("state") == "upcoming":
        return ("not open yet", "Bidding has not started.")
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


def _portfolio_extras(digest: dict) -> dict:
    """Best/worst holding, count, all-below-cost, and the day's last realized exit,
    computed from the digest. Every key is optional — an empty/partial digest yields
    a subset (or {}) and the renderers degrade cleanly."""
    out: dict = {}
    rows = [h for h in (digest.get("holdings") or [])
            if isinstance(h.get("pnl_pct"), (int, float))]
    if rows:
        best = max(rows, key=lambda h: h["pnl_pct"])
        worst = min(rows, key=lambda h: h["pnl_pct"])
        out["holdings_count"] = len(rows)
        out["best"] = {"symbol": best.get("symbol", ""), "pnl_pct": best["pnl_pct"]}
        out["worst"] = {"symbol": worst.get("symbol", ""), "pnl_pct": worst["pnl_pct"]}
        out["all_below_cost"] = all(h["pnl_pct"] < 0 for h in rows)
    sells = [t for t in (digest.get("trades") or [])
             if t.get("side") == "SELL" and isinstance(t.get("pnl_pct"), (int, float))]
    if sells:
        last = sells[-1]
        out["last_exit"] = {"symbol": last.get("symbol", ""), "pnl_pct": last["pnl_pct"]}
    return out


def _indent(text: str, width: int = 2) -> str:
    """Wrap prose to ~74 cols with a fixed left indent (email/push friendly)."""
    import textwrap
    pad = " " * width
    return textwrap.fill(" ".join((text or "").split()), width=74,
                         initial_indent=pad, subsequent_indent=pad)


_PROMPT = """You are the narration layer of a personal stock-research tool.
Write a 2-4 sentence morning "headline": the market regime, the single overarching
THEME of today's news, and the portfolio's posture. Do NOT enumerate or restate the
individual overnight items (they are listed separately below as bullets). Research
tone; NEVER the word "advice".

Portfolio: {portfolio}
Escalations flagged yesterday: {escalations}
Market regime: {regime}
Overnight HIGH-severity items (numbered):
{overnight}
Earnings within 3 sessions: {earnings}
New discovery-shelf ideas: {adds}

Also produce "overnight_notes": one short line (<=12 words) per overnight item, in the
SAME numbered order, each stating a DISTINCT, portfolio-relevant consequence for an
Indian-equity investor. Do not repeat wording across notes. Empty list if none.

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


def _ipo_watch(max_items: int | None = None, on: date | None = None) -> list[dict]:
    try:
        from core.ipo.calendar import issue_state
        on = on or date.today()
        cache = load_ipo_cache()
        mi = max_items if max_items is not None else settings.DELIVERY_BRIEF_MAX_IPOS
        rows = cache.get("current", []) + cache.get("upcoming", [])
        out = []
        for r in rows:
            state = issue_state(r, on)
            if state == "listed":
                continue          # it has a tape now; the tracker owns it
            out.append({
                "symbol": r.get("symbol", ""), "company": r.get("company", ""),
                "status": r.get("status", ""), "state": state,
                "issue_start": r.get("issue_start", ""),
                "issue_end": r.get("issue_end", ""),
                "qib_x": r.get("qib_x"), "retail_x": r.get("retail_x"),
                "total_x": r.get("total_x"), "issue_price": r.get("issue_price"),
                "cutoff_share": r.get("cutoff_share"),
            })
        # Open issues first — they are the ones with a deadline attached.
        order = {"open": 0, "closed": 1, "upcoming": 2, "unknown": 3}
        out.sort(key=lambda r: order.get(r["state"], 9))
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
        portfolio.update(_portfolio_extras(digest))
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
    overnight_notes = _dedupe_notes(overnight_notes)
    for idx, item in enumerate(brief["overnight"]):
        if idx < len(overnight_notes) and overnight_notes[idx]:
            item["note"] = overnight_notes[idx]
    return brief


def render_brief_text(brief: dict) -> str:
    """Sectioned, plain-English plain-text brief (redesign 2026-07-27).

    Renders identically in email, web-push, and the in-app Inbox. Each section
    auto-hides when empty. Never raises.
    """
    # The IPO section renders window state ("closes tomorrow"), which is
    # relative to the day the brief is FOR, not the day it is rendered.
    on = date.fromisoformat(brief["date"]) if brief.get("date") else date.today()
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
        L += ["IPO WATCH   (the tool's research view — not advice)",
              "  × = times the issue was subscribed; high QIB/overall = institutional interest."]
        for w in ipos:
            lean, reason = _ipo_lean(w)
            window = _ipo_window(w, on)
            head = f"  • {w['symbol']}  {w.get('company', '')}"
            if window:
                head += f"  ·  {window}"
            L.append(head)
            if lean in ("data pending", "not open yet"):
                L.append(f"      {reason}")
            else:
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


def enrich_brief_for_api(brief: dict) -> dict:
    """Add plain-English strings for JSON clients (the in-app Inbox).

    The stored brief is the source of truth for RL grading and replay, so this
    returns a shallow copy with only the derived keys added — the argument is
    never mutated. Unknown enum values fall through to the raw string, matching
    render_brief_text(). A malformed brief whose advisor_flags is a list of
    non-dicts raises TypeError, the same way render_brief_text() does — the
    stored brief is written by us, so a shape that wrong is a bug worth
    surfacing rather than papering over.
    """
    out = dict(brief)
    flags = brief.get("advisor_flags") or []
    if flags:
        out["advisor_flags"] = [
            {**f, "verdict_plain": _VERDICT_PLAIN.get(f.get("verdict", ""),
                                                      f.get("verdict", ""))}
            for f in flags
        ]
    regime = brief.get("regime")
    if isinstance(regime, dict) and regime.get("label"):
        word, gloss = _REGIME_PLAIN.get(regime["label"],
                                        (str(regime["label"]).title(), ""))
        out["regime"] = {**regime, "label_plain": word, "gloss": gloss}
    return out


def render_brief_html(brief: dict) -> str:
    """Styled, email-safe HTML brief (redesign 2026-07-30). Full standalone
    document; tables + inline styles + system fonts, dark via <style> media.
    Mirrors render_brief_text section-for-section; never raises."""
    try:
        return _render_brief_html_inner(brief, _HTML)
    except Exception as exc:
        logger.warning("[brief] html render failed (non-fatal): %s", exc)
        safe = _esc(render_brief_text(brief)).replace("\n", "<br>")
        return ("<!doctype html><html><body style=\"font-family:%s\">"
                "<pre style=\"font-family:%s\">%s</pre></body></html>" % (_FONT, _FONT, safe))


def _section(title: str, inner_html: str, H: dict) -> str:
    return (
        '<tr><td style="padding:20px 26px">'
        f'<div class="sa-ink" style="font:700 11.5px {_FONT};letter-spacing:.13em;'
        f'text-transform:uppercase;color:{H["accent"]};margin:0 0 12px">{_esc(title)}'
        f'<div style="height:2px;width:26px;background:{H["accent"]};border-radius:2px;'
        'margin:7px 0 0;opacity:.55"></div></div>'
        f'{inner_html}</td></tr>'
        f'<tr><td style="padding:0 26px"><div class="sa-div" '
        f'style="height:1px;background:{H["hair"]}"></div></td></tr>'
    )


def _html_rows(trs: str) -> str:
    return f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{trs}</table>'


def _render_brief_html_inner(brief: dict, H: dict) -> str:
    on = date.fromisoformat(brief["date"]) if brief.get("date") else date.today()
    try:
        hdr = date.fromisoformat(brief.get("date", "")).strftime("%A, %d %B %Y")
    except Exception:
        hdr = brief.get("date", "")

    rows: list[str] = []

    # SUMMARY
    headline = (brief.get("headline") or "").strip()
    if headline:
        rows.append(
            '<tr><td style="padding:22px 26px">'
            f'<p class="sa-body" style="margin:0;font:400 15px/1.6 {_FONT};color:{H["body"]}">'
            f'{_esc(headline)}</p></td></tr>'
            f'<tr><td style="padding:0 26px"><div class="sa-div" style="height:1px;background:{H["hair"]}"></div></td></tr>')

    # YOUR PORTFOLIO (KPI card)
    p = brief.get("portfolio")
    if p:
        pnl = p.get("total_pnl_pct", 0.0) or 0.0
        arrow = "▲" if pnl >= 0 else "▼"
        chip_cls, chip_ink = ("sa-pos", H["pos"]) if pnl >= 0 else ("sa-neg", H["neg"])
        chip_bg = H["pill_bg"] if pnl >= 0 else H["hi_bg"]
        meta_bits = []
        if p.get("holdings_count"):
            cost = "all currently below cost" if p.get("all_below_cost") else "mixed vs cost"
            meta_bits.append(f'<b style="color:{H["body"]}">{p["holdings_count"]} holdings</b>, {cost}.')
        if p.get("best"):
            meta_bits.append(f'Best <b style="color:{H["body"]}">{_esc(p["best"]["symbol"])} {p["best"]["pnl_pct"]:+.1f}%</b>')
        if p.get("worst"):
            meta_bits.append(f'Worst <b style="color:{H["body"]}">{_esc(p["worst"]["symbol"])} {p["worst"]["pnl_pct"]:+.1f}%</b>')
        meta = (' <span style="color:%s">·</span> ' % H["hair"]).join(meta_bits)
        exit_line = ""
        if p.get("last_exit"):
            le = p["last_exit"]
            exit_line = (f'<p class="sa-muted" style="margin:12px 0 0;font:400 13px/1.5 {_FONT};color:{H["muted"]}">'
                         f'Yesterday: autopilot exited <b style="color:{H["body"]}">{_esc(le["symbol"])} {le["pnl_pct"]:+.1f}%</b> on a thesis break.</p>')
        inner = (
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="sa-kpi" '
            f'style="background:{H["kpi"]};border:1px solid {H["hair"]};border-radius:12px"><tr><td style="padding:18px 20px">'
            f'<div class="sa-ink" style="font:700 34px {_FONT};color:{H["ink"]};letter-spacing:-.02em">₹{_inr(p.get("portfolio_value", 0))}</div>'
            f'<div style="margin:12px 0 0"><span class="{chip_cls}" style="display:inline-block;font:600 12.5px {_FONT};'
            f'color:{chip_ink};background:{chip_bg};padding:4px 10px;border-radius:999px">'
            f'{arrow} {abs(pnl):.1f}% since inception</span></div>'
            + (f'<p class="sa-muted" style="margin:14px 0 0;font:400 13.5px/1.55 {_FONT};color:{H["muted"]}">{meta}</p>' if meta else "")
            + exit_line
            + '</td></tr></table>')
        rows.append(_section("Your portfolio", inner, H))

    # NEEDS ATTENTION
    flags = brief.get("advisor_flags", []) or []
    if flags:
        items = []
        for f in flags:
            verb = _VERDICT_PLAIN.get(f.get("verdict", ""), f.get("verdict", ""))
            reason = f.get("reason", "")
            items.append(
                f'<div style="padding:8px 0"><span class="sa-ink" style="font:600 14.5px {_FONT};color:{H["ink"]}">'
                f'{_esc(f["symbol"])}</span> <span style="color:{H["warn"]};font:600 13px {_FONT}">{_esc(verb)}</span>'
                + (f'<div class="sa-muted" style="font:400 13px/1.5 {_FONT};color:{H["muted"]};margin:3px 0 0">{_esc(reason)}</div>' if reason else "")
                + '</div>')
        rows.append(_section("Needs attention", "".join(items), H))

    # MARKET CONDITIONS
    regime = (brief.get("regime") or {}).get("label")
    if regime:
        word, gloss = _REGIME_PLAIN.get(regime, (regime.title(), ""))
        inner = (
            f'<span style="display:inline-block;background:{H["pill_bg"]};border:1px solid {H["pill_bd"]};'
            f'color:{H["pill_ink"]};font:700 13px {_FONT};padding:6px 12px;border-radius:999px">{_esc(word)} · {_esc(regime)}</span>'
            + (f'<p class="sa-muted" style="margin:10px 0 0;font:400 13.5px/1.5 {_FONT};color:{H["muted"]}">{_esc(gloss)}</p>' if gloss else ""))
        rows.append(_section("Market conditions", inner, H))

    # OVERNIGHT (table with severity chip)
    overnight = brief.get("overnight", []) or []
    if overnight:
        trs = []
        for i in overnight:
            note = (i.get("note") or "").strip()
            why = (f'<div class="sa-muted" style="font:400 13px/1.5 {_FONT};color:{H["muted"]};margin:4px 0 0">'
                   f'<span style="color:{H["accent"]};font-weight:600">Why it matters:</span> {_esc(note)}</div>') if note else ""
            trs.append(
                f'<tr><td style="padding:12px 0;border-top:1px solid {H["hair_soft"]};vertical-align:top">'
                f'<div class="sa-ink" style="font:600 14.5px/1.45 {_FONT};color:{H["ink"]}">{_esc(i["headline"])}</div>{why}</td>'
                f'<td style="padding:12px 0 12px 12px;text-align:right;width:54px;vertical-align:top">'
                f'<span style="display:inline-block;font:700 10.5px {_FONT};letter-spacing:.06em;padding:3px 8px;'
                f'border-radius:6px;background:{H["hi_bg"]};color:{H["hi_ink"]}">{_esc(i.get("severity", "HIGH"))}</span></td></tr>')
        rows.append(_section("Overnight · high-impact news", _html_rows("".join(trs)), H))

    # EARNINGS
    earnings = brief.get("earnings_soon", []) or []
    if earnings:
        trs = []
        for e in earnings:
            watch = (e.get("watch") or "").strip()
            tail = f"watch: {watch}" if watch else "results & guidance are the next catalyst."
            trs.append(
                f'<tr><td style="padding:12px 0;border-top:1px solid {H["hair_soft"]};vertical-align:top">'
                f'<div class="sa-ink" style="font:600 14.5px {_FONT};color:{H["ink"]}">{_esc(e["symbol"])}</div>'
                f'<div class="sa-muted" style="font:400 13px/1.5 {_FONT};color:{H["muted"]};margin:4px 0 0">You hold this — {_esc(tail)}</div></td>'
                f'<td class="sa-ink" style="padding:12px 0;text-align:right;white-space:nowrap;width:96px;color:{H["ink"]};font:600 14px {_FONT}">{_esc(_fmt_date(e["date"]))}</td></tr>')
        rows.append(_section("Earnings this week · your holdings", _html_rows("".join(trs)), H))

    # IDEAS
    adds = (brief.get("discovery_adds", []) or [])[: settings.DELIVERY_BRIEF_MAX_IDEAS]
    if adds:
        trs = []
        for a in adds:
            verdict, pct = a.get("verdict"), _pct(a.get("conviction"))
            tag = (f'<span style="color:{H["accent"]};font:600 12.5px {_FONT}">{_esc(verdict)}'
                   + (f' · {pct}' if pct else "") + '</span>') if verdict else ""
            reason = a.get("reason", "")
            trs.append(
                f'<tr><td style="padding:12px 0;border-top:1px solid {H["hair_soft"]};vertical-align:top">'
                f'<div class="sa-ink" style="font:600 14.5px {_FONT};color:{H["ink"]}">{_esc(a["symbol"])} &nbsp;{tag}</div>'
                + (f'<div class="sa-muted" style="font:400 13px/1.5 {_FONT};color:{H["muted"]};margin:4px 0 0">{_esc(reason)}</div>' if reason else "")
                + '</td></tr>')
        rows.append(_section("Ideas the tool is researching · its own view, not advice", _html_rows("".join(trs)), H))

    # IPOs
    ipos = brief.get("ipo_watch", []) or []
    if ipos:
        trs = []
        for w in ipos:
            lean, reason = _ipo_lean(w)
            window = _ipo_window(w, on)
            demand = _ipo_demand(w) if lean not in ("data pending", "not open yet") else reason
            price = f'₹{_inr(w.get("issue_price"))}' if w.get("issue_price") else ""
            lean_color = H["warn"] if lean in ("data pending", "not open yet", "SOFT DEMAND") else H["accent"]
            leancol = f'<span style="color:{lean_color};font-weight:600">{_esc(lean)}</span>'
            trs.append(
                '<tr><td style="padding:12px 0">'
                f'<div class="sa-ink" style="font:600 14.5px {_FONT};color:{H["ink"]}">{_esc(w["symbol"])} '
                f'<span class="sa-muted" style="color:{H["muted"]};font-weight:600;font-size:12.5px">{_esc(w.get("company", ""))}</span></div>'
                f'<div class="sa-muted" style="font:400 13px/1.5 {_FONT};color:{H["muted"]};margin:4px 0 0">{_esc(window)}</div>'
                f'<div class="sa-muted" style="font:400 13px/1.5 {_FONT};color:{H["muted"]};margin:2px 0 0">Lean: {leancol} — {_esc(demand)}</div></td>'
                f'<td class="sa-ink" style="padding:12px 0;text-align:right;white-space:nowrap;width:96px;color:{H["ink"]};font:600 14px {_FONT}">{price}</td></tr>')
        rows.append(_section("IPO watch · research view, not advice", _html_rows("".join(trs)), H))

    # LOCK-IN
    lockin = brief.get("lockin_flags", []) or []
    if lockin:
        trs = []
        for lf in lockin:
            trs.append(
                f'<tr><td style="padding:12px 0;border-top:1px solid {H["hair_soft"]};vertical-align:top">'
                f'<div class="sa-ink" style="font:600 14.5px {_FONT};color:{H["ink"]}">{_esc(lf["symbol"])} '
                f'<span class="sa-muted" style="color:{H["muted"]};font-weight:600;font-size:12.5px">{_esc(lf.get("kind", ""))}</span></div>'
                f'<div class="sa-muted" style="font:400 13px/1.5 {_FONT};color:{H["muted"]};margin:4px 0 0">Supply risk as shares free up — context, not a signal.</div></td>'
                f'<td class="sa-ink" style="padding:12px 0;text-align:right;white-space:nowrap;width:96px;color:{H["ink"]};font:600 14px {_FONT}">{_esc(_fmt_date(lf.get("expiry", "")))}</td></tr>')
        rows.append(_section("Lock-in expiries", _html_rows("".join(trs)), H))

    body_rows = "".join(rows)

    button = ""
    url = (getattr(settings, "APP_PUBLIC_URL", "") or "").rstrip("/")
    if url:
        button = (f'<a href="{_esc(url)}/" style="display:inline-block;background:{H["accent_deep"]};'
                  f'color:#ffffff;text-decoration:none;font:600 14px {_FONT};padding:11px 20px;border-radius:9px">Open StockAgent →</a>')

    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="color-scheme" content="light dark">'
        f'<style>{_dark_css()}</style></head>'
        f'<body class="sa-page" style="margin:0;background:{H["page"]};-webkit-text-size-adjust:100%">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="sa-page" '
        f'style="background:{H["page"]}"><tr><td align="center" style="padding:22px 12px 40px">'
        '<table role="presentation" width="600" cellpadding="0" cellspacing="0" class="sa-card" '
        f'style="max-width:600px;width:100%;background:{H["card"]};border:1px solid {H["hair"]};'
        'border-radius:14px;overflow:hidden">'
        f'<tr><td style="background:{H["accent_deep"]};padding:20px 26px">'
        f'<div style="font:600 11px {_FONT};letter-spacing:.16em;text-transform:uppercase;color:#c7f2ea">StockAgent · Personal research</div>'
        f'<div style="font:700 22px {_FONT};color:#ffffff;margin:4px 0 0;letter-spacing:-.01em">Morning Brief</div>'
        f'<div style="font:500 13px {_FONT};color:#a9e5db;margin:6px 0 0">{_esc(hdr)}</div></td></tr>'
        f'{body_rows}'
        f'<tr><td class="sa-foot" style="background:{H["hair_soft"]};padding:20px 26px 24px">'
        f'<p class="sa-muted" style="margin:0 0 14px;font:400 12px/1.5 {_FONT};color:{H["muted"]}">'
        'Research tool — information only, <b>never personal advice</b>. '
        'Figures are model estimates from your paper portfolio and public sources.</p>'
        f'{button}'
        f'<p class="sa-muted" style="margin:16px 0 0;font:400 11px {_FONT};color:{H["muted"]};letter-spacing:.04em">StockAgent · morning brief</p>'
        '</td></tr>'
        '</table></td></tr></table></body></html>')


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
            text = render_brief_text(brief)
            html_body = None
            if settings.DELIVERY_BRIEF_HTML_ENABLED:
                try:
                    html_body = render_brief_html(brief)
                except Exception as exc:      # defence in depth (renderer already guards)
                    logger.warning("[brief] html render failed, sending text-only (non-fatal): %s", exc)
            deliver(f"Morning brief — {on}", text, url="/#/inbox/brief",
                    user_id=user_id, kind="brief", html_body=html_body)
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
