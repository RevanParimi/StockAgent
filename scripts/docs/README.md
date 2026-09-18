# KT documentation tools

These tools read source and documentation without starting StockAgent.
Use a local environment with [requirements.txt](requirements.txt); the PDF
builder also uses the repository's installed Playwright and Chromium.
Keep application/test dependencies separate from these rendering tools.

```text
python scripts/docs/build_kt_pdf.py
python scripts/docs/check_kt_docs.py
python scripts/docs/run_kt_checks.py
```

- `build_kt_pdf.py` renders `docs/TECHNICAL_DESIGN.md` through local Chromium
  into `docs/StockAgent-Three-Loops.pdf`. Browser requests are blocked. The
  footer records the Markdown hash; private local paths are not embedded.
- `check_kt_docs.py` checks local link targets, all SA story rows/dependencies,
  possible scheduler IDs, selected repository config values, PDF text and
  source hash, and the original PDF archive hash. Update its explicit config
  expectations when an accepted PI change alters the documented defaults.
  It does not prove link fragments or every sentence are semantically correct.
- `run_kt_checks.py` copies tracked source into a new isolated directory,
  excludes `.env` and runtime stores, disables dotenv and blocks external
  HTTP(S), sockets, SMTP, push and test subprocesses. Windows asyncio uses an
  explicitly created local socket pair; TestClient's in-process HTTP transport
  is allowed. This is a controlled harness, not an OS-level network sandbox.
  It runs the 30 existing files listed in the script, not the whole test suite.
  `--dependency-path PATH` can add an existing isolated test dependency folder.

Logs, intermediate HTML and machine-readable check summaries go to ignored
`analysis_data/kt_20260915/`. Do not commit those raw diagnostics. The original
PDF archive under `docs/archive/` is preserved separately and is never touched
by these tools. Regenerate and inspect the output PDF after source changes;
the checker does not regenerate it automatically or accept PI stories.
