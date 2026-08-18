# tests/unit/test_scheduler_ipo_refresh.py
"""PI Prospect P2 — ipo_refresh_pm must land strictly before Sunday's 18:00
weekly_review, or the digest is a coin flip between the fresh evening cache
and the stale 08:00 one (task 7)."""
from core.config import settings
from services.scheduler.python.scheduler import AutomobileScheduler


def test_the_pm_ipo_refresh_lands_before_the_weekly_review():
    """Both used to fire at 18:00 Sunday with no ordering, making the digest a
    coin flip between the fresh cache and the morning one."""
    pm_minutes = settings.IPO_REFRESH_HOUR_LIVE * 60 + settings.IPO_REFRESH_MINUTE_LIVE
    assert pm_minutes < 18 * 60
    # Still after NSE's ~17:00 bid update, or the evening pass reads stale bids.
    assert pm_minutes >= 17 * 60


def test_ipo_refresh_pm_job_registered_at_1745_ist():
    """The settings arithmetic above is necessary but not sufficient — this
    pins down that the scheduler actually registers ipo_refresh_pm's
    CronTrigger at the configured hour AND minute, not just that the config
    values happen to add up correctly."""
    sched = AutomobileScheduler()
    job = sched._scheduler.get_job("ipo_refresh_pm")
    assert job is not None
    fields = {f.name: str(f) for f in job.trigger.fields}
    assert fields["hour"] == "17" and fields["minute"] == "45"


def test_ipo_refresh_am_job_still_registered_at_0800_ist():
    """The am slot is untouched by this change — minute stays 0."""
    sched = AutomobileScheduler()
    job = sched._scheduler.get_job("ipo_refresh_am")
    assert job is not None
    fields = {f.name: str(f) for f in job.trigger.fields}
    assert fields["hour"] == "8" and fields["minute"] == "0"


def test_ipo_refresh_pm_job_absent_when_ipo_disabled(monkeypatch):
    monkeypatch.setattr(
        "services.scheduler.python.scheduler.cfg",
        lambda key, fallback=None: False if key == "ipo.enabled" else fallback,
    )
    sched = AutomobileScheduler()
    assert sched._scheduler.get_job("ipo_refresh_pm") is None


def test_both_refresh_hours_come_from_the_settings_constants(monkeypatch):
    """`IPO_REFRESH_HOUR_LIVE` was declared in base.py and read by NOTHING in
    production — the scheduler resolved the same key with its own inline cfg()
    call, so the only reader was the arithmetic test above. That is the
    declared-but-unread pattern this branch already deleted `gmp_max_age_hours`
    for, and it makes the test a mirror of a constant rather than of behaviour.

    Moving one hour and asserting the registered trigger follows proves the
    constants are what production actually reads. `IPO_REFRESH_MINUTE_LIVE`
    already worked this way; the hours now match it.
    """
    from core.config import settings as s
    monkeypatch.setattr(s, "IPO_REFRESH_HOUR", 9, raising=True)
    monkeypatch.setattr(s, "IPO_REFRESH_HOUR_LIVE", 19, raising=True)

    sched = AutomobileScheduler()
    pm = {f.name: str(f) for f in sched._scheduler.get_job("ipo_refresh_pm").trigger.fields}
    am = {f.name: str(f) for f in sched._scheduler.get_job("ipo_refresh_am").trigger.fields}
    assert pm["hour"] == "19" and pm["minute"] == "45"
    assert am["hour"] == "9" and am["minute"] == "0"
