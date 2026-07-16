# Audit Wave A — Urgent Reliability (AUD-084 + AUD-085 riders) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A slow/partial review day can no longer silently kill the whole trading day (AUD-084), and the delivery layer can no longer cement a failed send in its dedupe log or silently drop notifications (AUD-085 code riders + AUD-090 a/b/c observability lines).

**Architecture:** Contain the harvest `TimeoutError` inside `_daily_review_job` so the zero-output alert and `run_post_review_pipeline` always run on whatever reviews persisted; add an APScheduler `EVENT_JOB_ERROR` listener as belt-and-braces paging for the whole escaping-exception class (email transport is now live in prod). In the delivery layer, write the sent-log AFTER the delivery outcome with a `delivered` flag (undelivered records don't dedupe → same-day retry works once a transport appears), warn loudly when a send lands nowhere, and prune permanently-dead push subscriptions (400/403 join 404/410).

**Tech Stack:** Python 3.11, APScheduler 3.x, pytest + monkeypatch (existing test style), concurrent.futures.

**Prod context (evidence):** Tue 2026-07-14 — `TimeoutError: 3 (of 16) futures unfinished` at 17:21 IST escaped the harvest loop → 13 reviews saved, 0 trades, no value point, no digest, zero alerts. All 8 deliveries over 4 days logged `push=0 email=0`; one stale push subscription now fails 400 on every send. Email transport went live 2026-07-16 (Gmail SMTP in Railway) — these fixes make it actually receive the pages.

## Global Constraints

- Never let telemetry/alerting take down the job it watches — every new helper wraps in try/except and logs at debug/warning (house pattern, see `core/delivery/ops_alerts.py` docstring).
- The portfolio pipeline hook must run even when reviews partially fail — reviews are persisted per-ticker (AUD-043 invariant).
- No behavior change to dedupe semantics for already-written sent-log records: records WITHOUT a `delivered` key are legacy = treated as delivered.
- Keep committed text free of prod host/endpoint/cash specifics (public repo — audit program rule).
- Full-suite baseline to preserve: 10 failed / 10 errors / ~2181 passed / 12 skipped (AUD-022 stale mocks + 1 pre-existing event_ingestor date test).
- Work in a worktree branch `audit-wave-a-reliability`; ff-merge to main when green.

## File Structure

- `core/delivery/ops_alerts.py` — add `alert_job_partial_output()` (AUD-090b) and `alert_job_crashed()` (AUD-084 listener target).
- `services/scheduler/python/scheduler.py` — harvest containment + partial-alert call in `_daily_review_job`; `_on_job_error` listener registered in `_build_scheduler`.
- `core/delivery/alerts.py` — sent-log written after outcome with `delivered` flag; `_seen_keys` skips `delivered=False`.
- `core/delivery/channels.py` — prune 400/403; zero-subscription WARNING; deliver landed-nowhere WARNING.
- `core/portfolio/reconcile.py` — one INFO line on clean pass (AUD-090a).
- Tests: `tests/unit/test_ops_alerts.py`, `tests/unit/test_scheduler_portfolio_hook.py`, `tests/unit/test_delivery_alerts.py`, `tests/unit/test_delivery_channels.py`, `tests/unit/test_portfolio_reconcile.py` (all existing files, append/modify).

---

### Task 1: ops_alerts — partial-output + job-crashed helpers

**Files:**
- Modify: `core/delivery/ops_alerts.py` (append after `alert_job_zero_output`, ~line 100)
- Test: `tests/unit/test_ops_alerts.py` (append)

**Interfaces:**
- Consumes: existing `_emit(kind, message)` module helper; `AlertEvent`/`emit_alerts` from `core.delivery.alerts`.
- Produces: `alert_job_partial_output(job: str, produced: int, expected: int) -> None` (warning-severity alert when `0 < produced < expected`), `alert_job_crashed(job: str, error: str) -> None` (critical alert). Task 2 and Task 3 call these via late import.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_ops_alerts.py`. Note the autouse `_isolated_state` fixture already spies `_emit`; `alert_job_partial_output` emits WARNING severity so it calls `emit_alerts` directly, not `_emit` — spy it separately.

```python
def test_partial_output_job_alerts_warning(_isolated_state, monkeypatch):
    """AUD-090b: 13/16 after a harvest timeout was invisible — zero-output only
    fires at produced==0."""
    import core.delivery.alerts as al
    sent = []
    monkeypatch.setattr(al, "emit_alerts",
                        lambda events, **kw: sent.append(events[0]) or {"emitted": 1})
    ops.alert_job_partial_output("daily_review", produced=13, expected=16)
    assert len(sent) == 1
    assert sent[0].kind == "job_partial_output_daily_review"
    assert sent[0].severity == "warning"
    assert "13/16" in sent[0].message


def test_partial_output_silent_on_full_zero_or_empty(_isolated_state, monkeypatch):
    import core.delivery.alerts as al
    sent = []
    monkeypatch.setattr(al, "emit_alerts",
                        lambda events, **kw: sent.append(events[0]) or {"emitted": 1})
    ops.alert_job_partial_output("j", produced=16, expected=16)   # full — silent
    ops.alert_job_partial_output("j", produced=0, expected=16)    # zero-output's job
    ops.alert_job_partial_output("j", produced=3, expected=0)     # nothing expected
    assert sent == []


def test_job_crashed_alert(_isolated_state):
    sent = _isolated_state
    ops.alert_job_crashed("rl_daily_review", "TimeoutError: 3 futures unfinished")
    assert len(sent) == 1 and sent[0][0] == "job_crashed_rl_daily_review"
    assert "TimeoutError" in sent[0][1]


def test_new_helpers_never_raise(monkeypatch):
    import core.delivery.alerts as al

    def boom(*a, **k):
        raise RuntimeError("delivery down")
    monkeypatch.setattr(al, "emit_alerts", boom)
    monkeypatch.setattr(ops, "_emit", boom)
    ops.alert_job_partial_output("j", produced=1, expected=5)   # must not raise
    ops.alert_job_crashed("j", "boom")                          # must not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_ops_alerts.py -v`
Expected: the 4 new tests FAIL with `AttributeError: module 'core.delivery.ops_alerts' has no attribute 'alert_job_partial_output'` (existing 4 still pass).

- [ ] **Step 3: Implement**

Append to `core/delivery/ops_alerts.py`:

```python
def alert_job_partial_output(job: str, produced: int, expected: int) -> None:
    """A job that completed only PART of its input (e.g. 13/16 reviews after a
    harvest timeout, AUD-084/090b) is invisible to the zero-output alert.
    Warning severity — the day still ran; same-day repeats deduped by the
    alerts layer (date|kind key)."""
    try:
        if expected <= 0 or produced <= 0 or produced >= expected:
            return
        from core.delivery.alerts import AlertEvent, emit_alerts
        emit_alerts([AlertEvent(
            date=date.today().isoformat(),
            kind=f"job_partial_output_{job}", symbol="",
            message=(f"Job '{job}' completed {produced}/{expected} — the rest "
                     "timed out or failed. Check logs."),
            severity="warning")],
            title="StockAgent ops alert")
    except Exception as exc:
        logger.debug("[ops_alerts] alert_job_partial_output failed (non-fatal): %s", exc)


def alert_job_crashed(job: str, error: str) -> None:
    """An exception escaped a scheduled job entirely (AUD-084 listener class):
    everything after the crash point — alerts, portfolio pipeline — did not
    run. Same-day repeats deduped by the alerts layer (date|kind key)."""
    try:
        _emit(f"job_crashed_{job}",
              f"Scheduled job '{job}' CRASHED: {error[:300]} — steps after the "
              "crash (alerts / portfolio pipeline) did not run. Check logs.")
    except Exception as exc:
        logger.debug("[ops_alerts] alert_job_crashed failed (non-fatal): %s", exc)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_ops_alerts.py -v`
Expected: all 8 PASS.

- [ ] **Step 5: Commit**

```bash
git add core/delivery/ops_alerts.py tests/unit/test_ops_alerts.py
git commit -m "feat(ops-alerts): partial-output + job-crashed alert helpers (AUD-084/090b)"
```

---

### Task 2: Scheduler — contain the harvest TimeoutError (AUD-084 core)

**Files:**
- Modify: `services/scheduler/python/scheduler.py:475-558` (`_daily_review_job`)
- Test: `tests/unit/test_scheduler_portfolio_hook.py` (append)

**Interfaces:**
- Consumes: `alert_job_partial_output` from Task 1 (late import, same pattern as the existing `alert_job_zero_output` call).
- Produces: `_daily_review_job` that never lets `concurrent.futures.TimeoutError` (or any harvest error) skip the alert + pipeline tail.

Key facts for the implementer: `as_completed(futures, timeout=...)` raises `TimeoutError` **from the generator itself** when the aggregate budget expires — the old `try` around `future.result(timeout=180)` never guarded it, and `result(timeout=)` on an already-completed future never blocks (that per-ticker timeout was fiction). `RL_SCHEDULER_MAX_WORKERS` defaults to 1 → serial; budget goes to 300 s/ticker (ledger option). `executor.shutdown(wait=False, cancel_futures=True)` (Py 3.9+) releases the job thread without waiting for stragglers; a straggler review finishing later still persists harmlessly (its review is on disk for the RL layer; it just misses today's pipeline).

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_scheduler_portfolio_hook.py`:

```python
def test_daily_review_job_survives_harvest_timeout(monkeypatch):
    """AUD-084: Tue 2026-07-14 — the aggregate as_completed TimeoutError escaped
    the loop, skipping BOTH the alerts and the portfolio pipeline (13 reviews
    saved, 0 trades, no alert). The tail must run regardless."""
    import concurrent.futures as cf
    import services.scheduler.python.scheduler as sch
    import core.intelligence.rl.workflows.daily_review as dr
    import core.portfolio.pipeline as pl
    import core.delivery.ops_alerts as oa

    calls, partial = {}, {}
    monkeypatch.setattr(dr, "run_daily_review",
                        lambda t, d, sector=None: {"status": "completed"})
    monkeypatch.setattr(pl, "run_post_review_pipeline",
                        lambda d: calls.setdefault("pipeline", d) or {"status": "completed"})
    monkeypatch.setattr(sch, "get_active_tickers_with_sector",
                        lambda: [{"sym": "MARUTI", "sector": "automobile"},
                                 {"sym": "INFY", "sector": "it_sector"}])
    monkeypatch.setattr(
        oa, "alert_job_partial_output",
        lambda job, produced, expected: partial.update(produced=produced, expected=expected))

    def fake_as_completed(fs, timeout=None):
        fs = list(fs)
        cf.wait(fs)                 # deterministic: both futures finish instantly
        yield fs[0]                 # harvest ONE result...
        raise cf.TimeoutError()     # ...then the aggregate budget "expires"

    monkeypatch.setattr(sch._cf, "as_completed", fake_as_completed)

    sch.AutomobileScheduler()._daily_review_job()   # must not raise

    assert "pipeline" in calls, "TimeoutError skipped the portfolio pipeline"
    assert partial == {"produced": 1, "expected": 2}


def test_daily_review_job_partial_alert_silent_on_full_harvest(monkeypatch):
    """No partial alert noise on a normal full-success day."""
    import services.scheduler.python.scheduler as sch
    import core.intelligence.rl.workflows.daily_review as dr
    import core.portfolio.pipeline as pl
    import core.delivery.ops_alerts as oa

    fired = []
    monkeypatch.setattr(dr, "run_daily_review",
                        lambda t, d, sector=None: {"status": "completed"})
    monkeypatch.setattr(pl, "run_post_review_pipeline",
                        lambda d: {"status": "completed"})
    monkeypatch.setattr(sch, "get_active_tickers_with_sector",
                        lambda: [{"sym": "MARUTI", "sector": "automobile"}])
    monkeypatch.setattr(oa, "alert_job_partial_output",
                        lambda job, produced, expected: fired.append((produced, expected)))

    sch.AutomobileScheduler()._daily_review_job()
    assert fired == [(1, 1)]   # called, but helper itself no-ops at full output
```

Note: the second test asserts only that the call site passes correct numbers; the helper's own silence at `produced == expected` is covered by Task 1's tests.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_scheduler_portfolio_hook.py -v`
Expected: `test_daily_review_job_survives_harvest_timeout` FAILS — either an uncaught `TimeoutError` propagates or `partial` stays empty (no partial-alert call site yet). `..._silent_on_full_harvest` FAILS (`fired == []`).

- [ ] **Step 3: Implement**

In `services/scheduler/python/scheduler.py`, replace the `_daily_review_job` harvest block (currently lines 508-542, from `succeeded = 0` through the `alert_job_zero_output` try/except) with:

```python
        succeeded = 0
        stragglers: list[str] = []
        # AUD-084: the old "3-minute per-ticker timeout" was fiction —
        # as_completed only ever yields FINISHED futures, so result(timeout=)
        # never blocked. The only real cap is the aggregate as_completed budget,
        # and its TimeoutError rises from the GENERATOR, outside the old inner
        # try — on Tue 2026-07-14 it escaped, skipping the alerts and the
        # portfolio pipeline (13 reviews saved, 0 trades, zero alerts).
        # Contain it: harvest what finished, log the stragglers, always fall
        # through to the alert + pipeline tail. shutdown(wait=False) releases
        # this thread; a straggler finishing later still persists its review.
        executor = _cf.ThreadPoolExecutor(max_workers=max_w)
        try:
            futures = {
                executor.submit(_review_one, entry): entry
                for entry in ticker_entries
            }
            try:
                for future in _cf.as_completed(futures, timeout=300 * max(len(ticker_entries), 1)):
                    try:
                        ticker, sector, summary, err = future.result()
                        if err is not None:
                            logger.error(
                                "[Scheduler] Daily review FAILED for %s: %s", ticker, err, exc_info=True
                            )
                        else:
                            succeeded += 1
                            logger.info(
                                "[Scheduler] %s %s sector=%s — status=%s direction=%s lessons=%s weights=v%s",
                                ticker, review_date, sector,
                                summary.get("status"),
                                summary.get("direction_correct"),
                                summary.get("lessons_added"),
                                summary.get("weight_version"),
                            )
                    except Exception as exc:
                        logger.error("[Scheduler] Unexpected error in daily review: %s", exc, exc_info=True)
            except _cf.TimeoutError:
                stragglers = [e["sym"] for f, e in futures.items() if not f.done()]
                logger.error(
                    "[Scheduler] Daily review harvest budget exhausted — %d unfinished: %s; "
                    "continuing with %d completed reviews (AUD-084)",
                    len(stragglers), stragglers, succeeded,
                )
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        try:
            # AUD-039: "all reviews failed but the job logged complete" must page.
            from core.delivery.ops_alerts import alert_job_zero_output
            alert_job_zero_output("daily_review", produced=succeeded,
                                  expected=len(ticker_entries))
        except Exception:
            pass
        try:
            # AUD-090b: a partial day (13/16 on Tue 7/14) was invisible.
            from core.delivery.ops_alerts import alert_job_partial_output
            alert_job_partial_output("daily_review", produced=succeeded,
                                     expected=len(ticker_entries))
        except Exception:
            pass
```

Also update the `_daily_review_job` docstring line about timeouts — replace

```
        Each ticker has a 3-minute
        timeout to prevent a stalled LLM call from blocking the entire loop.
```

with

```
        The harvest has an aggregate budget (300 s x tickers); if it expires,
        the finished reviews stand, stragglers are logged, and the pipeline
        below still runs (AUD-084 — a slow day must not kill the trading day).
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_scheduler_portfolio_hook.py tests/unit/test_ops_alerts.py -v`
Expected: all PASS (7 in the hook file, 8 in ops_alerts).

- [ ] **Step 5: Commit**

```bash
git add services/scheduler/python/scheduler.py tests/unit/test_scheduler_portfolio_hook.py
git commit -m "fix(scheduler): contain harvest TimeoutError — alerts + pipeline always run (AUD-084)"
```

---

### Task 3: Scheduler — APScheduler error listener pages on any job crash

**Files:**
- Modify: `services/scheduler/python/scheduler.py` (`_build_scheduler` ~line 132; new method `_on_job_error` on `AutomobileScheduler`)
- Test: `tests/unit/test_scheduler_portfolio_hook.py` (append)

**Interfaces:**
- Consumes: `alert_job_crashed(job, error)` from Task 1 (late import).
- Produces: `AutomobileScheduler._on_job_error(event)` — registered for `EVENT_JOB_ERROR`; belt-and-braces for ANY exception that still escapes a job function.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_scheduler_portfolio_hook.py`:

```python
def test_scheduler_registers_job_error_listener():
    """AUD-084 rider: any exception escaping a job must page, not just land in
    the apscheduler log."""
    import services.scheduler.python.scheduler as sch
    inst = sch.AutomobileScheduler()
    assert inst._on_job_error in [cb for cb, _mask in inst._scheduler._listeners]


def test_on_job_error_emits_crash_alert(monkeypatch):
    import services.scheduler.python.scheduler as sch
    import core.delivery.ops_alerts as oa

    crashed = []
    monkeypatch.setattr(oa, "alert_job_crashed",
                        lambda job, error: crashed.append((job, error)))

    class _Event:
        job_id = "rl_daily_review"
        exception = TimeoutError("3 (of 16) futures unfinished")

    sch.AutomobileScheduler()._on_job_error(_Event())
    assert crashed and crashed[0][0] == "rl_daily_review"
    assert "unfinished" in crashed[0][1]


def test_on_job_error_never_raises(monkeypatch):
    import services.scheduler.python.scheduler as sch
    import core.delivery.ops_alerts as oa

    def boom(job, error):
        raise RuntimeError("alert layer down")
    monkeypatch.setattr(oa, "alert_job_crashed", boom)

    class _Event:
        job_id = "rl_daily_review"
        exception = RuntimeError("x")

    sch.AutomobileScheduler()._on_job_error(_Event())   # must not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_scheduler_portfolio_hook.py -v`
Expected: 3 new tests FAIL (`AttributeError: ... has no attribute '_on_job_error'`).

- [ ] **Step 3: Implement**

In `_build_scheduler`, immediately after `scheduler = BackgroundScheduler(timezone="Asia/Kolkata")`:

```python
        # AUD-084 rider: anything that still escapes a job function (the
        # harvest-TimeoutError class) must page a human, not just vanish
        # into the apscheduler error log.
        try:
            from apscheduler.events import EVENT_JOB_ERROR
            scheduler.add_listener(self._on_job_error, EVENT_JOB_ERROR)
        except Exception as exc:
            logger.warning("[Scheduler] could not register error listener: %s", exc)
```

New method on `AutomobileScheduler` (place after `_build_scheduler`):

```python
    def _on_job_error(self, event) -> None:
        """EVENT_JOB_ERROR hook — one critical ops alert per crashed job run
        (AUD-084 rider). Never raises: alerting must not hurt the scheduler."""
        job_id = str(getattr(event, "job_id", "unknown"))
        exc = getattr(event, "exception", None)
        logger.error("[Scheduler] Job %s CRASHED: %r", job_id, exc)
        try:
            from core.delivery.ops_alerts import alert_job_crashed
            alert_job_crashed(job_id, repr(exc))
        except Exception as alert_exc:
            logger.warning("[Scheduler] crash alert failed (non-fatal): %s", alert_exc)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_scheduler_portfolio_hook.py -v`
Expected: all 10 PASS.

- [ ] **Step 5: Commit**

```bash
git add services/scheduler/python/scheduler.py tests/unit/test_scheduler_portfolio_hook.py
git commit -m "feat(scheduler): EVENT_JOB_ERROR listener pages via ops alert (AUD-084 rider)"
```

---

### Task 4: alerts.py — sent-log records the delivery outcome; undelivered retries

**Files:**
- Modify: `core/delivery/alerts.py` (`emit_alerts` lines 105-123, `_seen_keys` lines 50-64, module docstring)
- Test: `tests/unit/test_delivery_alerts.py` (modify 1, append 2)

**Interfaces:**
- Consumes: `deliver(title, body, user_id=...) -> {"delivered": bool, ...}` (unchanged contract from channels.py).
- Produces: `emit_alerts(...)` return dict gains `"delivered": bool`; sent-log records gain `"delivered": bool`; `_seen_keys` skips records whose `delivered` is exactly `False` (missing key = legacy = delivered).

**Why:** prod incident — the sent-log was appended BEFORE delivery, so the `date|kind` dedupe suppressed any same-day resend; when the user finally enabled a transport, that day's alerts were gone forever (AUD-085).

- [ ] **Step 1: Update/write the failing tests**

In `tests/unit/test_delivery_alerts.py`, add `import json` to the imports, then REPLACE `test_emit_never_raises_on_delivery_failure` (lines 49-53) with:

```python
def test_emit_never_raises_on_delivery_failure(tmp_path):
    log = str(tmp_path / "alerts_sent.jsonl")
    with patch.object(al, "deliver", side_effect=RuntimeError("channel down")):
        out = emit_alerts([_ev()], sent_log=log)
    assert out["emitted"] == 1 and out["delivered"] is False
```

Append:

```python
def test_undelivered_alert_retries_next_emit_then_dedupes(tmp_path):
    """AUD-085 rider: appending the sent-log BEFORE the outcome cemented failed
    sends — after the user subscribes, the same-day alert must go out."""
    log = str(tmp_path / "alerts_sent.jsonl")
    with patch.object(al, "deliver",
                      return_value={"delivered": False, "push": 0, "email": 0}):
        assert emit_alerts([_ev()], sent_log=log)["emitted"] == 1
    with patch.object(al, "deliver",
                      return_value={"delivered": True, "push": 1, "email": 0}) as m:
        out2 = emit_alerts([_ev()], sent_log=log)   # transport appeared → retry
        out3 = emit_alerts([_ev()], sent_log=log)   # delivered → now dedupes
    assert out2["emitted"] == 1 and out2["delivered"] is True
    assert out3["emitted"] == 0
    assert m.call_count == 1


def test_legacy_records_without_delivered_key_still_dedupe(tmp_path):
    """Records written before the delivered flag existed are treated as sent."""
    log = tmp_path / "alerts_sent.jsonl"
    log.write_text(json.dumps({"date": "2026-07-09", "kind": "advisor_exit",
                               "symbol": "OLDCO", "user_id": ""}) + "\n",
                   encoding="utf-8")
    with patch.object(al, "deliver", return_value={"delivered": True}) as m:
        out = emit_alerts([_ev()], sent_log=str(log))
    assert out["emitted"] == 0 and m.call_count == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_delivery_alerts.py -v`
Expected: the replaced test FAILS (`KeyError: 'delivered'`), retry test FAILS (`out2["emitted"] == 0` — old code deduped it), legacy test PASSES already (keep it as a regression guard).

- [ ] **Step 3: Implement**

In `core/delivery/alerts.py`:

(a) `_seen_keys` — inside the loop, after `rec = json.loads(line)` add:

```python
                if rec.get("delivered") is False:   # AUD-085: undelivered → retryable
                    continue
```

(b) `emit_alerts` — replace the block from `with open(path, "a", ...)` through `return {"emitted": len(uniq), ...}` (lines 107-120) with:

```python
        body = "\n".join(
            f"{_SEVERITY_TAG[e.severity]} {e.symbol + ' — ' if e.symbol else ''}{e.message}"
            for e in uniq
        )
        # AUD-085 rider: deliver FIRST, then record the outcome — a record with
        # delivered=false does not dedupe, so the same-day batch retries once a
        # transport (push sub / SMTP) appears. Legacy records lack the key and
        # are treated as delivered.
        delivered = False
        outcome: dict = {}
        try:
            outcome = deliver(title, body, user_id=user_id) or {}
            delivered = bool(outcome.get("delivered"))
        except Exception as exc:
            logger.warning("[alerts] delivery failed (non-fatal): %s", exc)
        if not delivered:
            logger.warning(
                "[alerts] %d alert(s) NOT delivered (%s) — recorded delivered=false, "
                "will retry on next emit (AUD-085)",
                len(uniq), outcome.get("reason") or "no channel delivered")
        with open(path, "a", encoding="utf-8") as fh:
            for e in uniq:
                rec = e.model_dump()
                rec["user_id"] = uid
                rec["delivered"] = delivered
                fh.write(json.dumps(rec) + "\n")
        return {"emitted": len(uniq), "delivered": delivered,
                "kinds": sorted({e.kind for e in uniq})}
```

(c) Module docstring — after the sentence about the dedupe key, add:

```
Each record carries "delivered" (AUD-085): false means no channel accepted
the batch — such records are ignored by dedupe so the alert retries on the
next emit; records written before this field existed are treated as
delivered.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_delivery_alerts.py tests/unit/test_ops_alerts.py tests/unit/test_portfolio_reconcile.py -v`
Expected: all PASS (reconcile suite exercises `_alert` → confirms no regression in the emit path).

- [ ] **Step 5: Commit**

```bash
git add core/delivery/alerts.py tests/unit/test_delivery_alerts.py
git commit -m "fix(delivery): sent-log records delivery outcome; undelivered alerts retry (AUD-085)"
```

---

### Task 5: channels.py — prune dead subs on 400/403, warn on silent drops

**Files:**
- Modify: `core/delivery/channels.py` (`send_push` lines 106-137, `deliver` lines 140-156)
- Test: `tests/unit/test_delivery_channels.py` (append)

**Interfaces:**
- Consumes: nothing new.
- Produces: unchanged signatures; behavior — `send_push` prunes on 400/403/404/410 and WARNs when push is enabled but zero subscriptions exist; `deliver` WARNs when nothing was delivered (AUD-090c + AUD-085 observability).

**Why:** prod has one stale subscription failing 400 on every send (kept forever, never pruned), and 4 days of `push=0 email=0` at INFO level looked healthy in the logs.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_delivery_channels.py` (module already imports `ch`, `PushStore`, `deliver`, `send_push`; `_SUB`/`_SUB2` defined at top):

```python
def test_send_push_prunes_dead_subscription_on_400(tmp_path, monkeypatch):
    """AUD-085 rider: the prod stale sub fails 400 (malformed/VAPID-mismatch)
    on EVERY send and was never pruned — 400/403 are permanent, like 404/410."""
    store = PushStore(path=str(tmp_path / "subs.json"))
    store.add(_SUB)
    monkeypatch.setattr(ch.settings, "DELIVERY_PUSH_ENABLED", True)
    monkeypatch.setattr(ch.settings, "VAPID_PRIVATE_KEY", "priv")

    class _Resp:
        status_code = 400

    class _Bad(Exception):
        def __init__(self):
            self.response = _Resp()

    def _fake_webpush(subscription_info, data, vapid_private_key, vapid_claims):
        raise _Bad()

    monkeypatch.setattr(ch, "webpush", _fake_webpush)
    assert send_push("t", "b", store=store) == 0
    assert store.list() == []                       # 400 pruned


def test_send_push_zero_subscriptions_warns(tmp_path, monkeypatch, caplog):
    """AUD-090c: push enabled + no subscription = notification silently dropped."""
    import logging
    store = PushStore(path=str(tmp_path / "subs.json"))
    monkeypatch.setattr(ch.settings, "DELIVERY_PUSH_ENABLED", True)
    monkeypatch.setattr(ch.settings, "VAPID_PRIVATE_KEY", "priv")
    monkeypatch.setattr(ch, "webpush", lambda **kw: None)
    with caplog.at_level(logging.WARNING, logger="core.delivery.channels"):
        assert send_push("t", "b", store=store) == 0
    assert any("0 subscriptions" in r.message for r in caplog.records)


def test_deliver_warns_when_nothing_delivered(monkeypatch, caplog):
    import logging
    monkeypatch.setattr(ch.settings, "DELIVERY_ENABLED", True)
    monkeypatch.setattr(ch, "send_push", lambda *a, **k: 0)
    monkeypatch.setattr(ch, "send_email", lambda *a, **k: False)
    with caplog.at_level(logging.WARNING, logger="core.delivery.channels"):
        out = deliver("Morning brief", "body")
    assert out["delivered"] is False
    assert any("NOWHERE" in r.message for r in caplog.records)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_delivery_channels.py -v`
Expected: 3 new tests FAIL (sub not pruned on 400; no warning records found).

- [ ] **Step 3: Implement**

In `send_push`, replace the body after the enabled/VAPID guard (lines 118-137) with:

```python
    store = store or PushStore()
    subs = store.list(user_id)
    if not subs:
        # AUD-090c: enabled-but-no-recipients is the silent-drop signature.
        logger.warning(
            "[delivery] push enabled but 0 subscriptions registered for user "
            "'%s' — notification dropped (enable alerts in the PWA)",
            user_id or settings.PORTFOLIO_DEFAULT_USER_ID)
        return 0
    payload = json.dumps({"title": title, "body": body[:1500], "url": url})
    sent = 0
    for sub in subs:
        try:
            webpush(
                subscription_info=sub,
                data=payload,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": f"mailto:{settings.VAPID_CLAIM_EMAIL}"},
            )
            sent += 1
        except Exception as exc:
            code = getattr(getattr(exc, "response", None), "status_code", None)
            if code in (400, 403, 404, 410):
                # 404/410 = expired; 400/403 = malformed sub or VAPID-key
                # mismatch (AUD-085 prod stale sub) — all permanent, prune.
                store.remove(sub.get("endpoint", ""), user_id)
                logger.info("[delivery] pruned dead push subscription (%s)", code)
            else:
                logger.warning("[delivery] push send failed (non-fatal): %s", exc)
    return sent
```

In `deliver`, replace the final `logger.info(...)` line (155) with:

```python
    if pushed or emailed:
        logger.info("[delivery] %s — push=%d email=%d", title, pushed, emailed)
    else:
        logger.warning(
            "[delivery] %s — landed NOWHERE (push=0 email=0): no push "
            "subscriptions and email disabled/unconfigured (AUD-085)", title)
```

Also update the module docstring line `Expired subscriptions (404/410) are pruned on send.` → `Dead subscriptions (400/403/404/410) are pruned on send.`

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_delivery_channels.py tests/unit/test_delivery_alerts.py -v`
Expected: all PASS (including the pre-existing 410-prune and zero-VAPID tests).

- [ ] **Step 5: Commit**

```bash
git add core/delivery/channels.py tests/unit/test_delivery_channels.py
git commit -m "fix(delivery): prune dead push subs on 400/403 + warn on silent drops (AUD-085/090c)"
```

---

### Task 6: reconcile.py — clean pass says so (AUD-090a)

**Files:**
- Modify: `core/portfolio/reconcile.py:97`
- Test: `tests/unit/test_portfolio_reconcile.py` (append)

**Interfaces:** none new — one INFO line so "ran clean" is distinguishable from "didn't run".

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_portfolio_reconcile.py`:

```python
def test_clean_pass_logs_info(tmp_path, _alert_spy, caplog):
    """AUD-090a: a clean pass must leave a log line — silence previously meant
    either 'clean' or 'never ran'."""
    import logging
    s = _store(tmp_path, [_h("MARUTI", 10)], cash=9000.0)
    s.append_transaction(_txn("t1", "BUY", "MARUTI", 10, 100.0, 10000.0, 9000.0))
    with caplog.at_level(logging.INFO, logger="core.portfolio.reconcile"):
        assert rec.reconcile(s)["status"] == "clean"
    assert any("clean" in r.message for r in caplog.records)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_portfolio_reconcile.py -v`
Expected: new test FAILS (no log records); existing 7 pass.

- [ ] **Step 3: Implement**

In `reconcile()`, replace the final clean return (line 97) with:

```python
        logger.info("[reconcile] clean for %s — %d txns replayed, %d holdings "
                    "verified (%d unverifiable)", store.user_id, len(txns),
                    len(portfolio.holdings) - len(unverifiable), len(unverifiable))
        return {"status": "clean", "issues": [], "unverifiable": unverifiable}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_portfolio_reconcile.py -v`
Expected: all 8 PASS.

- [ ] **Step 5: Commit**

```bash
git add core/portfolio/reconcile.py tests/unit/test_portfolio_reconcile.py
git commit -m "feat(reconcile): INFO line on clean pass (AUD-090a)"
```

---

### Task 7: Verification, ledger, merge

**Files:**
- Modify: `docs/audit/LEDGER.md` (AUD-084, AUD-085, AUD-090 rows → status)
- No code changes.

- [ ] **Step 1: Full unit+contract suite**

Run: `python -m pytest tests/ -q --timeout=300 2>&1 | tail -5` (or without `--timeout` if the plugin is absent)
Expected: pass/fail/error/skip counts match the pre-wave baseline (10 failed / 10 errors / ~2181+13 passed / 12 skipped — the failures are the known AUD-022 stale mocks + 1 pre-existing event_ingestor date test; verify NO NEW failures vs a `git stash`-free main run if in doubt).

- [ ] **Step 2: Update the ledger**

In `docs/audit/LEDGER.md`:
- AUD-084 row: status `OPEN (URGENT)` → `FIXED (Wave A 2026-07-16: harvest TimeoutError contained — stragglers logged, zero/partial alerts + pipeline always run; budget 300s/ticker; shutdown(wait=False); EVENT_JOB_ERROR listener → job_crashed ops alert)`.
- AUD-085 row: status → `FIXED (transport live 2026-07-16 — Gmail SMTP verified in prod; Wave A code riders: sent-log written after outcome w/ delivered flag + retry, zero-sub WARNING, landed-nowhere WARNING, prune 400/403)`.
- AUD-090 row: status → `PARTIAL (Wave A: (a) reconcile clean INFO, (b) partial-output alert, (c) zero-recipient warning DONE; (d) last-run-outcome surface on /scheduler/status → Wave F)`.
- Keep wording free of prod host/cash specifics.

- [ ] **Step 3: Commit ledger**

```bash
git add docs/audit/LEDGER.md
git commit -m "docs(audit): Wave A shipped — AUD-084 fixed, AUD-085 riders fixed, AUD-090 a-c folded"
```

- [ ] **Step 4: Merge + push (per standing autonomy: act, verify, report)**

```bash
git checkout main
git merge --ff-only audit-wave-a-reliability
git push origin main
```

Expected: fast-forward, push succeeds (public repo — commit messages already specifics-free).

- [ ] **Step 5: Post-deploy verification note**

Railway auto-deploys on push. Verify next trading day after 16:35 IST: `[Scheduler]` daily-review banner → `[portfolio_pipeline]` lines → digest email received. If a timeout occurs, expect the new `harvest budget exhausted` line followed by pipeline execution and a partial-output email.

---

## Self-Review

- **Spec coverage:** AUD-084 core (Task 2) + listener (Task 3); AUD-085 riders — sent-log-after-outcome (Task 4), zero-recipient WARNING + landed-nowhere WARNING (Task 5), prune-on-400 (Task 5); AUD-090a (Task 6), 090b (Tasks 1+2), 090c (Task 5); 090d explicitly deferred to Wave F in the ledger update. ✓
- **Placeholder scan:** none — every step has complete code/commands. ✓
- **Type consistency:** `alert_job_partial_output(job, produced, expected)` / `alert_job_crashed(job, error)` used identically in Tasks 1/2/3; `emit_alerts` return `"delivered"` key consistent between Task 4 code and tests; `_on_job_error(event)` matches registration. ✓
