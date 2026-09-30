"""
SA-009 fixture: a small prediction-store tree with every case the inventory
and the migration must tell apart. Not a test module (no test_ prefix).

Dimension rosters are literals copied from the sector settings, so expected
results come from this file's design, not from the code under test. Every
file carries marker text and prices the manifest must never repeat.

    predictions/
      renewable_energy/SUZLON   managed owner; its log and weights say
                                "automobile" (the old schema default)
      automobile/SUZLON         the old self-heal's copy: automobile roster;
                                envelope, day 07-01 and weights conflict
      banking_bfsi/RBLBANK      managed owner
      bfsi/RBLBANK              byte-identical copy in an unknown sector dir
      automobile/MARUTI         managed owner
      MARUTI/                   legacy flat store, automobile roster
      LEGACYCO/                 legacy flat store, no roster
      it_sector/TCS             managed owner carrying the automobile roster;
                                07-31 graded in two of its own logs
      generic/NEWCO             unmanaged, no roster (directory only)
      generic/SUNPHARMA         empty (minted by a read)
      automobile/ACME, generic/ACME            unmanaged duplicate
      automobile/INOXWIND, renewable_energy/INOXWIND
                                managed as automobile, mapped to
                                renewable_energy: owner and map disagree
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

AUTO = ["competitive_intel", "fundamentals", "pattern_analysis", "policy_regulatory",
        "raw_materials", "risk_macro", "sales_demand", "sentiment", "valuation_catalyst"]
BANK = ["fundamentals", "institutional", "macro_policy", "pattern_analysis", "risk",
        "universe_setup"]
IT = ["fundamentals", "global_macro", "insider_smart_money", "pattern_analysis",
      "peer_benchmark", "risk_macro", "sentiment", "transcript_nlp"]
RENEW = ["business", "fundamentals", "risk", "sentiment_policy", "technical", "valuation"]
GENERIC = ["business", "earnings", "fundamentals", "macro", "management", "risk",
           "technical", "valuation"]
ROSTERS = {"automobile": AUTO, "banking_bfsi": BANK, "it_sector": IT,
           "renewable_energy": RENEW, "generic": GENERIC}
NATIVE = {"automobile", "banking_bfsi", "it_sector", "renewable_energy"}
REGISTRY = {"SUZLON": "renewable_energy", "RBLBANK": "banking_bfsi", "MARUTI": "automobile",
            "TCS": "it_sector", "INOXWIND": "renewable_energy", "SUNPHARMA": "pharma"}
MANAGED = [
    {"sym": "SUZLON", "sector": "renewable_energy", "enabled": True},
    {"sym": "RBLBANK", "sector": "banking_bfsi", "enabled": True},
    {"sym": "MARUTI", "sector": "automobile", "enabled": True},
    {"sym": "TCS", "sector": "it_sector", "enabled": False},
    {"sym": "INOXWIND", "sector": "automobile", "enabled": True},
]
SECRETS = ("SECRET-THESIS-TEXT", "SECRET-LESSON", "SECRET-DOSSIER", "1234.56", "987.65")


def inventory_kwargs() -> dict:
    return {
        "rosters": ROSTERS,
        "registry": dict(REGISTRY),
        "graph_of": lambda s: s if s in NATIVE else "generic",
        "resolve": lambda t: REGISTRY.get(t, "generic"),
        "known_sectors": set(REGISTRY.values()) | NATIVE | {"generic"},
    }


def _put(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(obj, indent=2).encode("utf-8"))


def _scores(dims):
    return {d: 0.61 for d in dims}


def envelope(ticker, cycle, dims, dates, *, sector=None, price=1234.56):
    env = {
        "ticker": ticker, "cycle_id": f"{ticker}_{cycle}", "generated_at": f"{cycle}-01",
        "base_close": price,
        "daily_forecasts": [
            {"day": i + 1, "date": d, "predicted_close": round(price + i, 2),
             "predicted_verdict": "BUY", "predicted_agent_scores": _scores(dims),
             "key_assumptions": ["SECRET-THESIS-TEXT"]}
            for i, d in enumerate(dates)
        ],
    }
    if sector is not None:
        env["sector"] = sector
    return env


def entry(day, dims, *, actual=1240.0):
    return {"day": 1, "date": day, "predicted_close": 1234.56, "actual_close": actual,
            "price_error_pct": 0.44, "predicted_verdict": "BUY", "actual_direction": "UP",
            "direction_correct": True, "predicted_agent_scores": _scores(dims),
            "lessons_generated": ["SECRET-LESSON"]}


def feedback_log(ticker, cycle, entries, sector="automobile"):
    return {"ticker": ticker, "sector": sector, "cycle_id": f"{ticker}_{cycle}",
            "entries": entries}


def weights(ticker, dims, sector="automobile"):
    w = {d: round(1 / len(dims), 6) for d in dims}
    return {"ticker": ticker, "sector": sector, "last_updated": "2026-07-31",
            "weight_version": 3, "current_weights": w, "base_weights": dict(w)}


def build_tree(root: Path) -> tuple[Path, Path]:
    """Write the fixture under root. Returns (predictions dir, managed file)."""
    base = root / "predictions"
    p = base

    s = p / "renewable_energy" / "SUZLON"
    _put(s / "SUZLON_2026-07_prediction_envelope.json",
         envelope("SUZLON", "2026-07", RENEW, ["2026-07-01", "2026-07-02"],
                  sector="renewable_energy"))
    _put(s / "SUZLON_2026-07_daily_feedback_log.json",
         feedback_log("SUZLON", "2026-07", [entry("2026-07-01", RENEW)]))
    _put(s / "SUZLON_agent_weight_memory.json", weights("SUZLON", RENEW))

    s = p / "automobile" / "SUZLON"
    _put(s / "SUZLON_2026-07_prediction_envelope.json",
         envelope("SUZLON", "2026-07", AUTO, ["2026-07-01", "2026-07-02"],
                  sector="automobile", price=987.65))
    _put(s / "SUZLON_2026-07_daily_feedback_log.json",
         feedback_log("SUZLON", "2026-07", [entry("2026-07-01", AUTO, actual=990.0)]))
    _put(s / "SUZLON_agent_weight_memory.json", weights("SUZLON", AUTO))
    _put(s / "archived_envelopes" / "2026-07_v1.json",
         envelope("SUZLON", "2026-07", AUTO, ["2026-07-01"], sector="automobile",
                  price=987.65))

    for d in ("banking_bfsi", "bfsi"):
        s = p / d / "RBLBANK"
        _put(s / "RBLBANK_2026-07_prediction_envelope.json",
             envelope("RBLBANK", "2026-07", BANK, ["2026-07-03"], sector="banking_bfsi"))
        _put(s / "RBLBANK_2026-07_daily_feedback_log.json",
             feedback_log("RBLBANK", "2026-07", [entry("2026-07-03", BANK)]))

    s = p / "automobile" / "MARUTI"
    _put(s / "MARUTI_2026-07_prediction_envelope.json",
         envelope("MARUTI", "2026-07", AUTO, ["2026-07-01"], sector="automobile"))
    _put(s / "MARUTI_agent_weight_memory.json", weights("MARUTI", AUTO))
    _put(p / "MARUTI" / "MARUTI_2026-06_prediction_envelope.json",
         envelope("MARUTI", "2026-06", AUTO, ["2026-06-02"]))
    _put(p / "LEGACYCO" / "LEGACYCO_dossier.json",
         {"ticker": "LEGACYCO", "observations": ["SECRET-DOSSIER"]})

    s = p / "it_sector" / "TCS"
    _put(s / "TCS_2026-07_prediction_envelope.json",
         envelope("TCS", "2026-07", AUTO, ["2026-07-31"], sector="it_sector"))
    _put(s / "TCS_2026-07_daily_feedback_log.json",
         feedback_log("TCS", "2026-07", [entry("2026-07-31", [])]))
    _put(s / "TCS_2026-08_daily_feedback_log.json",
         feedback_log("TCS", "2026-08", [entry("2026-07-31", [], actual=1250.0)]))

    s = p / "generic" / "NEWCO"
    _put(s / "NEWCO_2026-07-15_offmarket.json", {"date": "2026-07-15", "ticker": "NEWCO"})
    _put(s / "NEWCO_dossier.json", {"ticker": "NEWCO", "observations": ["SECRET-DOSSIER"]})
    (p / "generic" / "SUNPHARMA").mkdir(parents=True)

    _put(p / "automobile" / "ACME" / "ACME_2026-07_prediction_envelope.json",
         envelope("ACME", "2026-07", AUTO, ["2026-07-01"], sector="automobile"))
    _put(p / "generic" / "ACME" / "ACME_2026-07_prediction_envelope.json",
         envelope("ACME", "2026-07", GENERIC, ["2026-07-01"], sector="generic"))

    _put(p / "automobile" / "INOXWIND" / "INOXWIND_agent_weight_memory.json",
         weights("INOXWIND", AUTO))
    _put(p / "renewable_energy" / "INOXWIND" / "INOXWIND_agent_weight_memory.json",
         weights("INOXWIND", RENEW))

    _put(p / "automobile" / "_shared_ledger.json", {"lessons": ["SECRET-LESSON"]})
    _put(p / "_market_ledger.json", {"lessons": ["SECRET-LESSON"]})

    managed = root / "managed_tickers.json"
    _put(managed, MANAGED)
    return base, managed


def tree_state(root: Path) -> list[tuple[str, str]]:
    """Every directory and file under root, with each file's SHA-256."""
    out = []
    for q in sorted(root.rglob("*")):
        rel = q.relative_to(root).as_posix()
        if q.is_dir():
            out.append((rel, "<dir>"))
        else:
            out.append((rel, hashlib.sha256(q.read_bytes()).hexdigest()))
    return out
