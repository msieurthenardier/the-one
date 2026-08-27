# Leg: external-write-provenance-and-concurrency

**Status**: completed
**Flight**: [External Client Access](../flight.md)

## Objective

Make external-client *writes* first-class: log them as `source='external'` with the
principal's identity, honor the per-agent approval flag exactly as the agent's own
writes do, close the last-writer-wins clobber on the direct-write path with a
field-scoped compare-and-swap that returns a truthful stale *tool result*, and pin
the governance invariant that no external principal can reach the approval-mode
setting or the revision transitions.

## Context

- Implements flight **DD3** (provenance: `source='external'` + `source_principal`),
  **DD4** (honor the approval flag), **DD5** (field-scoped CAS + stale tool-result on
  the direct path), and **DD6** (governance invariant, tested).
- Builds directly on Leg 1: `_calling_agent` already routes an external caller
  (`caller.source == EXTERNAL_SOURCE_NAME`) to the external registry and returns
  `agent_name`. This leg adds a provenance-aware companion resolver so the write
  tools can tag the revision with who wrote it. Both legs touch `_calling_agent`, as
  the flight anticipated.
- **The approval flow preserves external provenance for free.** `_transition`/
  `mark_applied` (`repositories.py`) only flip `status` + `resolved_at`; they never
  rewrite `source`. So an external write queued under approval mode keeps
  `source='external'`/`source_principal=<id>` through the operator's approve — no
  special handling on the approve path.
- **DD5 stale result is a tool result, not an HTTP 409** (Architect). A CAS miss
  returns `{applied_to_store: false, effective: "stale", field, current_value,
  proposed_value}` — the same non-retry-inducing shape family the approval branch
  already returns (`_apply_revision`), so neither an external client nor the agent is
  invited into a rewrite loop. HTTP 409 stays exclusive to the operator approve
  endpoint (an HTTP request).
- **DD5 scope (honest):** the CAS hardens the **direct-write branch of
  `_apply_revision` only**. The operator approve path (`api.py`, whole-row `save`),
  restore, and Studio edit remain whole-row writers — accepted single-operator debt
  (flight DD5). This leg does not touch them.

## Inputs

- Leg 1 landed (v36): the external principal, its routing in `_calling_agent`, the
  four external-credential endpoints, `EXTERNAL_SOURCE_NAME`.
- `agent_revisions` at v36 shape (`schema.py`): `source CHECK IN ('self','restore')`,
  no `source_principal` column.
- `_apply_revision(agent_name, field, text, apply)` (`surface.py`) with its
  approval-branch (`upsert_pending_revision`) and persist-branch (whole-row `save`
  then `append`), plus the two write tools calling `_calling_agent(ctx)`.
- The v23 rebuild ceremony (`schema.py`, `if version < 23:`) as the table-rebuild
  precedent; the v35 `>= 35` migration-test rewind pattern.

## Outputs

- Migration **v37** (`CURRENT_VERSION` → 37): `agent_revisions` rebuilt to widen
  `source CHECK` to `('self','restore','external')` and add `source_principal TEXT`
  (nullable), preserving all rows, the `restored_from` self-FK, and both FKs.
- `AgentRevision` model (`models.py`): `source` Literal widened; new
  `source_principal: str | None = None`.
- `AgentRevisionRepository` (`repositories.py`): `append` and `upsert_pending_revision`
  (both insert AND in-place-update branches) thread `source`/`source_principal`;
  `_row_to_model` maps the new column.
- `SQLiteAgentStore.compare_and_set_field(name, field, base_value, new_value) -> bool`
  (`repositories.py`): the field-scoped CAS.
- `_apply_revision` (`surface.py`): gains `source`/`source_principal` params (default
  `"self"`/`None`); persist branch uses the CAS + returns the stale result on a miss.
- `_calling_principal(ctx)` (`surface.py`): returns `(agent_name, source,
  source_principal)`; the two write tools use it.
- Governance regression tests (DD6).

## Acceptance Criteria

- [x] **AC1 — Migration v37.** `CURRENT_VERSION == 37`. Fresh DB and v36→v37 upgrade
      both yield `agent_revisions` with `source CHECK IN ('self','restore','external')`
      and a nullable `source_principal TEXT`. The rebuild preserves every existing
      row (values intact, `source_principal` NULL for them), the `restored_from`
      self-FK, and the `agent_name`/`restored_from` FK semantics. Idempotent on a
      schema-version rewind re-run (guarded on `source_principal` column presence).
      `PRAGMA foreign_keys == 1` asserted; envelope restores it to ON.
- [x] **AC2 — `restored_from` chain survives the rebuild.** A seeded restore row
      pointing at an earlier revision (a `restored_from` reference) still resolves
      after the rebuild — the self-FK is intact and the pointed-at row is unchanged.
- [x] **AC3 — External direct write is logged `external` with the principal.** With
      approval mode OFF, an external client's `update_my_description`/`system_prompt`
      applies directly and writes one `agent_revisions` row with `status='applied'`,
      `source='external'`, `source_principal = <the ext credential identifier>`. The
      agent's own write in the same conditions still logs `source='self'`,
      `source_principal IS NULL`.
- [x] **AC4 — External write honors the approval flag.** With approval mode ON, an
      external write does NOT persist; it enqueues a `pending` row carrying
      `source='external'`/`source_principal=<id>`; the operator approve applies it and
      the row remains `source='external'` (provenance preserved through approval).
      Dismiss leaves the field unchanged.
- [x] **AC5 — Field-scoped CAS closes the direct-path clobber.** The direct-write
      branch updates only the one field via `compare_and_set_field` (WHERE
      `name=? AND {field}=:base_value`). A concurrent whole-row change to the *other*
      field between base-capture and write is not clobbered by the CAS (only the
      revised column is written).
- [x] **AC6 — Stale direct write fails closed with a truthful tool result.** When the
      revised field drifted from `base_value` before the CAS, the write applies
      nothing and returns `{applied_to_store: false, effective: "stale", field,
      current_value, proposed_value}` — no `agent_revisions` row is written, the store
      is untouched, and the result does not claim success (non-retry-inducing).
      Returned identically to an external client and to the agent's own in-turn call.
- [x] **AC7 — Provenance touch-points complete (no read regression).** Reading any
      revision — including an `external` one — round-trips through `_row_to_model`
      into an `AgentRevision` without error (the model Literal admits `external`);
      `list_for_agent` and the operator `GET …/revisions` return external rows with
      their `source`/`source_principal`. A pending re-propose by a different principal
      updates `source`/`source_principal` on the deduped row (the UPDATE branch of
      `upsert_pending_revision`, not just insert).
- [x] **AC8 — Governance invariant (DD6).** An `ext_` credential is 403 on the
      operator control plane: `PUT …/approval-mode`, `POST …/revisions/{id}/approve`,
      `POST …/revisions/{id}/dismiss`, `POST …/revisions/{id}/restore`, and the Leg-1
      external-credential management endpoints — every `/api/…` path is off the
      confined mount. Its `get_my_configuration` projection contains no approval-mode
      field. No MCP tool exposes approval mode or a revision transition.
- [x] **AC9 — Suite green, with two named regressions updated in place.** `make
      test-unit` passes. Two existing tests WILL break and must be retargeted (not
      deleted-and-re-added — edit in place so blame records the shift):
      1. `tests/test_db_migration.py::TestSchemaV34::test_v34_fresh_db_has_agent_revisions_table`
         (~:5645) pins the exact 10-column *set* of `agent_revisions` on a fresh
         head DB — v37 adds `source_principal`, so its `expected` column set must gain
         `source_principal`.
      2. `tests/test_self_configuration_write.py::test_save_failure_leaves_no_orphan_log_row`
         (~:689) monkeypatches `SQLiteAgentStore.save` to raise and asserts no log row
         — the CAS direct path no longer calls `save`, so the monkeypatch goes inert
         and the write would succeed. Retarget it to monkeypatch
         `compare_and_set_field` (raise), preserving the saved-before-logged assertion.
      No other test pins `source IN ('self','restore')` behavior that this leg breaks
      (the browser seed INSERTs at `test_studio_self_configuration_history.py:63-68`
      and `queue.py:58` name explicit columns and omit `source_principal` → NULL —
      safe as-is, do not churn them).

## Verification Steps

- AC1/AC2: `test_db_migration.py` additions — a v37 shape/CHECK test (assert
  `external` is ACCEPTED and a bogus source REJECTED, and `source_principal` accepts
  NULL for self/restore and a value for external), a rewind idempotency test, and a
  `restored_from`-chain preservation test. **Two distinct setups (review Issue #2 —
  avoid the false-pass):** the `source_principal`-column-presence guard means a
  *stamp-only* rewind (`DELETE FROM schema_version WHERE version >= 37`) leaves the
  column present and short-circuits the rebuild, so it exercises nothing. Use it only
  for the *idempotency* test (guard correctly skips). For the *rebuild-firing* tests
  (shape/CHECK + chain-preservation), construct a genuine `source_principal`-less v36
  table — `DROP TABLE agent_revisions` + recreate at the v34 shape, seed rows
  (including a `restored_from` chain), stamp version 36, then `ensure_schema` — so the
  ceremony actually runs (mirror `TestSchemaV34`'s DROP-based rewind, NOT the
  `TestSchemaV35` stamp-only rewind). Assert `PRAGMA foreign_keys == 1`.
- AC3/AC4/AC6: `_apply_revision` tests driving both principals × both approval modes,
  asserting the logged `source`/`source_principal`, the pending→approve provenance,
  and the stale-result shape (monkeypatch/interleave a drift between base-capture and
  CAS; assert no row written and the store untouched, mirroring Flight 2's staleness
  test that asserts the store is untouched on a 409).
- AC5: a test that captures `base_value`, writes the *other* field via a whole-row
  path, then runs the CAS and asserts the other field's change survived.
- AC7: `_row_to_model` round-trip on an `external` row; the re-propose-updates-
  provenance test on `upsert_pending_revision`.
- AC8: gate tests — an `ext_` bearer gets 403 on each listed `/api/…` route (extend
  the Leg-1 confinement test); a projection test asserts no approval-mode key.
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh <files> -x --timeout 30` while
  iterating; `make test-unit` once at leg-end.

## Implementation Guidance

1. **Model** (`models.py:~708`): `source: Literal["self", "restore", "external"]`;
   add `source_principal: str | None = None` (document: the external credential
   identifier for `external` rows, NULL otherwise — safe to store/log by Mission 20's
   id/secret split; never the secret).
2. **Migration v37** (`schema.py`, after the v36 block): guard on
   `PRAGMA table_info(agent_revisions)` — if `source_principal` already present, just
   stamp the version (rewind-idempotent). Else run the rebuild ceremony (v23 pattern):
   `PRAGMA foreign_keys=OFF`; `CREATE TABLE agent_revisions_new (...)` with the
   widened `source CHECK`, the new `source_principal TEXT`, `restored_from ...
   REFERENCES agent_revisions_new(id) ON DELETE SET NULL`, and the `agent_name ...
   REFERENCES agents(name) ON DELETE CASCADE`; `INSERT INTO agent_revisions_new
   (<10 named cols>) SELECT <the same 10 named cols> FROM agent_revisions` — name the
   columns explicitly on BOTH sides (mirror the v23 precedent, `schema.py:~1082`) and
   let `source_principal` default to NULL, not a trailing positional `NULL` reliant on
   physical column order; `DROP TABLE agent_revisions`;
   `ALTER TABLE agent_revisions_new RENAME TO agent_revisions` (self-FK rewrites under
   modern `legacy_alter_table` OFF); recreate `idx_agent_revisions_agent_status`;
   `PRAGMA foreign_keys=ON`; `INSERT OR IGNORE INTO schema_version` LAST; commit.
   Bump `CURRENT_VERSION = 37`.
3. **Repository** (`repositories.py`): `append` gains `source_principal: str | None =
   None` (add to the INSERT column list + params). `upsert_pending_revision` gains
   `source: str = "self"` and `source_principal: str | None = None`; thread to the
   insert branch AND set them in the in-place UPDATE branch (a re-propose by a
   different principal must refresh who proposed). `_row_to_model` maps
   `source_principal=row["source_principal"]`.
4. **CAS** (`repositories.py`, mirror `set_self_revision_requires_approval`):
   `compare_and_set_field(self, name, field, base_value, new_value) -> bool`. Assert
   `field` ∈ `{"description", "system_prompt"}` (defensive whitelist — the column
   name is interpolated) then `UPDATE agents SET {field}=?, updated_at=? WHERE name=?
   AND {field}=?` with `(new_value, now_iso(), name, base_value)`; `commit`; return
   `cur.rowcount == 1`.
5. **`_apply_revision`** (`surface.py`): add params `source: str = "self",
   source_principal: str | None = None`. Approval branch: pass them to
   `upsert_pending_revision`. Persist branch: replace `model_copy` + whole-row `save`
   with `applied = await agent_store.compare_and_set_field(agent_name, field,
   base_value, text)`; if not `applied`, re-read current (`getattr(await
   agent_store.load(agent_name), field)`) and return the stale result — include a
   short human `message` alongside the pinned keys, matching the family of the other
   two branches, to further discourage a retry loop; if applied,
   `append(..., source=source, source_principal=source_principal, status="applied",
   ...)` (saved-before-logged preserved — append only after CAS confirms), then the
   `next_turn` `pending.record`, then the applied result. (Optional, per review: an
   `exists()` pre-check in the CAS would disambiguate a concurrent-delete from a
   genuine drift — harmless to omit at single-writer scale since `_apply_revision`
   already `load`ed the agent.)
6. **Provenance resolver** (`surface.py`): `_calling_principal(ctx) -> tuple[str, str,
   str | None]` returning `(agent_name, source, source_principal)` where
   `source = "external" if caller.source == EXTERNAL_SOURCE_NAME else "self"` and
   `source_principal = caller.identifier if source == "external" else None`. Factor the
   shared caller/agent resolution into one helper `_resolve_caller_and_agent(ctx) ->
   (caller, agent_name)` that runs the DD9 refusal tail exactly once; both
   `_calling_agent` (returns just `agent_name`, unchanged for the two read tools) and
   `_calling_principal` derive from it — no duplicated DD9 tail. The two write tools
   call `_calling_principal` and forward `source`/`source_principal` into
   `_apply_revision`.
7. **Governance tests** (DD6): assert the `ext_` bearer 403s on the operator routes
   and the projection omission (AC8). No production code needed here beyond Leg 1's
   confinement — this AC *pins an existing property* so a future change can't erode it.

## Edge Cases

- **Re-propose by a different principal under approval mode** → the deduped pending
  row's `source`/`source_principal` update to the latest proposer (guidance #3).
- **Stale on `next_session` vs `next_turn`** → the stale result is returned before any
  `pending.record`, so a stale write never leaves an in-memory deferral either.
- **`field` interpolation** → guarded by the Literal at the tool boundary AND the
  whitelist assert in the CAS (defense in depth; never interpolate an unvalidated
  field).
- **Rewind re-run of the migration** → the `source_principal`-presence guard makes the
  v37 block a no-op when already applied (mirrors the ADD COLUMN guards).
- **An `external` row read by any pre-existing code path** → the widened model Literal
  is what prevents a `ValidationError`→500; AC7 pins the round-trip.

## Files Affected

- `the_one/db/schema.py` — v37 rebuild; `CURRENT_VERSION = 37`.
- `the_one/db/models.py` — `AgentRevision.source` widened; `source_principal` field.
- `the_one/db/repositories.py` — `append`/`upsert_pending_revision`/`_row_to_model`
  provenance; `compare_and_set_field`.
- `the_one/self_configuration/surface.py` — `_apply_revision` params + CAS + stale
  result; `_calling_principal`; the two write tools.
- `tests/…` — migration (v37 + chain + rewind), `_apply_revision` provenance/approval/
  stale, CAS clobber, `_row_to_model` round-trip, governance 403s. **Update in place
  (AC9):** `tests/test_db_migration.py::TestSchemaV34::
  test_v34_fresh_db_has_agent_revisions_table` (expected column set gains
  `source_principal`) and `tests/test_self_configuration_write.py::
  test_save_failure_leaves_no_orphan_log_row` (retarget monkeypatch from `save` to
  `compare_and_set_field`).
- Docs: `SECURITY-MODEL.md` / `agents.md` provenance + external-write note (may fold
  into the flight-end doc pass).

---

## Post-Completion Checklist

- [x] All acceptance criteria verified
- [x] Tests passing (`make test-unit`) — 4507 passed, 10 skipped, 0 failed
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed` (flight-end review & commit still pending)
- [x] Check off this leg in flight.md
- [x] (Not final leg — no flight-status change here)
- [x] Do NOT commit (deferred to flight-end review)

## Citation Audit
*(verified against `flight/03-external-client-access` post-Leg-1, 2026-08-27)*

- `surface.py:_apply_revision` — approval branch `upsert_pending_revision` (no source
  param today), persist branch whole-row `save` then `append(source="self")`,
  `next_turn` `pending.record`; the two `@mcp.tool()` write tools call
  `_calling_agent(ctx)`. ✓
- `repositories.py` `AgentRevisionRepository.append` (source param present, no
  source_principal), `upsert_pending_revision` (hard-codes `source="self"` in the
  insert branch; UPDATE branch sets only proposed/base/created_at), `_row_to_model`,
  `_transition`/`mark_applied` (status+resolved_at only — source preserved),
  `supersede_pending`. ✓
- `repositories.py` `SQLiteAgentStore.save` (whole-row upsert) and
  `set_self_revision_requires_approval` (targeted UPDATE precedent for the CAS). ✓
- `models.py:~708` `AgentRevision.source: Literal["self","restore"]`. ✓
- `schema.py` `if version < 23:` rebuild ceremony (PRAGMA OFF/ON envelope,
  executescript, version stamp last); `CURRENT_VERSION = 36` post-Leg-1. ✓
- Operator control-plane routes for AC8: `PUT …/approval-mode`, `POST …/revisions/
  {id}/approve|dismiss`, `POST …/revisions/{id}/restore` (`api.py`), all under
  `/api/…` (off the confined `/mcp/self-configuration` mount). ✓
