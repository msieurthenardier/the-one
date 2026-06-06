# Leg: purge-by-age-primitive

**Status**: completed
**Flight**: [Daily Automatic Purge](../flight.md)

## Objective

Add `ChatSessionRepository.delete_older_than(agent_name, cutoff) -> list[str]` — an age-filtered, id-returning sibling of F2's `delete_all_for_agent` — that deletes an agent's chat sessions whose `updated_at` predates a cutoff and returns the deleted ids, with deterministic unit tests for the age filter, connector sweep, active-session survival, cross-agent isolation, returned ids, and rename composition.

## Context

- **Design decision DD2** (flight): the sweep (Leg 3) needs an **age predicate** (`updated_at < cutoff`) and the **ids** of deleted rows (not just a count) so it can evict the matching in-memory `_sessions` entries (DD4). F2's `delete_all_for_agent` is unconditional and count-returning — this leg adds the age-filtered, id-returning variant beside it.
- **DD2 primary form — SELECT-id-snapshot then DELETE** (not `RETURNING`): `RETURNING` is net-new to this repo (zero existing usage; F2's sibling used plain `DELETE`), and the deployed SQLite version is not pinned in this flight. SELECT-then-DELETE removes the build-sensitivity branch. The two statements run on the repo's **single serial connection**. Note this is NOT a transactional-isolation guarantee (the bare SELECT runs outside any transaction; only the DELETE+commit form one): the real safety comes from the connection being serial plus `updated_at` being **monotonic-forward** — see Edge Cases for why that makes the SELECT/DELETE gap benign and false-deletion-free.
- **DD3** (flight): comparison is **lexical** on the ISO-8601-UTC `updated_at` string. `updated_at` is always written via `now_iso()` (`models.py` `default_factory=now_iso`; every insert passes `session.updated_at`), and the active-session resolver already orders lexically on it (`ORDER BY updated_at DESC`). The cutoff Leg 3 passes is produced in the same `now_iso()` shape. This leg's tests use explicit ISO strings to pin the comparison.
- **Active connector session survives for free**: it is not special-cased — its `updated_at` is recent (bumped on each engaged turn), so it is `>= cutoff` and the predicate leaves it. Only *superseded* (aged) connector rows fall below the cutoff. This leg's tests assert exactly that.
- **Coverage split (DD4)**: these are the deterministic invariants — they live in fast unit tests here; the live composition is the Leg 4 behavior test.

## Inputs

What exists before this leg runs (post-Leg-1 line numbers):
- `the_one/db/repositories.py`: `class ChatSessionRepository` (`:940`); `delete_all_for_agent` (`:1070`, the F2 unconditional `DELETE … WHERE agent_name = ?` + `rowcount`); `purge_messages` follows it; `create()` inserts a `ChatSession` passing `session.updated_at`.
- `the_one/db/models.py`: `ChatSession` with `updated_at: str = Field(default_factory=now_iso)` — callers may pass an explicit `updated_at` (used to seed aged rows in tests).
- `tests/test_db_repositories.py`: `chat_repo` fixture (`:96`); `class TestChatSessionRepository` (`:2394`) with the F2 delete-all tests to mirror — `test_delete_all_for_agent_sweeps_interactive_and_connector` (`:2509`, the connector-seeding pattern: `ChatSession(id=…, agent_name="a1", platform="discord", connector_id="acc-1", channel_id="ch-1")`), `test_delete_all_for_agent_leaves_other_agents` (`:2531`), `test_delete_all_for_agent_empty_is_noop` (`:2545`), `test_rename_then_purge_composition` (`:2553`).

## Outputs

- `the_one/db/repositories.py`: `ChatSessionRepository.delete_older_than(agent_name: str, cutoff: str) -> list[str]` added immediately after `delete_all_for_agent`.
- `tests/test_db_repositories.py`: new tests in `TestChatSessionRepository` covering the age filter, connector sweep, active-session survival, cross-agent isolation, returned ids, empty no-op, and rename-then-sweep composition.

## Acceptance Criteria

- [ ] `delete_older_than(agent_name, cutoff)` deletes exactly the agent's sessions whose `updated_at < cutoff` (lexical) and returns the list of their ids; sessions with `updated_at >= cutoff` are left.
- [ ] A **connector-keyed** aged row (`platform`/`connector_id`/`channel_id` set, aged `updated_at`) is swept; a **recent** connector-keyed row (active session) is kept — proving connector rows are subject to the same age filter and the active session survives.
- [ ] Another agent's sessions are never touched, regardless of their `updated_at` (cross-agent isolation via the `agent_name` filter).
- [ ] Returns `[]` for an agent with no matching rows (empty / all-recent), issuing no error.
- [ ] The returned ids exactly equal the set of rows removed (verifiable by listing remaining sessions before/after).
- [ ] A **rename-then-sweep** composition holds: rename an agent with aged + recent rows, sweep by the new name with a cutoff between the two ages, assert the aged row is gone, the recent row remains, and a bystander agent is untouched.
- [ ] `ruff check` + `ruff format --check` clean on changed files.
- [ ] `tests/test_db_repositories.py` passes in full.

## Verification Steps

- `docker exec the-one pytest tests/test_db_repositories.py -x --timeout 30` → green, including the new `delete_older_than` tests.
- `docker exec the-one ruff check the_one/db/repositories.py tests/test_db_repositories.py` and `ruff format --check` on the same → clean.

## Implementation Guidance

1. **Add the method** after `delete_all_for_agent` (`repositories.py:1085`, before `purge_messages`):
   ```python
   async def delete_older_than(self, agent_name: str, cutoff: str) -> list[str]:
       """Delete an agent's chat sessions whose ``updated_at`` predates
       ``cutoff`` and return the ids of the deleted rows.

       Age-filtered, id-returning sibling of :meth:`delete_all_for_agent`
       (M13 F03). Used by the daily purge sweep (Leg 3), which needs the
       ids to evict the matching in-memory ``_sessions`` entries.

       Comparison is LEXICAL on the ISO-8601-UTC ``updated_at`` string —
       sound because ``updated_at`` is always written via ``now_iso()``
       and the active-session resolver already orders lexically on it.
       ``cutoff`` must be a ``now_iso()``-shaped string (the caller builds
       it as ``(now_utc - timedelta(days=N)).isoformat()``).

       Name-keyed and rename-safe for the same reasons as
       :meth:`delete_all_for_agent`. Returns ``[]`` when nothing matches.

       Form: SELECT the ids, then DELETE the same predicate, on the
       serial connection (DD2 — no ``RETURNING``). Not atomic, but safe:
       ``updated_at`` only moves forward, so an interleaving bump can only
       move a captured row OUT of the predicate, never an uncaptured row
       in — the returned ids are always a superset of rows actually
       deleted (no false deletion; at worst a benign spurious eviction
       downstream).
       """
       async with self.conn.execute(
           "SELECT id FROM chat_sessions WHERE agent_name = ? AND updated_at < ?",
           (agent_name, cutoff),
       ) as cur:
           ids = [row[0] for row in await cur.fetchall()]
       if ids:
           await self.conn.execute(
               "DELETE FROM chat_sessions WHERE agent_name = ? AND updated_at < ?",
               (agent_name, cutoff),
           )
           await self.conn.commit()
       return ids
   ```

2. **Tests** (`tests/test_db_repositories.py`, in `TestChatSessionRepository`) — mirror the F2 delete-all tests' seeding style. Use explicit ISO strings so the lexical comparison is pinned, e.g. `AGED = "2020-01-01T00:00:00+00:00"`, `RECENT = "2099-01-01T00:00:00+00:00"`, `CUTOFF = "2050-01-01T00:00:00+00:00"`.
   - **age filter + returned ids**: agent `a1` with an aged interactive row and a recent interactive row; `delete_older_than("a1", CUTOFF)` returns `["<aged id>"]`; remaining `list(agent_name="a1")` is just the recent one.
   - **connector sweep + active survives**: `a1` with an aged connector-keyed row (seed `platform="discord", connector_id="acc-1", channel_id="ch-1", updated_at=AGED`) and a recent connector-keyed row (same channel shape, `updated_at=RECENT`); sweep deletes only the aged one; the recent (active) one remains. *(Add a one-line test comment: the "recent `updated_at`" here is the unit-level proxy for an active session — true most-recent-by-external-key resolution is Leg 4's behavior gate, per the DD4 coverage split — so a future reader doesn't mistake the proxy for the real invariant.)*
   - **cross-agent isolation**: `a2` with an aged row; sweeping `a1` returns only `a1`'s ids and leaves `a2`'s aged row intact.
   - **empty / all-recent no-op**: `a1` with only a recent row → `delete_older_than("a1", CUTOFF)` returns `[]`, row remains; also an agent with no rows → `[]`.
   - **boundary (`updated_at == cutoff` kept)**: seed a row with `updated_at = CUTOFF` exactly; `delete_older_than("a1", CUTOFF)` returns `[]` and the row remains (strict `<` → exactly-at-cutoff is kept, pinning DD3's "predates the window" semantics).
   - **rename-then-sweep**: mirror `test_rename_then_purge_composition` (`:2553`) but with an aged + a recent row; `rename("a1","a1-renamed")`; `delete_older_than("a1-renamed", CUTOFF)` removes the aged, keeps the recent, bystander `a2` untouched.

## Edge Cases

- **Benign spurious eviction (documented, accept)** — and why no *false deletion* is possible: if, between the SELECT and the DELETE, a concurrent coroutine on the shared connection *bumped* a captured row's `updated_at` to `>= cutoff`, the DELETE re-evaluates the predicate and skips it — so the returned id list could name a row that still exists. The guarantee that makes this safe is **`updated_at` monotonicity**: it only ever moves *forward* (every bump is `now_iso()`), so an interleaving write can only move a captured row *out* of the predicate, never move an uncaptured row *into* it. Therefore the returned ids are always a **superset** of rows actually deleted — the DELETE can never remove a row the SELECT didn't capture. Downstream (Leg 3) the worst case is a spurious `_sessions` eviction of a session that still has a DB row; it is simply reloaded on next access (same as a reaper eviction). Harmless; not worth a heavier lock.
- **Lexical-comparison soundness**: all test timestamps must be the same ISO-8601-UTC shape as `now_iso()` (with `+00:00`), or the lexical comparison is meaningless. Do not mix space-separated `datetime('now')` strings into the test seeds.
- **`updated_at == cutoff` boundary**: the predicate is strict `<`, so a row exactly at the cutoff is **kept**. This matches "predates the window." Tests should not depend on the exact-equality boundary, but a reviewer may add one asserting `==cutoff` is kept.
- **No FK/cascade interaction**: like `delete_all_for_agent`, the v5 FK drop means this neither cascades nor is blocked; no agent-existence check.

## Files Affected
- `the_one/db/repositories.py` — `ChatSessionRepository.delete_older_than` (age-filtered, id-returning).
- `tests/test_db_repositories.py` — new `delete_older_than` tests in `TestChatSessionRepository`.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed` (the Flight Director handles `completed`/commit at flight end)
- [ ] Check off this leg in flight.md — *(deferred: Flight Director does this at flight end)*
- [ ] Commit — *(deferred: this flight commits once after the last autonomous leg; do NOT commit here)*
