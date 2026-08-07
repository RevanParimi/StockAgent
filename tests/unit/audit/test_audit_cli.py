from unittest.mock import patch

import core.audit.cli as cli


def test_report_flag_prints_the_section(capsys):
    with patch.object(cli, "build_report", return_value={"verdict": "INSUFFICIENT_DATA"}), \
         patch.object(cli, "render_section", return_value="SECTION TEXT"):
        rc = cli.main(["--report"])
    assert rc == 0
    assert "SECTION TEXT" in capsys.readouterr().out


def test_backfill_flag_prints_counts(capsys):
    with patch.object(cli, "grade_due",
                      return_value={"graded": 7, "skipped_unpriceable": 0,
                                    "already_present": 2, "lanes": {}}):
        rc = cli.main(["--backfill"])
    assert rc == 0
    assert "7" in capsys.readouterr().out


def test_no_flag_is_an_error(capsys):
    assert cli.main([]) == 2


def test_backfill_failure_returns_nonzero(capsys):
    with patch.object(cli, "grade_due", side_effect=RuntimeError("prices down")):
        assert cli.main(["--backfill"]) == 1
