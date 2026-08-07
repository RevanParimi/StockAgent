"""Command-line entry point for the verification layer.

    python -m core.audit.cli --report
    python -m core.audit.cli --backfill [--user primary]

On prod the backfill is normally driven through POST /audit/backfill; this CLI
exists for local runs and for a shell on the volume if one becomes available.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date

from core.audit.outcomes import grade_due
from core.audit.report import build_report, render_section

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="core.audit.cli")
    parser.add_argument("--backfill", action="store_true",
                        help="grade every matured call in all history")
    parser.add_argument("--report", action="store_true",
                        help="print the current graded-outcome report")
    parser.add_argument("--user", default=None, help="user_id (default: owner)")
    args = parser.parse_args(argv)

    if not (args.backfill or args.report):
        parser.print_usage(sys.stderr)
        print("error: pass --backfill or --report", file=sys.stderr)
        return 2

    if args.backfill:
        try:
            result = grade_due(date.today(), args.user)
        except Exception as exc:
            print(f"backfill failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2))

    if args.report:
        try:
            print(render_section(build_report(args.user)))
        except Exception as exc:
            print(f"report failed: {exc}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":       # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
