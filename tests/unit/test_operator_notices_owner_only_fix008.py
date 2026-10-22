"""FIX-008: operator notices reach only the owner; market notices reach everyone.

Invariants, stated from the outside:

- an owner and a member both hold push subscriptions. Each operator caller's
  notice reaches the owner's devices and the owner's mailbox once, and
  nothing reaches the member: no push, no email, no outbox row, nothing in the
  member's Inbox;
- each market caller still reaches both, each at the account's own address;
- a user id planted in a drift or quarantine notice never reaches the member;
- with no account at all, an operator notice goes to the default user and
  DELIVERY_EMAIL_TO once; a failed owner lookup never widens to members;
- the registered `error_backlog` entry, run through the real watchdog, the
  real registry and a real backlog over a real WARNING row, warns the owner
  once a day while an issue is untriaged, closes with one "resolved" notice,
  then stays silent; no notice carries the log line's text;
- every caller of the alert entry points is classified, so a new one fails
  until it is placed.

Transports are recorded at their lowest seams (pywebpush's `webpush` and
`smtplib.SMTP`); nothing leaves the process.
"""
from __future__ import annotations

import ast
import email
import json
import logging
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

from core.config import settings
from core.delivery import alerts, channels
from services.data.stores import user_store

REPO = Path(__file__).resolve().parents[2]
IST = ZoneInfo("Asia/Kolkata")
OWNER_EMAIL = "owner@example.invalid"
MEMBER_EMAIL = "member@example.invalid"
OWNER_ENDPOINTS = ("https://push.example.invalid/owner-phone",
                   "https://push.example.invalid/owner-laptop")
MEMBER_ENDPOINT = "https://push.example.invalid/member-phone"
PLANTED = "u_planted7f3a9c"             # a user id that must never reach the member
TEMPLATE_MARKER = "zebraquokka"         # survives normalisation, so it is in the template


class Wire:
    """What left through each transport, by recipient."""

    def __init__(self):
        self.pushes: list[tuple[str, dict]] = []      # (endpoint, payload)
        self.emails: list[tuple[str, str]] = []       # (recipient, decoded text)

    def push_count(self, endpoint: str) -> int:
        return sum(1 for ep, _ in self.pushes if ep == endpoint)

    def emails_to(self, address: str) -> list[str]:
        return [text for to, text in self.emails if to == address]

    def member_received(self) -> list[str]:
        return ([json.dumps(p) for ep, p in self.pushes if ep == MEMBER_ENDPOINT]
                + self.emails_to(MEMBER_EMAIL))

    def owner_received(self) -> list[str]:
        return ([json.dumps(p) for ep, p in self.pushes if ep in OWNER_ENDPOINTS]
                + self.emails_to(OWNER_EMAIL))


def _decoded(raw: str) -> str:
    msg = email.message_from_string(raw)
    parts = msg.walk() if msg.is_multipart() else [msg]
    out = [str(msg["Subject"])]
    for part in parts:
        payload = part.get_payload(decode=True)
        if payload:
            out.append(payload.decode("utf-8", "replace"))
    return "\n".join(out)


@pytest.fixture()
def wire(tmp_path, monkeypatch):
    """Delivery switched on with recording transports, Atlas off, and an empty
    users.db and push store of this test's own."""
    w = Wire()
    monkeypatch.setattr(user_store, "_DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(user_store, "_conn_holder", {"conn": None})
    for name, value in {"DELIVERY_ENABLED": True, "DELIVERY_PUSH_ENABLED": True,
                        "DELIVERY_EMAIL_ENABLED": True, "VAPID_PRIVATE_KEY": "test-vapid",
                        "EMAIL_TRANSPORT": "smtp", "RESEND_API_KEY": "",
                        "SMTP_HOST": "smtp.example.invalid", "SMTP_USER": "",
                        "DELIVERY_EMAIL_TO": OWNER_EMAIL, "APP_PUBLIC_URL": "",
                        "DELIVERY_DATA_DIR": str(tmp_path / "delivery")}.items():
        monkeypatch.setattr(settings, name, value)
    from services.data.stores import atlas_store
    monkeypatch.setattr(atlas_store, "enabled", lambda: False)

    def webpush(subscription_info, data, **_kw):
        w.pushes.append((subscription_info["endpoint"], json.loads(data)))

    class FakeSMTP:
        def __init__(self, *_a, **_kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def starttls(self):
            pass

        def login(self, *_a):
            pass

        def sendmail(self, _from, to_addrs, msg):
            for to in to_addrs:
                w.emails.append((to, _decoded(msg)))

    monkeypatch.setattr(channels, "webpush", webpush)
    monkeypatch.setattr(channels.smtplib, "SMTP", FakeSMTP)
    yield w
    if user_store._conn_holder.get("conn") is not None:
        user_store._conn_holder["conn"].close()


def _subscribe(user_id: str, *endpoints: str) -> None:
    store = channels.PushStore()
    for ep in endpoints:
        store.add({"endpoint": ep, "keys": {"p256dh": "k", "auth": "a"}}, user_id=user_id)


@pytest.fixture()
def accounts(wire):
    """The production shape: the first signup is the owner under the default
    portfolio id; an invited member; both with push on."""
    owner = user_store.create_user(OWNER_EMAIL, "pw-for-tests-1", "Owner", role="owner",
                                   user_id=settings.PORTFOLIO_DEFAULT_USER_ID)
    member = user_store.create_user(MEMBER_EMAIL, "pw-for-tests-1", "Member")
    _subscribe(owner["user_id"], *OWNER_ENDPOINTS)
    _subscribe(member["user_id"], MEMBER_ENDPOINT)
    return {"owner": owner, "member": member}


# ---------------------------------------------------------------------------
# the callers, each driven through its own real code
# ---------------------------------------------------------------------------

WATCHDOG_DAY = datetime(2026, 10, 13, 6, 30, tzinfo=IST)     # a Tuesday: no heartbeat


def _watchdog_registry_broken(tmp_path, monkeypatch):
    from core.ops.watchdog import runner as R
    monkeypatch.setattr(R, "_REGISTRY_PATH", tmp_path / "no-such-registry.yaml")
    monkeypatch.setattr(R, "_STATE_PATH", tmp_path / "watchdog_state.json")
    R.run_watchdog(now=WATCHDOG_DAY)


def _watchdog_entry_due(tmp_path, monkeypatch):
    from core.ops.watchdog import checks as C
    from core.ops.watchdog import runner as R
    from core.ops.watchdog.checks import CheckResult
    reg = tmp_path / "milestones.yaml"
    reg.write_text(yaml.safe_dump({"milestones": [
        {"id": "fix008_probe", "kind": "invariant", "title": "Probe", "check": "probe"}]}),
        encoding="utf-8")
    monkeypatch.setattr(R, "_REGISTRY_PATH", reg)
    monkeypatch.setattr(R, "_STATE_PATH", tmp_path / "watchdog_state.json")
    monkeypatch.setattr(C, "run_check", lambda name: CheckResult("pending", "probe pending"))
    out = R.run_watchdog(now=WATCHDOG_DAY)
    assert out["notified"] == 1


def _ops_job_crashed(tmp_path, monkeypatch):
    from core.delivery import ops_alerts
    ops_alerts.alert_job_crashed("daily_review", "RuntimeError: boom")


def _ops_partial_output(tmp_path, monkeypatch):
    from core.delivery import ops_alerts
    ops_alerts.alert_job_partial_output("daily_review", 13, 16, "skipped no_envelope: X")


def _audit_breach(tmp_path, monkeypatch):
    from core.audit import thresholds
    out = thresholds.emit_breaches([{"rule": "min_hit_rate_60d", "severity": "warning",
                                     "message": "hit rate 38% below 45%"}])
    assert out["emitted"] >= 1


def _ledger_drift(tmp_path, monkeypatch):
    from core.portfolio import reconcile
    reconcile._alert(PLANTED, ["cash 1000.00 != replay 900.00"])


def _portfolio_quarantined(tmp_path, monkeypatch):
    from core.portfolio.store import PortfolioStore
    store = PortfolioStore(user_id=PLANTED, base_dir=str(tmp_path / "portfolios"))
    store._portfolio_path().write_text("{not json", encoding="utf-8")
    store.load()
    assert list(store._dir.glob("portfolio.json.corrupt-*"))


def _universe_budget(tmp_path, monkeypatch):
    from core.portfolio import universe
    universe._emit_ops_alert("universe budget exceeded: 412 > 400 tickers")


def _atlas_etl_quarantine(tmp_path, monkeypatch):
    from scripts import atlas_etl
    atlas_etl._emit_ops_alert("atlas ETL quarantined 3 rows")


OPERATOR_CALLERS = {
    "watchdog registry broken": _watchdog_registry_broken,
    "watchdog entry due": _watchdog_entry_due,
    "ops job crashed": _ops_job_crashed,
    "ops partial output": _ops_partial_output,
    "audit breach": _audit_breach,
    "ledger drift": _ledger_drift,
    "portfolio quarantined": _portfolio_quarantined,
    "universe budget": _universe_budget,
    "atlas etl quarantine": _atlas_etl_quarantine,
}


class _FakeNSE:
    def listEquityStocksByIndex(self, index="NIFTY 50"):
        return {"data": [{"symbol": index}, {"symbol": "AAA"}, {"symbol": "CCC"}]}

    def exit(self):
        pass


def _index_reconstitution(tmp_path, monkeypatch):
    """Both symbols are shelf ideas: the shelf is shared, so the change is a
    market notice. A stock only some account holds or watches goes to that
    account alone (FIX-009, test_index_watch_own_accounts_fix009.py)."""
    import core.delivery.index_watch as iw
    cache = tmp_path / "idx.json"
    cache.write_text(json.dumps({"NIFTY 50": {"fetched_at": "old", "symbols": ["AAA", "BBB"]}}),
                     encoding="utf-8")
    monkeypatch.setattr(iw.settings, "DELIVERY_INDEX_WATCH", ["NIFTY 50"])
    monkeypatch.setattr(iw, "_make_nse_client", lambda: _FakeNSE())
    monkeypatch.setattr(iw, "_shelf_symbols", lambda: {"BBB", "CCC"})
    monkeypatch.setattr(iw, "_account_symbols", lambda: {})
    assert iw.run_index_watch(on=date(2026, 10, 12), cache_path=str(cache))["events"] == 2


def _discovery_shelf_add(tmp_path, monkeypatch):
    import core.discovery as disc
    from backend.shared.schemas.discovery import ScreenResult

    class Dive:
        symbol, conviction = "NEWCO", 0.71

    class Shelf:
        def apply_deep_dives(self, dives, on):
            return {"added": ["NEWCO"], "displaced": [], "skipped": []}

        def rotate_stale(self, on):
            return []

    monkeypatch.setattr(disc.settings, "DISCOVERY_IPO_ENABLED", False)
    monkeypatch.setattr(disc, "sync_recent", lambda **kw: {})
    monkeypatch.setattr(disc, "refresh_bulk_block", lambda **kw: {})
    monkeypatch.setattr(disc, "refresh_listing", lambda **kw: {})
    monkeypatch.setattr(disc, "run_screen", lambda on: ScreenResult(
        screen_date="2026-10-10", universe_size=1, shortlist_size=1, candidates=[]))
    monkeypatch.setattr(disc, "run_deep_dives", lambda cands, on: [Dive()])
    monkeypatch.setattr(disc, "ShelfStore", Shelf)
    monkeypatch.setattr(disc, "run_paper_reviews",
                        lambda on: {"reviewed": [], "failed": [], "skipped": []})
    assert disc.run_discovery_cycle(on=date(2026, 10, 10))["shelf"]["added"] == ["NEWCO"]


def _preopen_reforecast(tmp_path, monkeypatch):
    import services.scheduler.python.scheduler as sched
    monkeypatch.setattr(
        "core.intelligence.rl.workflows.preopen_check.run_preopen_check",
        lambda tickers=None: {"severity": 0.85, "direction": "risk_off",
                              "flagged": ["MARUTI"], "reforecasts": ["MARUTI"]})
    sched.AutomobileScheduler.__new__(sched.AutomobileScheduler)._preopen_shock_check_job()


MARKET_CALLERS = {
    "index reconstitution": _index_reconstitution,
    "discovery shelf add": _discovery_shelf_add,
    "pre-open re-forecast": _preopen_reforecast,
}


# ---------------------------------------------------------------------------
# operator notices: the owner, once; the member, nothing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("caller", sorted(OPERATOR_CALLERS))
def test_operator_notice_reaches_only_the_owner(caller, accounts, wire, tmp_path, monkeypatch):
    OPERATOR_CALLERS[caller](tmp_path, monkeypatch)
    assert wire.member_received() == []
    assert wire.push_count(MEMBER_ENDPOINT) == 0
    assert all(wire.push_count(ep) == 1 for ep in OWNER_ENDPOINTS), wire.pushes
    assert len(wire.emails_to(OWNER_EMAIL)) == 1          # the mailbox gets it once
    assert {to for to, _ in wire.emails} == {OWNER_EMAIL}


@pytest.mark.parametrize("caller", sorted(MARKET_CALLERS))
def test_market_notice_still_reaches_everyone(caller, accounts, wire, tmp_path, monkeypatch):
    MARKET_CALLERS[caller](tmp_path, monkeypatch)
    assert wire.push_count(MEMBER_ENDPOINT) == 1
    assert all(wire.push_count(ep) == 1 for ep in OWNER_ENDPOINTS)
    assert len(wire.emails_to(OWNER_EMAIL)) == 1
    assert len(wire.emails_to(MEMBER_EMAIL)) == 1         # at the member's own address


def _inbox(token: str) -> str:
    from fastapi.testclient import TestClient
    from services.api.server import app
    r = TestClient(app).get("/delivery/alerts?limit=500",
                            headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    return json.dumps(r.json())


@pytest.mark.parametrize("caller", ["ledger drift", "portfolio quarantined"])
def test_a_planted_user_id_never_reaches_the_member(caller, accounts, wire, tmp_path,
                                                    monkeypatch):
    OPERATOR_CALLERS[caller](tmp_path, monkeypatch)
    assert any(PLANTED in text for text in wire.owner_received())    # it did go out
    assert not any(PLANTED in text for text in wire.member_received())
    owner_tok = user_store.create_session(accounts["owner"]["user_id"], True)
    member_tok = user_store.create_session(accounts["member"]["user_id"], True)
    assert PLANTED in _inbox(owner_tok)
    assert PLANTED not in _inbox(member_tok)


def test_the_inbox_shows_each_account_only_its_own_records(accounts, wire, tmp_path,
                                                           monkeypatch):
    """The sent-log is shared. Records written without a user id belong to the
    default user, who is the owner."""
    log = alerts._sent_log_path(None)
    legacy = [{"date": "2026-07-01", "kind": "legacy_no_key", "symbol": "", "message": "a"},
              {"date": "2026-07-02", "kind": "legacy_blank", "symbol": "", "message": "b",
               "user_id": "", "delivered": True}]
    log.write_text("".join(json.dumps(r) + "\n" for r in legacy), encoding="utf-8")
    alerts.emit_alerts([alerts.AlertEvent(date="2026-10-12", kind="advisor_exit",
                                          symbol="OWNERCO", message="exit OWNERCO")],
                       user_id=accounts["owner"]["user_id"])
    alerts.emit_alerts([alerts.AlertEvent(date="2026-10-12", kind="advisor_exit",
                                          symbol="MEMBERCO", message="exit MEMBERCO")],
                       user_id=accounts["member"]["user_id"])
    _index_reconstitution(tmp_path, monkeypatch)

    def kinds(tok):
        return [(a["kind"], a.get("symbol")) for a in json.loads(_inbox(tok))["alerts"]]

    owner = kinds(user_store.create_session(accounts["owner"]["user_id"], True))
    member = kinds(user_store.create_session(accounts["member"]["user_id"], True))
    assert ("advisor_exit", "OWNERCO") in owner and ("advisor_exit", "MEMBERCO") not in owner
    assert {"legacy_no_key", "legacy_blank"} <= {k for k, _ in owner}
    assert ("advisor_exit", "MEMBERCO") in member and ("advisor_exit", "OWNERCO") not in member
    assert not {"legacy_no_key", "legacy_blank"} & {k for k, _ in member}
    for who in (owner, member):                 # market notices: one copy each
        assert sorted(s for k, s in who if k.startswith("index_")) == ["BBB", "CCC"]
    assert owner[-1] == ("legacy_no_key", "")   # still newest first


def test_the_outbox_path_queues_operator_notices_for_the_owner_only(accounts, wire, tmp_path,
                                                                     monkeypatch):
    """With Atlas on, deliver() queues one outbox row set per audience user."""
    from core.delivery import outbox
    from services.data.stores import atlas_store
    queued: list[str] = []
    monkeypatch.setattr(atlas_store, "enabled", lambda: True)
    monkeypatch.setattr(outbox, "enqueue_message",
                        lambda uid, *a, **kw: queued.append(uid) or 2)
    _ledger_drift(tmp_path, monkeypatch)
    assert queued == [accounts["owner"]["user_id"]]
    queued.clear()
    _index_reconstitution(tmp_path, monkeypatch)
    assert sorted(queued) == sorted([accounts["owner"]["user_id"],
                                     accounts["member"]["user_id"]])
    assert wire.pushes == [] and wire.emails == []        # queued, not sent inline


def test_without_accounts_the_default_user_is_the_owner(wire, tmp_path, monkeypatch):
    """AUTH off, before the first signup: no users.db row. An orphan push
    subscription under another id is not the owner."""
    _subscribe(settings.PORTFOLIO_DEFAULT_USER_ID, OWNER_ENDPOINTS[0])
    _subscribe("u_orphan01", MEMBER_ENDPOINT)
    _ledger_drift(tmp_path, monkeypatch)
    assert wire.push_count(OWNER_ENDPOINTS[0]) == 1 and wire.push_count(MEMBER_ENDPOINT) == 0
    assert [to for to, _ in wire.emails] == [OWNER_EMAIL]     # DELIVERY_EMAIL_TO, once
    assert alerts.owner_audience() == [settings.PORTFOLIO_DEFAULT_USER_ID]


def test_a_failed_owner_lookup_narrows_to_the_default_user(accounts, wire, tmp_path,
                                                           monkeypatch, caplog):
    def boom():
        raise sqlite3.OperationalError("database is locked")
    monkeypatch.setattr(alerts, "_owner_account_ids", boom)
    with caplog.at_level(logging.WARNING, logger="core.delivery.alerts"):
        assert alerts.owner_audience() == [settings.PORTFOLIO_DEFAULT_USER_ID]
    assert "owner lookup failed" in caplog.text
    _ledger_drift(tmp_path, monkeypatch)
    assert wire.member_received() == []
    assert len(wire.emails_to(OWNER_EMAIL)) == 1


def test_only_role_owner_accounts_are_the_owner_audience(wire):
    user_store.create_user("m1@example.invalid", "pw-for-tests-1", "M1")
    user_store.create_user("m2@example.invalid", "pw-for-tests-1", "M2")
    assert alerts.owner_audience() == [settings.PORTFOLIO_DEFAULT_USER_ID]
    owner = user_store.create_user("o@example.invalid", "pw-for-tests-1", "O", role="owner",
                                   user_id="u_owner0001")
    assert alerts.owner_audience() == [owner["user_id"]]


# ---------------------------------------------------------------------------
# the registered backlog entry, end to end
# ---------------------------------------------------------------------------

@pytest.fixture()
def backlog(tmp_path, monkeypatch):
    """A real telemetry.db holding one fresh WARNING row, read by the real
    backlog through the real `error_backlog` check."""
    from core.ops import error_backlog as eb
    from services.data.stores import log_store
    db = tmp_path / "telemetry.db"
    src = sqlite3.connect(str(db), isolation_level=None)
    src.executescript(log_store._SCHEMA)
    log_store._migrate(src)
    src.execute("INSERT INTO app_logs (ts, level, logger, message) VALUES (?, ?, ?, ?)",
                ((datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(), "WARNING",
                 "fix008.planted",
                 f"[fix008] {TEMPLATE_MARKER} handshake refused for user {PLANTED}"))
    src.close()
    conn = eb.open_registry(db)
    monkeypatch.setattr(eb, "_conn", conn)
    yield eb, conn
    conn.close()


def test_the_registered_backlog_entry_warns_the_owner_daily_then_closes_once(
        accounts, wire, backlog, tmp_path, monkeypatch):
    from core.ops.watchdog import checks as C
    from core.ops.watchdog import runner as R
    from core.ops.watchdog.checks import CheckResult
    from core.ops.watchdog.registry import load_registry
    eb, conn = backlog
    entry = next(e for e in load_registry(R._REGISTRY_PATH) if e.check == "error_backlog")
    real = C.run_check
    monkeypatch.setattr(C, "run_check", lambda name: real(name) if name == "error_backlog"
                        else CheckResult("satisfied", "not under test"))
    monkeypatch.setattr(R, "_STATE_PATH", tmp_path / "watchdog_state.json")

    def run(day: int) -> list[str]:
        before = len(wire.emails)
        R.run_watchdog(now=WATCHDOG_DAY + timedelta(days=day))
        return [text for _, text in wire.emails[before:]]

    first = run(0)
    assert len(first) == 1 and f"[watchdog] {entry.title}" in first[0]
    assert "Due now." in first[0] and "GET /ops/errors" in first[0]
    assert run(0) == []                                    # once a day
    assert len(run(1)) == 1                                # still untriaged: again
    fp = eb.issues(conn)[0]["fingerprint"]
    assert eb.triage(fp, status="acknowledged", conn=conn)["status"] == "acknowledged"
    closing = run(2)
    assert len(closing) == 1 and "Now satisfied" in closing[0]
    assert "Next step" not in closing[0]
    assert run(3) == [] and run(4) == []                   # then silence
    texts = wire.owner_received()
    assert len(wire.emails) == 3 and wire.member_received() == []
    assert not any(TEMPLATE_MARKER in t or PLANTED in t for t in texts)
    assert any(fp in t for t in texts)                     # the fingerprint names it


def test_the_registry_entry_names_the_triage_steps():
    doc = yaml.safe_load((REPO / "config" / "milestones.yaml").read_text(encoding="utf-8"))
    entries = [e for key in ("milestones", "invariants") for e in (doc.get(key) or [])
               if e.get("check") == "error_backlog"]
    assert len(entries) == 1
    e = entries[0]
    assert e["kind"] == "invariant" and e in doc["invariants"]
    assert "window" not in e and "deadline" not in e and "schedule" not in e   # daily
    for words in ("GET /ops/errors", "python scripts/prod_errors.py --base",
                  "acknowledged", "fixed", "wontfix"):
        assert words in e["action"], words


# ---------------------------------------------------------------------------
# every caller classified
# ---------------------------------------------------------------------------

OPERATOR_SITES = {
    ("core/ops/watchdog/runner.py", "_broadcast"),
    ("core/delivery/ops_alerts.py", "_emit"),
    ("core/delivery/ops_alerts.py", "alert_job_partial_output"),
    ("core/audit/thresholds.py", "emit_breaches"),
    ("core/portfolio/reconcile.py", "_alert"),
    ("core/portfolio/store.py", "PortfolioStore._alert_quarantine"),
    ("core/portfolio/universe.py", "_emit_ops_alert"),
    ("scripts/atlas_etl.py", "_emit_ops_alert"),
}
MARKET_SITES = {
    ("core/delivery/index_watch.py", "run_index_watch"),     # shelf ideas only (FIX-009)
    ("core/discovery/__init__.py", "run_discovery_cycle"),
    ("services/scheduler/python/scheduler.py",
     "AutomobileScheduler._preopen_shock_check_job"),
}
OWN_ACCOUNT_SITES = {           # an account's alert about its own portfolio
    ("core/delivery/brief.py", "run_morning_brief"),
    ("core/portfolio/pipeline.py", "run_post_review_pipeline"),
    ("core/delivery/index_watch.py", "run_index_watch"),     # held or watched (FIX-009)
}
_ENTRY_POINTS = {"emit_owner_alerts", "emit_alerts_broadcast", "emit_alerts",
                 "owner_audience", "alert_audience", "_emit_to"}


def _call_sites() -> set[tuple[str, str, str]]:
    found: set[tuple[str, str, str]] = set()
    for root in ("core", "services", "scripts", "src"):
        for path in sorted((REPO / root).rglob("*.py")):
            if {"node_modules", "__pycache__"} & set(path.parts):
                continue
            rel = path.relative_to(REPO).as_posix()
            tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=rel)
            names = {n: n for n in _ENTRY_POINTS}
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module == "core.delivery.alerts":
                    names.update({a.asname or a.name: a.name for a in node.names
                                  if a.name in _ENTRY_POINTS})
            stack: list[str] = []

            def visit(node):
                scoped = isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                if scoped:
                    stack.append(node.name)
                if isinstance(node, ast.Call):
                    f = node.func
                    callee = (names.get(f.id) if isinstance(f, ast.Name) else
                              f.attr if isinstance(f, ast.Attribute)
                              and f.attr in _ENTRY_POINTS else None)
                    if callee:
                        found.add((rel, ".".join(stack) or "<module>", callee))
                for child in ast.iter_child_nodes(node):
                    visit(child)
                if scoped:
                    stack.pop()
            visit(tree)
    return found


def test_every_alert_caller_is_classified():
    """A new caller fails here until it is placed: an operator notice uses
    emit_owner_alerts, a market notice emit_alerts_broadcast, an account's own
    alert emit_alerts with that account's id. Nothing outside alerts.py picks
    its own audience."""
    sites = _call_sites()
    outside = {s for s in sites if s[0] != "core/delivery/alerts.py"}
    assert outside == ({(p, f, "emit_owner_alerts") for p, f in OPERATOR_SITES}
                       | {(p, f, "emit_alerts_broadcast") for p, f in MARKET_SITES}
                       | {(p, f, "emit_alerts") for p, f in OWN_ACCOUNT_SITES})
    inside = {(f, c) for p, f, c in sites if p == "core/delivery/alerts.py"}
    assert inside == {("emit_owner_alerts", "_emit_to"), ("emit_owner_alerts", "owner_audience"),
                      ("emit_alerts_broadcast", "_emit_to"),
                      ("emit_alerts_broadcast", "alert_audience"),
                      ("_emit_to", "emit_alerts")}
    assert set(OPERATOR_CALLERS) and len(MARKET_CALLERS) == len(MARKET_SITES)
