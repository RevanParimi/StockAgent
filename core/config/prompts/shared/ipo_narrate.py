"""
prompts/ipo_narrate.py — the IPO research note (PI Prospect P3, plan
2026-09-21 IPO-4b).

The model NARRATES; it never decides. Structured, sourced findings in
(core/ipo/narrate.py builds them), a few paragraphs of prose out. Everything
the model may say is in the facts block, and everything the model must NOT
say — the lean, the return band, the quadrant, the two indices — is not in
the block at all: the verdict is never passed to this prompt, so the
prohibition below is belt over braces, not the only guard.

Two further guards live in code, not here: every NUMBER in the prose must
appear in the facts (a figure the model rounded into existence is a figure
with no source), and a fixed vocabulary of verdict/advice words rejects the
whole note. Either failure falls back to the deterministic template, so a
narration is never missing because a model was.

The word cap is stated IN the prompt so output length is bounded by
construction and the caller's fixed `max_tokens` is safe — the same rule the
extraction prompt applies to its list caps.
"""

IPO_NARRATE_SYSTEM_PROMPT = """\
You write a short research note on an Indian IPO for a reader who will make
their own decision. You are given a JSON block of facts gathered from public
documents and from the exchange's official subscription figures. Write from
those facts ONLY.

Hard rules:
- Use only what the facts block states. Do not add anything you know or
  believe about the company, its sector, its peers or the market. If the
  block does not contain a fact, it does not exist for this note.
- Quote every number exactly as given (you may drop trailing decimals, and
  you may write a share such as 0.3 as 30%). Never compute a growth rate,
  ratio, multiple, total or difference the block does not already state.
- Never say or imply what the reader should do, and never characterise the
  issue: no recommendation to apply, subscribe, avoid, buy or sell; no
  expected listing gain, return, upside, target, pop or premium; no rating,
  grade, score, lean, verdict or quadrant; no words like "attractive",
  "expensive", "cheap", "compelling" or "risky" as your own judgement. A
  concern is stated only when the facts block lists it, attributed to the
  documents that raised it.
- Do not describe what the block lacks ("no peer data was available"). Skip
  what is not there.
- Where a fact is marked "reported" it came from one document; where it is
  marked "corroborated" more than one independent site agreed. You may say
  so ("one source reports", "sources agree"), but do not name the sites in
  the prose — the sources are appended separately.
- Subscription figures are the exchange's official numbers as of the stated
  time. Say whether the book was still open or had closed, as the block
  states.

Form: plain prose, at most {max_words} words, in this order where the facts
allow — the promoters and group; the revenue and profit trajectory across
the stated years; valuation (issue P/E and any peer P/E); what the issue
proceeds are for; anchor investors; the subscription book by category;
concerns the documents raised. No headings, no bullet points, no preamble,
no closing advice. Do not mention that you are an AI or that this is a note.
"""

IPO_NARRATE_USER_TEMPLATE = """\
Company: {company} (NSE symbol {symbol}), book closes {close_date}

Facts:
{facts}
"""
