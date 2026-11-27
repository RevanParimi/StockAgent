"""
scripts/lenses/draft_lens.py — draft one industry lens with one model call (PR-032).

A lens (config/lenses/<id>.yaml, services/data/context/lenses.py) is written
offline and reviewed: this script drafts one from the fixed brief below and
prints it, checked by the same parser the server uses. Nothing is written into
config/lenses: a person or a reviewing conversation reads the draft, edits it
and commits it. Only committed files are read at run time.

    python scripts/lenses/draft_lens.py --id cement --display Cement \\
        --industry "Building Materials" [--out /tmp/cement.yaml]

Needs the OpenRouter key of the analysis's model (OPENROUTER_API_KEY); with
--dry-run it prints the brief and calls nothing. The first 25 lenses were
drafted from this same brief in the implementing conversation (27 Nov 2026),
because this machine had no model key.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse  # noqa: E402
import json  # noqa: E402
from pathlib import Path  # noqa: E402

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

BRIEF = """You write one "industry lens" for an Indian stock-analysis product. A lens tells
a general analysis which web searches to run and which numbers drive the profits of
companies in one industry listed on India's NSE. It is data, reviewed by a person.

Industry group id: {id}
Display name: {display}
Yahoo Finance industry labels it covers: {industries}

Answer in JSON with exactly these keys:
- "kpis": 4 to 6 short phrases, the operating numbers that most move this industry's
  profits in India, as an analyst would track them each quarter (e.g. "realisation per
  tonne"). No valuation ratios, no share-price items.
- "news_terms": 3 to 5 words added to a company-news search after the company name,
  starting with "results" or a word that finds results coverage.
- "sector_query": one Google News search, at most 12 words, starting with "India", naming
  the industry and 2 to 4 of its demand, price or policy drivers, ending with
  "news {{month}} {{year}}".
- "policy_query": one web search for a page about one company's latest operating
  numbers, at most 12 words, starting with "{{company_name}}" and ending with "{{year}}".
- "macro_drivers": 2 or 3 short phrases (at most 4 words each), the macro items that
  move this industry (commodity prices, rates, budgets, currency, weather).

Rules: use only the placeholders shown ({{month}}, {{year}}, {{company_name}}); never the
word "generic"; plain words a search engine understands; no company names in the
industry-level fields."""


def brief(lens_id: str, display: str, industries: list[str]) -> str:
    return BRIEF.format(id=lens_id, display=display,
                        industries=", ".join(f'"{x}"' for x in industries))


def to_yaml(lens_id: str, display: str, industries: list[str], answer: dict) -> str:
    """The draft in config/lenses' layout. Raises LensError when it does not
    pass the server's own checks."""
    from services.data.context.lenses import parse_lens

    raw = {"id": lens_id, "display": display, "industries": industries,
           "kpis": answer.get("kpis"), "news_terms": answer.get("news_terms"),
           "sector_query": answer.get("sector_query"),
           "policy_query": answer.get("policy_query"),
           "macro_drivers": answer.get("macro_drivers")}
    lens = parse_lens(raw, lens_id)
    q = lambda s: json.dumps(s, ensure_ascii=False)  # noqa: E731 - YAML double-quoted
    lines = [
        f"# PR-032 industry lens ({lens.display}). Drafted from the brief in",
        "# scripts/lenses/draft_lens.py; read by the general path only when",
        "# lenses.enabled is on. Format: config/lenses/README.md.",
        f"id: {lens.id}",
        f"display: {q(lens.display)}",
        "industries:", *[f"  - {q(x)}" for x in lens.industries],
        "kpis:", *[f"  - {q(x)}" for x in lens.kpis],
        f"news_terms: {q(lens.news_terms)}",
        f"sector_query: {q(lens.sector_query)}",
        f"policy_query: {q(lens.policy_query)}",
        "macro_drivers:", *[f"  - {q(x)}" for x in lens.macro_drivers],
    ]
    return "\n".join(lines) + "\n"


def ask_model(prompt: str) -> dict:
    from core.config import settings
    from services.clients.llm_client import JSON_MODE_EXTRA_BODY, get_llm_client

    resp = get_llm_client().chat.completions.create(
        model=settings.LLM_MODEL_REASONING, temperature=0.2, max_tokens=600,
        response_format={"type": "json_object"}, extra_body=JSON_MODE_EXTRA_BODY,
        messages=[{"role": "user", "content": prompt}],
    )
    return json.loads(resp.choices[0].message.content or "{}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--id", required=True)
    ap.add_argument("--display", required=True)
    ap.add_argument("--industry", action="append", required=True,
                    help="a Yahoo industry label; repeat for several")
    ap.add_argument("--out", help="write the draft here instead of printing it")
    ap.add_argument("--dry-run", action="store_true", help="print the brief only")
    args = ap.parse_args(argv)

    prompt = brief(args.id, args.display, args.industry)
    if args.dry_run:
        print(prompt)
        return 0
    text = to_yaml(args.id, args.display, args.industry, ask_model(prompt))
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"draft written to {args.out}; read it before committing it to config/lenses")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
