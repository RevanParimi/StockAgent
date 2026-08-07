from unittest.mock import patch

import core.audit.thresholds as th


def _report(verdict="UNPROVEN", hit60=0.60, n=40, spread=3.0):
    return {
        "verdict": verdict, "min_n": 30, "total_rows": n,
        "hit_rate": {"60": {"n": n, "value": hit60, "lo": 0.4, "hi": 0.8}},
        "conviction_spread": spread,
    }


def test_low_hit_rate_breaches():
    with patch.object(th, "_cfg", side_effect=lambda k, d: {"audit.min_hit_rate_60d": 0.45}.get(k, d)):
        breaches = th.evaluate_breaches(_report(hit60=0.30))
    assert any(b["rule"] == "min_hit_rate_60d" for b in breaches)


def test_healthy_report_produces_no_breaches():
    with patch.object(th, "_cfg", side_effect=lambda k, d: d):
        assert th.evaluate_breaches(_report(hit60=0.62, spread=4.0)) == []


def test_thin_sample_never_breaches_hit_rate():
    with patch.object(th, "_cfg", side_effect=lambda k, d: d):
        breaches = th.evaluate_breaches(_report(hit60=0.10, n=5))
    assert not any(b["rule"] == "min_hit_rate_60d" for b in breaches)


def test_flat_conviction_breaches_at_info_severity():
    with patch.object(th, "_cfg", side_effect=lambda k, d: d):
        breaches = th.evaluate_breaches(_report(spread=0.1))
    flat = [b for b in breaches if b["rule"] == "conviction_flat_spread"]
    assert flat and flat[0]["severity"] == "info"


def test_news_blind_rate_breaches():
    with patch.object(th, "_cfg", side_effect=lambda k, d: d):
        breaches = th.evaluate_breaches(_report(), news_blind_rate=0.60)
    assert any(b["rule"] == "max_news_blind_rate" for b in breaches)


def test_news_blind_rate_none_is_not_a_breach():
    with patch.object(th, "_cfg", side_effect=lambda k, d: d):
        breaches = th.evaluate_breaches(_report(), news_blind_rate=None)
    assert not any(b["rule"] == "max_news_blind_rate" for b in breaches)


def test_emit_is_silenced_by_kill_switch():
    with patch.object(th, "_cfg", side_effect=lambda k, d: False if k == "audit.alerts_enabled" else d):
        with patch.object(th, "emit_alerts_broadcast") as m:
            out = th.emit_breaches([{"rule": "min_hit_rate_60d", "severity": "warning",
                                     "message": "m"}])
    assert m.call_count == 0 and out["emitted"] == 0


def test_emit_sends_one_batch():
    with patch.object(th, "_cfg", side_effect=lambda k, d: True if k == "audit.alerts_enabled" else d):
        with patch.object(th, "emit_alerts_broadcast", return_value={"emitted": 1}) as m:
            out = th.emit_breaches([{"rule": "min_hit_rate_60d", "severity": "warning",
                                     "message": "m"}])
    assert m.call_count == 1 and out["emitted"] == 1


def test_emit_nothing_when_no_breaches():
    with patch.object(th, "emit_alerts_broadcast") as m:
        assert th.emit_breaches([])["emitted"] == 0
    assert m.call_count == 0
