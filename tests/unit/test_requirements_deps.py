"""AUD-078 regression: nsepython was imported by two LIVE fetchers but never
declared — dev venv had it, prod image didn't, so FII/DII/bulk-deal/earnings/
MF-herding context was silently empty in every prod prompt since first deploy."""
from pathlib import Path

REQ = Path("requirements.txt").read_text(encoding="utf-8")


def _declared(pkg: str) -> bool:
    return any(
        line.split("#")[0].strip().lower().startswith(pkg)
        for line in REQ.splitlines()
    )


def test_nsepython_declared():
    assert _declared("nsepython"), "nsepython missing from requirements.txt (AUD-078)"


def test_nse_still_declared():
    assert _declared("nse>")  # the OTHER NSE client, used by 10+ fetchers
