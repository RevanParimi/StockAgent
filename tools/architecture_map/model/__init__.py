"""The architecture model: generated facts and curated meaning (MAP-001).

`generate.py` writes `docs/architecture-map/model.json` and `TREES.md` from the
code and from `curated/`; `check.py` is the guard that fails when they disagree.
Standard library and PyYAML only, and every reader takes the repository root, so
tests run it on small fixture trees. It reads source files; it imports none.
"""
