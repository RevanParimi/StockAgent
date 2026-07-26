# ⚖️ Legal & Compliance Checklist

> What we must consider before StockAgent serves anyone beyond its owner — and **why**
> each item is on the list (the concrete cause, not the theory).
>
> **This document is engineering due diligence, not legal advice.** Before public signups
> or any paid tier, a qualified Indian securities lawyer reviews this list.

**The one-table summary:**

| Area | Trigger point | Severity if ignored |
|---|---|---|
| SEBI (advice/research regs) | First stranger; any payment | 🔴 Regulatory action |
| Autopilot for others | Ever | 🔴 Never do without licenses |
| DPDP Act (data protection) | First external user's data | 🟠 Fines, real user harm |
| Market data licensing | Commercial redistribution | 🟠 ToS/licensing claims |
| Public repo hygiene | Already live today | 🟠 Security incidents |
| Multi-tenancy security | User #2 | 🔴 Cross-user data leak |
| ToS / Privacy / Disclaimers | First external user | 🟡 No liability shield |

---

## 1. SEBI — the big one 🇮🇳

Two regulation families apply to what this product does:

**Investment Adviser (IA) Regulations, 2013.** Registration is required when someone is
*"engaged in the business of providing investment advice to clients, for consideration."*

- **Cause of exposure:** the advisor pipeline produces **personalized** BUY / TRIM / SELL
  verdicts on a specific user's actual holdings, sized to their positions. That is the
  textbook shape of investment advice — personalization is precisely what separates
  "advice" from "research."
- **What keeps today's deployment out of scope:** one user (the owner), no clients, no
  consideration, no business. A personal tool is a personal tool.
- **What changes the answer:** strangers as users (the "business" prong strengthens), and
  *any* payment (the "consideration" prong triggers — note: a paid chat subscription could
  be argued to be consideration for the advice around it, even if the advice screen itself
  is free).

**Research Analyst (RA) Regulations, 2014.** Cover preparing/publishing research reports
and recommendations on securities *to the public*.

- **Cause of exposure:** our per-ticker verdict cards (verdict + confidence + rationale)
  distributed to many users are functionally research reports. The existing "labelled
  research, never advice" framing (already enforced in the narrator prompt) points here —
  RA is the **lighter, more realistic registration path** than IA for the product shape we
  have, and SEBI has been easing RA entry requirements in recent years.

**Autopilot — the red line.** Auto-executing trades for *other people* is not an advice
question anymore; it's portfolio management (PMS licensing: large net-worth requirements,
minimum ticket sizes) or broker territory.
- **Rule baked into the roadmap:** autopilot remains **owner-only, forever**, unless the
  company someday holds the licenses. Other users get suggestions they act on themselves.
  This single rule removes the most dangerous exposure entirely.

**Practical sequence:** friends & family (free, invite-only, research-labelled) → low risk,
proceed. Public signups or paid tier → lawyer first, likely RA registration path, possibly
restructuring output so external users see ticker research (shared verdicts) rather than
position-sized personal instructions.

---

## 2. DPDP Act, 2023 — India's data protection law 🔐

- **Cause of exposure:** the moment user #2 signs up, we store their **financial personal
  data** — email, portfolio holdings, transaction history. Holdings data is exactly the
  kind whose leak causes concrete harm (it reveals wealth, positions, behavior). The DPDP
  Act requires: consent with a clear purpose notice, using data only for that purpose,
  deletion on request, and breach notification.
- **What it means in practice (cheap if done at signup, painful retrofitted):**
  - Signup includes a plain-language purpose notice + consent checkbox.
  - A working "delete my account and data" path (the per-user data layout makes this
    genuinely easy — one user_id scope to erase).
  - Backups containing user data are access-controlled; know where they live
    (currently: nightly volume backup email — that becomes multi-user PII the moment
    user #2 exists, so the backup channel and storage need the same care as the DB).
  - Push subscription endpoints and email addresses are PII too — prune on logout/delete.

---

## 3. Market data & third-party ToS 📈

- **Cause of exposure:** prices come via unofficial channels (yfinance, nsepython-style
  scraping of NSE endpoints) and news via a Google-results wrapper (Serper). Tolerated for
  a personal tool; **redistributing** exchange data and scraped headlines to a paying user
  base is exactly what exchange data-licensing policies and provider ToS exist to catch.
  NSE licenses real-time/derived data commercially; Google-results wrappers restrict
  commercial republication.
- **Practical sequence:** friends-scale — low risk, unchanged. Productization — budget for
  a licensed market-data feed as a real line item, and re-read Serper's commercial terms.
  Delayed EOD data (our main use) is the cheapest licensing tier; the architecture doesn't
  change, only the fetcher behind the cache does.

---

## 4. Public repo — live today, so already binding 🌍

Concrete causes, each already real:

1. **Secrets in git history are forever.** Forks, clones, and archive caches keep history
   even after a force-push "removal." Standing rules (already in effect): secrets only in
   Railway env vars; **any** leaked key is rotated immediately, never just deleted; prod
   endpoint/cash specifics stay out of committed docs.
2. **Public prompts are an attack surface.** Our exact ingestion and analysis prompts are
   readable. An adversary who wants to move a verdict can craft headlines/filings text
   *knowing precisely what the pipeline will do with them* (prompt injection via the news
   pipeline). Mitigations: ingestion treats all fetched text as untrusted data (never as
   instructions), and the deterministic advisor rules — not raw LLM output — remain the
   only thing that can trigger a trade.
3. **Public infra layout = reconnaissance map.** Route names, job schedules, and the
   auth model are readable. This is survivable **only** because auth actually gets turned
   on (M0) — security through obscurity isn't available to a public repo, so there must
   be none of it.
4. **No LICENSE file.** Legally "all rights reserved," but the code is world-readable and
   fork-able in practice. Decision needed at productization: pick a license deliberately,
   or take the repo private (simplest for a commercial product; also retires cause #2
   and #3 substantially).

---

## 5. Multi-tenancy security — the user #2 problems 🚪

Each of these is benign today with one user and becomes a live vulnerability with two:

1. **IDOR (insecure direct object reference).** Today `user_id` is a parameter/default
   (`PORTFOLIO_DEFAULT_USER_ID`), not an identity the server verifies. With 2+ users, any
   caller who can name another user's id can read their portfolio. **Fix (M0, the heart of
   the auth work): `user_id` is derived server-side from the session token, never accepted
   from the client.**
2. **Shared stores need tenant scoping everywhere.** Portfolios are per-user directories
   (good), but every new table (sessions, quotas, feedback events, outbox) must carry and
   filter by `user_id` from day one. A single unscoped query is a cross-tenant leak.
   The semantic chat cache has its own version of this rule: user-specific answers must
   never enter the shared cache (Blueprint 3, safety rule 1).
3. **Abuse = wallet drain.** Open endpoints that trigger LLM calls (chat, `/analyse`) are
   a costs attack, not just a data attack. Fix: auth on every LLM-triggering route +
   per-user quotas (M0) + per-user cost tripwire (Blueprint 4).
4. **Admin/ops endpoints.** `X-Scheduler-Key` enforcement exists but is dormant until the
   env var is set in Railway. That switch flips **before** user #2, full stop.
5. **Backups are multi-tenant the moment users are.** See DPDP above — same cause, listed
   here because the fix (access-controlled backup destination) is an ops task, not code.

---

## 6. The paperwork floor 📄

Needed at the first external user (templates exist; a lawyer tightens them later):

- **Terms of Service** — research-not-advice, no guarantee of returns, user bears trading
  decisions, service-availability disclaimer, quota/fair-use terms.
- **Privacy policy** — what we store (email, holdings, watchlist, usage), why, where
  (Railway; region), deletion path (DPDP alignment).
- **In-product disclaimer** — the "labelled research" line, already system-enforced in the
  narrator, stays on every advice surface and every brief/email footer.

---

## Decision gates, restated as a timeline

| Gate | What must be true before passing it |
|---|---|
| **User #2 (friend, free)** | Auth on · SCHEDULER_KEY set · tenant-scoped queries · consent notice + ToS/privacy page · backups access-controlled |
| **Public signups (free)** | Lawyer consult (SEBI RA path) · DPDP full compliance · repo license/private decision · data-feed licensing review |
| **Any payment** | SEBI registration question resolved **first** (consideration prong) · billing ToS |
| **Autopilot for anyone but the owner** | Licensed entity or never. Default: **never** |

*Written 2026-07-26 as part of the scaling program. Companions:
[SCALING_VISION.md](SCALING_VISION.md), [SCALING_BLUEPRINTS.md](SCALING_BLUEPRINTS.md).*
