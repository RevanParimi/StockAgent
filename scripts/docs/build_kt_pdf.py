"""Build the shareable KT PDF from docs/TECHNICAL_DESIGN.md, without the app.

Requires markdown2 and the repository's Playwright/Chromium development tools.
Intermediate HTML and checks go to ignored analysis_data/kt_20260915/.
"""
from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path
import re
import subprocess

import markdown2

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "docs/TECHNICAL_DESIGN.md"
PDF = ROOT / "docs/StockAgent-Three-Loops.pdf"

CSS = """
@page { size: A4; margin: 18mm 16mm 19mm; }
* { box-sizing: border-box; }
body { color: #233347; font: 10pt/1.48 Arial, sans-serif; margin: 0; }
h1, h2, h3 { color: #102b49; line-height: 1.18; }
h2 { break-after: avoid; margin: 26px 0 14px; font-size: 24pt; border-top: 5px solid #0b8b89; padding-top: 16px; }
h3 { font-size: 13pt; margin: 22px 0 9px; break-after: avoid; }
h2 + p { break-after: avoid; }
p { orphans: 3; widows: 3; }
a { color: #096f78; text-decoration: none; overflow-wrap: anywhere; }
table { width: 100%; border-collapse: collapse; margin: 15px 0 20px; font-size: 8.4pt; line-height: 1.42; }
thead { display: table-header-group; }
tr { break-inside: avoid; }
th { background: #102b49; color: white; text-align: left; padding: 9px 10px; }
td { border-bottom: 1px solid #d7e2e9; padding: 8px 10px; vertical-align: top; overflow-wrap: anywhere; }
tbody tr:nth-child(even) { background: #f1f6f8; }
code { font-family: Consolas, monospace; font-size: .88em; overflow-wrap: anywhere; }
pre { background: #f1f6f8; border-left: 3px solid #0b8b89; padding: 13px; font-size: 8.3pt; white-space: pre-wrap; overflow-wrap: anywhere; break-inside: avoid; }
li { padding-left: 3px; margin: 6px 0; }
blockquote { background: #f1f6f8; border-left: 3px solid #0b8b89; margin: 18px 0; padding: 10px 16px; }
.cover { height: 246mm; position: relative; break-after: page; padding-top: 32mm; }
.eyebrow { color: #0b8b89; font-size: 10pt; font-weight: bold; letter-spacing: 2px; text-transform: uppercase; }
.cover h1 { font-size: 48pt; margin: 24px 0 12px; letter-spacing: -2px; }
.subtitle { color: #284662; font-size: 29pt; line-height: 1.18; margin: 0 0 25px; }
.accent { width: 80px; border-top: 6px solid #0b8b89; margin: 25px 0; }
.deck { max-width: 430px; font-size: 13pt; line-height: 1.6; }
.cover-bottom { position: absolute; bottom: 14mm; border-top: 1px solid #d7e2e9; padding-top: 18px; width: 100%; }
.toc { break-after: page; }
.toc h2 { break-before: auto; }
.toc a { display: block; padding: 9px 0; border-bottom: 1px solid #d7e2e9; font-size: 11pt; }
.source-note { color: #56697a; font-size: 8.5pt; }
"""

JS = r"""
import { chromium } from 'playwright';
import fs from 'node:fs';
const opts = JSON.parse(process.argv[1]);
const browser = await chromium.launch({headless:true});
try {
  const page = await browser.newPage({viewport:{width:1000,height:1300}});
  await page.route('**/*', route => route.abort());
  await page.setContent(fs.readFileSync(opts.html,'utf8'), {waitUntil:'load'});
  await page.emulateMedia({media:'print'});
  await page.pdf({path:opts.pdf, preferCSSPageSize:true, printBackground:true,
    displayHeaderFooter:true, headerTemplate:'<div></div>',
    footerTemplate:`<div style="font-family:Arial;font-size:8px;width:100%;margin:0 16mm;color:#56697a;display:flex;justify-content:space-between"><span>StockAgent | KT ${opts.edition} | Source ${opts.digest}</span><span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>`});
  const overflow = await page.evaluate(() => [...document.querySelectorAll('pre,table')]
    .filter(e=>e.scrollWidth>e.clientWidth+2).length);
  console.log(JSON.stringify({html_overflow_elements:overflow}));
  if (overflow) process.exitCode=1;
} finally { await browser.close(); }
"""


def main() -> None:
    raw = SOURCE.read_bytes()
    source = raw.decode("utf-8-sig")
    edition = re.search(r"\*\*Edition:\*\* (\d{4}-\d{2}-\d{2})", source).group(1)
    # LF-normalized, matching check_kt_docs.canonical_sha256, so the footer
    # digest does not depend on the checkout's line endings.
    digest = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
    content = markdown2.markdown(source, extras=["tables", "fenced-code-blocks", "header-ids", "code-friendly"])
    content = re.sub(r"<h1[^>]*>.*?</h1>\s*", "", content, count=1, flags=re.S)
    headings = re.findall(r'<h2 id="([^"]+)">(.*?)</h2>', content)
    toc = '<section class="toc"><h2>Inside this guide</h2>' + ''.join(
        f'<a href="#{anchor}">{title}</a>' for anchor, title in headings) + '</section>'
    # Relative source links are useful in Markdown; do not embed local user
    # filesystem paths in a shareable PDF. Keep labels and internal links.
    content = re.sub(r'<a href="(?!#)[^"]*">(.*?)</a>', r'\1', content, flags=re.S)
    cover = f'''<section class="cover"><div class="eyebrow">Current implementation + PI roadmap</div>
    <h1>StockAgent</h1><p class="subtitle">Technical design<br>&amp; knowledge transfer</p>
    <div class="accent"></div><p class="deck">Understand the three loops, IPO evidence,
    portfolio decisions, profit and loss, scheduled work, and the changes still ahead.</p>
    <div class="cover-bottom"><strong>Edition {html.escape(edition)}</strong><br>
    Code-grounded explanations for engineering and product teammates.<br>
    <span class="source-note">Human testing duties are a separate document.<br>
    Source: docs/TECHNICAL_DESIGN.md · SHA-256 {digest[:12]}</span></div></section>'''
    work = ROOT / "analysis_data/kt_20260915"
    work.mkdir(parents=True, exist_ok=True)
    intermediate = work / "kt.html"
    intermediate.write_text(f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
                           f'<title>StockAgent — Technical Design and KT</title><style>{CSS}</style>'
                           f'</head><body>{cover}{toc}{content}</body></html>', encoding="utf-8")
    subprocess.run(["node", "--input-type=module", "-e", JS,
                    json.dumps({"html": str(intermediate), "pdf": str(PDF),
                                "edition": edition, "digest": digest[:12]})], cwd=ROOT, check=True)
    print(json.dumps({"pdf": str(PDF.relative_to(ROOT)), "source_sha256": digest,
                      "bytes": PDF.stat().st_size}))


if __name__ == "__main__":
    main()
