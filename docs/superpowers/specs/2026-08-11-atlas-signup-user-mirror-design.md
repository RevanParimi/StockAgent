# Atlas signup → user mirror (C3 gap) — design

**Date:** 2026-08-11
**Status:** IMPLEMENTED 2026-08-11 — see §10 for the two as-built refinements
**Closes:** the "signup→atlas.db users wiring (C3 gap)" item, open since Phase C

---

## 1. Problem

`POST /auth/signup` writes the new account to `data/users.db` and nowhere else.
[`services/api/routes/auth_api.py`](../../../services/api/routes/auth_api.py)
calls `user_store.create_user(...)` in both branches and makes no `atlas_store`
call at all.

Meanwhile `atlas_store.user_ids()` answers `SELECT user_id FROM users` against
**`data/atlas.db`**. That list is the fan-out set: it is what the morning brief
and autopilot iterate over once the Atlas plane is live.

The two facts together mean: **after the C11 cutover, anyone who signs up is
invisible.** They authenticate fine — auth reads `users.db`, which is correct —
but they receive no brief, no autopilot, nothing. The account looks healthy from
the inside and produces silence from the outside.

This does not endanger the cutover itself. `scripts/atlas_etl.py` performs a
one-time `INSERT OR IGNORE INTO users … SELECT … FROM src.users`, so every
account existing at cutover time is migrated and the owner-presence validation
passes. The gap opens strictly *after* the flip — which is to say, exactly when
the first friend is invited.

The delete side was already wired: `auth_api` calls
`atlas_store.delete_user_completely(uid)` on account deletion. Only the create
side was missed.

---

## 2. Constraint that shapes the whole design

`atlas_store._get_conn()` performs `mkdir` + `executescript(_SCHEMA)` on first
use. **Any** `atlas_store` write therefore *creates* `data/atlas.db`.

The watchdog's `atlas_cutover_pending` check treats an unexplained `atlas.db` as
a dirty pre-flight and returns `blocked`. `runner._run_preps` deliberately skips
blocked entries. So an ungated mirror plus a single pre-cutover signup would:

1. create `atlas.db`,
2. flip the milestone to `blocked`,
3. suppress Saturday's automatic ETL + validation prep,
4. and talk the operator out of the cutover this work exists to support.

**Therefore the mirror must return before opening a connection when the flag is
off.** This is not a stylistic preference; it is the difference between helping
and sabotaging the cutover.

---

## 3. Architecture

One function, one call site, one invariant.

`users.db` stays the identity source of truth and the auth path is untouched.
`atlas.db`'s `users` table is a **derived mirror** with exactly two jobs: be the
FK target for the seven dependent PII tables, and populate `user_ids()`.

Because it is derived, it is repairable: re-running the idempotent ETL backfills
anything missing. That is what makes a non-fatal write safe — provided the drift
is actually detected, which is component 3.

---

## 4. Component 1 — `atlas_store.mirror_user()`

```python
def mirror_user(user_id: str, *, users_db: Path | str = Path("data/users.db")) -> bool
```

**Body, in order:**

1. `if not enabled(): return False` — first statement, before `_get_conn()`.
2. `_lock`, then `conn.commit()` (ATTACH cannot run inside a transaction).
3. `ATTACH DATABASE ? AS src`.
4. The ETL's own statement, narrowed:
   `INSERT OR IGNORE INTO users (user_id, email, pw_hash, display_name, role,
   created_at, consent_at) SELECT … FROM src.users WHERE user_id = ?`
5. `commit()`, `DETACH DATABASE src` in a `finally`.
6. Return whether the row is present in `atlas.db` afterwards.

Never raises, matching `upsert_user_instrument` and `user_ids()` — every
`atlas_store` entry point returns a falsy value and logs rather than propagating.

`users_db` is a keyword parameter defaulting to the same literal `run_etl` uses,
so `atlas_store` acquires no new imports and tests can point it anywhere.

**Why ATTACH rather than passing fields in:** `atlas.db.users.pw_hash` is
`NOT NULL`, but `user_store._row_to_user()` deliberately omits the hash. Reusing
the ETL's `INSERT … SELECT` keeps the hash inside SQLite, and — more importantly
— means the mirrored column set is written down **once**. Signup and the ETL
cannot drift apart, because they are the same statement.

---

## 5. Component 2 — call site in `signup`

Both branches mirror, but placement differs:

- **Owner branch** — immediately after `create_user(...)`.
- **Invited branch** — **after `consume_invite` succeeds.** On an invalid code
  the existing code deletes the just-created user and raises 403. Mirroring
  before that point would strand an orphan `atlas.db` row referencing a user
  that no longer exists in `users.db`.

Wrapped in `try/except` at the call site (defense-in-depth; the callee already
guards), logging a warning. **Signup never fails because of the mirror** — the
Atlas plane is a derived index, not the account.

---

## 6. Component 3 — the `users_mirrored` invariant

The precedent for a swallowed failure is `PortfolioStore._sync_instrument`,
whose docstring justifies it: "the index is a derived backstop **rebuilt
nightly**." There is no nightly rebuild for users. Without detection, a failed
mirror is a person who silently receives nothing — the exact failure class the
watchdog was built to eliminate.

New check in `core/ops/watchdog/checks.py`, new entry in
`config/milestones.yaml`:

| Condition | State | Detail |
|---|---|---|
| `not atlas_store.enabled()` | `satisfied` | Atlas plane off; users.db is the sole identity store |
| counts equal | `satisfied` | `N users, all mirrored` |
| atlas short | `pending` | names the shortfall; action = re-run the idempotent ETL |
| atlas ahead | `pending` | a delete cascade half-failed |

Comparing `user_store.count_users()` with `len(atlas_store.user_ids())`. Being
`satisfied` while the flag is off means it stays silent until the cutover makes
it meaningful.

---

## 7. Adjacent fix — the same landmine on the delete path

`delete_user_completely` calls `_get_conn()` unconditionally. It is
*deliberately* not flag-gated, because DPDP erasure must run regardless of the
flag — that reasoning is sound and stays.

But pre-cutover it would materialise `atlas.db` and block the cutover exactly as
described in §2. Fix: skip step 1 when the `atlas.db` file does not exist. A
nonexistent database holds zero rows, so the erasure is already complete and
DPDP semantics are bit-for-bit unchanged.

Currently latent, not live: the owner cannot self-delete (`auth_api` returns 403)
and no other accounts exist. Included because it is two lines and the same
failure.

---

## 8. Testing

TDD, tests written first.

**The load-bearing test** — flag off, call `mirror_user()`, then assert
`data/atlas.db` **does not exist on disk**. Asserted on the filesystem, not on
the return value: the return value would pass even if the file were created,
and the file is the thing that blocks the cutover.

`mirror_user`:
- copies the row when enabled, `pw_hash` and `consent_at` included
- idempotent — twice leaves exactly one row
- unknown `user_id` → `False`, no row written
- missing `users.db` → `False`, no raise

`signup`:
- mirrors the owner (first-user branch) when enabled
- mirrors an invited member when enabled
- **invalid invite leaves no atlas row** (the ordering guarantee in §5)
- returns 200 when `mirror_user` is **patched to raise**. `mirror_user` does not
  raise in normal operation (§4); this test exercises the call-site `try/except`
  from §5, so the guard cannot be deleted as dead code without a test turning red

`users_mirrored`: each of the four rows in §6's table.

Delete path: with `atlas.db` absent the call creates no file; with it present the
cascade still runs.

---

## 9. Out of scope

`sessions`, `invites`, `chat_usage`. Verified that `atlas_store` contains no read
or write of any of the three — they exist purely as ETL destinations for schema
and FK completeness. Mirroring them live would be speculative work in service of
no reader. The ETL still copies them once at cutover.

Also out of scope: switching auth to read `atlas.db`. `users.db` remains the
identity SoT, before and after the cutover.

---

## 10. As built (2026-08-11)

Implemented as designed, plus two refinements found while writing the tests:

1. **The call site passes the path rather than trusting the default.** §4 kept
   `users_db` defaulting to the literal `Path("data/users.db")`; `signup` now
   calls `mirror_user(uid, users_db=user_store.db_path())` via a new
   one-line accessor. Re-deriving the literal in a second module means that if
   `user_store._DB_PATH` ever moves — which is exactly what every test does —
   the mirror silently reads a *different* file than the one signup just wrote
   to, and reports "user not found" for a user that plainly exists.

2. **A missing `users.db` returns before the ATTACH, not through it.** `ATTACH`
   *creates* an empty database at a nonexistent path, so relying on the
   `no such table: src.users` failure would leave a stray file behind on every
   miss. The existence check is now explicit.

`test_a_failed_mirror_leaves_the_connection_usable` was written against a real
but table-less DB for the same reason: with the early return above, a
nonexistent path never reaches the `ATTACH`, so it would no longer exercise the
`finally: DETACH` that keeps the connection usable after a failure.

Files: `services/data/stores/atlas_store.py` (`mirror_user`, delete-path guard),
`services/data/stores/user_store.py` (`db_path`),
`services/api/routes/auth_api.py` (`_mirror_to_atlas` + both branches),
`core/ops/watchdog/checks.py` (`users_mirrored`), `config/milestones.yaml`,
`tests/unit/test_atlas_signup_user_mirror.py` (15),
`tests/unit/ops/test_watchdog_checks_more.py` (+6).
