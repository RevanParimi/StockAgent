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
  It also guards the KT header, using read-only local `git`. The `Code
  inspected` revision must be a commit that is an ancestor of HEAD, no newer
  than the edition date. It must contain every source file the KT links and
  every job ID in section 9's table. Linked sources changed since that revision
  are listed under `header.linked_sources_changed_since_revision`, not failed.
  Re-read the affected sections before moving the revision forward. The guard
  cannot detect changed behaviour inside a file that already existed.
- The builder and checker both hash `TECHNICAL_DESIGN.md` over
  **LF-normalized** bytes, so CRLF and LF checkouts agree on PDF freshness.
- `kt_manifest.py write|verify` records review-input manifests in
  committed-blob terms. For each file it records git's own blob id
  (`git hash-object`, compare with `git rev-parse REV:PATH`) and the SHA-256
  of those same blob bytes. It refuses to record a file whose bytes do not
  reproduce git's id. Some older files are committed with CRLF, so do not
  assume LF normalization equals the blob. `verify` checks the working tree;
  `verify --rev REV` checks a commit. Regenerate the manifest last, after
  every payload edit.
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
