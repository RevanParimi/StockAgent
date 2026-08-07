"""The audit section rides the existing Learning Evidence envelope.

build_scorecard/save_scorecard are imported INSIDE _scorecard_monthly_job, so
they are not attributes of the scheduler module — they must be patched at their
source module. build_audit_report/render_audit_section are module-level imports
in the scheduler and are patched there.
"""
from unittest.mock import patch

import services.scheduler.python.scheduler as sched


def test_audit_section_is_appended_to_the_learning_evidence_email():
    s = sched.AutomobileScheduler()
    sent = {}

    def _capture(subject, body):
        sent["subject"], sent["body"] = subject, body

    with patch("core.intelligence.rl.eval.scorecard.build_scorecard", return_value={}), \
         patch("core.intelligence.rl.eval.scorecard.save_scorecard", return_value="/tmp/x.json"), \
         patch("core.intelligence.rl.eval.learning_evidence.build_learning_evidence",
               return_value={"verdict": "UNPROVEN"}), \
         patch("core.intelligence.rl.eval.learning_evidence.render_report",
               return_value="LEARNING EVIDENCE BODY"), \
         patch("core.intelligence.rl.eval.learning_evidence.save_report",
               return_value=("/tmp/a.json", "/tmp/a.txt")), \
         patch("core.delivery.channels.send_email", side_effect=_capture), \
         patch.object(sched, "build_audit_report",
                      return_value={"verdict": "INSUFFICIENT_DATA", "total_rows": 0,
                                    "min_n": 30, "hit_rate": {}, "per_trigger": {},
                                    "conviction_spread": None}), \
         patch.object(sched, "render_audit_section", return_value="AUDIT SECTION"):
        s._scorecard_monthly_job()

    assert "LEARNING EVIDENCE BODY" in sent["body"]
    assert "AUDIT SECTION" in sent["body"]


def test_audit_section_failure_does_not_lose_the_learning_evidence_email():
    s = sched.AutomobileScheduler()
    sent = {}

    with patch("core.intelligence.rl.eval.scorecard.build_scorecard", return_value={}), \
         patch("core.intelligence.rl.eval.scorecard.save_scorecard", return_value="/tmp/x.json"), \
         patch("core.intelligence.rl.eval.learning_evidence.build_learning_evidence",
               return_value={"verdict": "UNPROVEN"}), \
         patch("core.intelligence.rl.eval.learning_evidence.render_report",
               return_value="LEARNING EVIDENCE BODY"), \
         patch("core.intelligence.rl.eval.learning_evidence.save_report",
               return_value=("/tmp/a.json", "/tmp/a.txt")), \
         patch("core.delivery.channels.send_email",
               side_effect=lambda subject, body: sent.update(body=body)), \
         patch.object(sched, "build_audit_report", side_effect=RuntimeError("boom")):
        s._scorecard_monthly_job()

    assert "LEARNING EVIDENCE BODY" in sent["body"]
