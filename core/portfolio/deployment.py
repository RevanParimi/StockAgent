"""
Idle-cash deployment (SA-049): how much of a portfolio the autopilot keeps in
stocks, and why any cash below that stays idle.

Before this, the autopilot opened a position only through a SWITCH, and a
plain EXIT's proceeds waited in cash for good: on 27 Sep 2026 the owner's
₹10 L portfolio was 81% cash in 2 holdings. With `autopilot.deploy_idle_cash`
on, the executor (core/portfolio/autopilot.py `_deploy_idle_cash`) opens new
positions after the day's sells and switches, from the day's buy candidates
(core/discovery/candidates.py), best conviction first.

**The market regime sets the target.** The daily review's sticky regime label
(core/intelligence/regime/state.py) maps to a target invested share of total
equity (`autopilot.deploy_target_invested_pct`; owner, 1 Nov 2026):

  NORMAL, RISK_ON, MOMENTUM_EXTENDED, OVERSOLD (calm)   80%
  RISK_OFF                                              50%
  MACRO_CRISIS                                          no new positions

A day with no label recorded for it opens nothing, and so does a day the
review recorded without a label because the inputs that answered do not
establish one (FIX-023): "market regime unavailable for 2026-10-30: India VIX
did not answer; no new positions". A label made of fallback values, or the
detector's NORMAL default after an exception, is never recorded as a day's
regime.

**The rules decide how much; the ideas decide how many (owner, 4 Nov 2026).**
The target is the regime's share and nothing else, so it grows when the user
adds money. A new position asks for a share of equity, the NORMAL share over
`portfolio.target_holdings` (80% ÷ 12 ≈ 6.7%), in every regime: RISK_OFF only
stops sooner. SA-050's sizing rule keeps it within the position cap, its
sector's cap and the cash floor. Holdings are as many as the ideas that pass
the checks, up to `portfolio.max_holdings`. `portfolio.overrides` gives one
portfolio its own values, its own regime shares and its own switch.

**Examples.** ₹12 L in NORMAL: the target is ₹9.6 L and a position asks for
₹80,000, so 12 ideas at ₹1,000 end at 80 shares each and exactly the target.
₹50 L in NORMAL: a position asks for ₹3,33,333, or 333 shares at ₹1,000; twelve
come to ₹39.96 L, ₹4,000 short of the ₹40 L target, so a thirteenth opens and
₹43.29 L is invested. In RISK_OFF ₹12 L stops at ₹6 L, and nothing is ever sold
to get there.

**When to open another position** (`stop_reason`): never at `max_holdings` or
past the day's limit; otherwise while invested is below the target. A buy
therefore passes the target by at most one position, in every regime.

**The soft minimum.** `portfolio.min_holdings` is an aim in calm regimes, never
a reason to buy: the record says when it is not met and why ("8 holdings, below
the 10 aimed for: only 8 qualifying ideas"; "9 holdings, below the 10 aimed for:
target reached").

Pure apart from `recorded_regime` and `regime_gap`, which read the regime
state file.
"""
from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass
from datetime import date

from core.config import settings
from core.portfolio.sizing import inr

logger = logging.getLogger(__name__)

CALM = ("NORMAL", "RISK_ON", "MOMENTUM_EXTENDED", "OVERSOLD")

# Why an idea was not bought, as a count of ideas reads in the run's record:
# "3 ideas above entry band".
OUTCOME_WORDS = {
    "held": "already held",
    "sold": "sold after the latest deep dive",
    "gate": "withheld by the data gate",
    "price": "without a close for the review session",
    "before_dive": "priced at a close from before its latest deep dive or analysis",
    "surveillance": "not cleared by NSE's surveillance report",
    "band": "above entry band",
    "invalidated": "at or below invalidation",
    "size": "with no room under a cap or the cash floor",
    "ledger": "already in the ledger",
    "waiting": "qualifying but not bought today",
}


@dataclass(frozen=True)
class Breadth:
    """One portfolio's deployment settings: config, then its override."""
    deploy: bool
    min_holdings: int
    target_holdings: int
    max_holdings: int
    shares: dict[str, float]    # target invested share of equity, by regime label

    def position_inr(self, equity: float) -> float:
        """What one new position asks for at `equity`: the NORMAL share of it
        over the holdings aimed for, whatever today's regime. No NORMAL share
        configured asks for nothing, so nothing opens."""
        share = max(0.0, float(self.shares.get("NORMAL") or 0.0))
        return equity * share / 100.0 / max(1, self.target_holdings)


def breadth(user_id: str) -> Breadth:
    """`portfolio.*` and `autopilot.deploy_idle_cash`, with any key the
    portfolio's own entry in `portfolio.overrides` sets in their place. Its
    `deploy_target_invested_pct` replaces only the regimes it names."""
    own = (settings.PORTFOLIO_OVERRIDES or {}).get(user_id) or {}

    def pick(key, default):
        value = own.get(key) if isinstance(own, dict) else None
        return default if value is None else value

    b = Breadth(
        deploy=bool(pick("deploy_idle_cash", settings.AUTOPILOT_DEPLOY_IDLE_CASH)),
        min_holdings=int(pick("min_holdings", settings.PORTFOLIO_MIN_HOLDINGS)),
        target_holdings=int(pick("target_holdings", settings.PORTFOLIO_TARGET_HOLDINGS)),
        max_holdings=int(pick("max_holdings", settings.PORTFOLIO_MAX_HOLDINGS)),
        shares={**settings.AUTOPILOT_DEPLOY_TARGET_PCT,
                **{str(k).strip().upper(): float(v)
                   for k, v in (pick("deploy_target_invested_pct", {}) or {}).items()}},
    )
    if not b.min_holdings <= b.target_holdings <= b.max_holdings:
        logger.warning("[deployment] %s: holdings settings out of order (min %d, target %d, "
                       "max %d); the maximum still binds", user_id, b.min_holdings,
                       b.target_holdings, b.max_holdings)
    return b


def active(portfolio) -> bool:
    """Whether the autopilot deploys this portfolio's idle cash today: the
    autopilot on, the portfolio opted in with cash accounting, and the switch
    on for it."""
    return bool(settings.AUTOPILOT_ENABLED and portfolio.autopilot
                and portfolio.cash_deployable is not None
                and breadth(portfolio.user_id).deploy)


def recorded_regime(on: date) -> str | None:
    """The sticky market regime the daily review recorded for `on`, or None
    (a seam: tests answer it)."""
    from core.intelligence.regime.state import label_recorded_for
    return label_recorded_for(on.isoformat())


def regime_gap(on: date) -> str:
    """Why `recorded_regime(on)` is None (a seam): "market regime unavailable
    for 2026-10-30: India VIX did not answer", or "no market regime recorded
    for 2026-10-30"."""
    from core.intelligence.regime.state import unrecorded_reason
    return unrecorded_reason(on.isoformat())


@dataclass(frozen=True)
class Target:
    regime: str | None
    share_pct: float | None    # the regime's target share of equity; None = no target
    invested_inr: float        # rupees deployment works toward; 0 = open nothing
    min_holdings: int          # the soft minimum in force; 0 outside calm regimes
    closed: str                # why no position opens at all; "" when one may


def target(regime: str | None, equity: float, b: Breadth, floor_cash: float,
           gap: str = "") -> Target:
    """What deployment works toward today, at `equity` (total equity): the
    regime's share, within equity less the cash floor. `gap` says why there
    is no `regime` (`regime_gap`)."""
    if not regime:
        return Target(None, None, 0.0, 0,
                      f"{gap or 'no market regime recorded for the review day'}; "
                      "no new positions")
    share = b.shares.get(regime)
    if share is None:
        return Target(regime, None, 0.0, 0,
                      f"no target set for market regime {regime}: no new positions")
    if share <= 0:
        return Target(regime, float(share), 0.0, 0,
                      f"market regime {regime}: no new positions, cash held on purpose")
    want = min(share / 100.0 * equity, max(0.0, equity - floor_cash))
    return Target(regime, float(share), want, b.min_holdings if regime in CALM else 0, "")


def _pct(part: float, whole: float) -> float:
    return part / whole * 100.0 if whole > 0 else 0.0


def stop_reason(t: Target, b: Breadth, *, equity: float, invested: float, holdings: int,
                opened: int, max_new: int) -> str:
    """"" when deployment should open another position now, else why not."""
    if t.closed:
        return t.closed
    if t.invested_inr <= 0:
        return "no equity above the cash floor to invest"
    if holdings >= b.max_holdings:
        return f"{holdings} holdings, the maximum of {b.max_holdings}"
    if invested >= t.invested_inr:
        return (f"regime {t.regime}, target reached: {_pct(invested, equity):.1f}% invested "
                f"against a target of {_pct(t.invested_inr, equity):.1f}% "
                f"({inr(t.invested_inr)})")
    if opened >= max_new:
        return (f"{opened} new position{'s' if opened != 1 else ''} today, "
                f"the daily limit of {max_new}")
    return ""


def counted(outcomes: list[dict]) -> list[str]:
    """'3 ideas above entry band', one line per kind of non-buy."""
    counts = Counter(o["outcome"] for o in outcomes if o["outcome"] in OUTCOME_WORDS)
    return [f"{n} idea{'s' if n != 1 else ''} {OUTCOME_WORDS[k]}"
            for k, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]


def below_aim(t: Target, *, holdings: int, invested: float, stop: str, outcomes: list[dict]) -> str:
    """The soft minimum's sentence, "" when it is met or not in force. It
    reports and never buys: "8 holdings, below the 10 aimed for: only 8
    qualifying ideas"."""
    if not t.min_holdings or holdings >= t.min_holdings:
        return ""
    qualifying = sum(o["outcome"] in ("bought", "waiting") for o in outcomes)
    waiting = sum(o["outcome"] == "waiting" for o in outcomes)
    if t.invested_inr > 0 and invested >= t.invested_inr:
        why = "target reached"
    elif holdings + waiting >= t.min_holdings or (stop and not outcomes):
        why = stop      # enough ideas wait behind the daily limit, or none was looked at
    elif qualifying:
        why = f"only {qualifying} qualifying idea{'s' if qualifying != 1 else ''}"
    else:
        why = "no qualifying idea"
    return (f"{holdings} holding{'s' if holdings != 1 else ''}, below the {t.min_holdings} "
            f"aimed for: {why}")


def run_record(*, on: date, t: Target, b: Breadth, equity: float, invested_before: float,
               invested_after: float, holdings_before: int, holdings_after: int,
               cash_after: float, outcomes: list[dict], stop: str) -> dict:
    """The run's record: what was bought and, for every idea not bought and
    for the cash left idle, why. Kept in the day's digest."""
    qualifying = sum(o["outcome"] in ("bought", "waiting") for o in outcomes)
    reasons = [stop] if stop else ["no further qualifying idea"]
    aim = below_aim(t, holdings=holdings_after, invested=invested_after, stop=stop,
                    outcomes=outcomes)
    if aim:
        reasons.append(aim)
    reasons += counted(outcomes)
    return {
        "date": on.isoformat(),
        "regime": t.regime,
        "target_share_pct": t.share_pct,
        "target_inr": round(t.invested_inr, 2),
        "target_pct": round(_pct(t.invested_inr, equity), 1),
        "min_holdings": t.min_holdings,
        "target_holdings": b.target_holdings,
        "max_holdings": b.max_holdings,
        "position_inr": round(b.position_inr(equity), 2),
        "equity": round(equity, 2),
        "invested_before_pct": round(_pct(invested_before, equity), 1),
        "invested_after_pct": round(_pct(invested_after, equity), 1),
        "holdings_before": holdings_before,
        "holdings_after": holdings_after,
        "cash_after": round(cash_after, 2),
        "bought": [o["symbol"] for o in outcomes if o["outcome"] == "bought"],
        "qualifying": qualifying,
        "reasons": reasons,
        "ideas": outcomes,
    }
