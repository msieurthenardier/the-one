# Leg: approval-mode-and-queue

**Status**: completed
**Flight**: [Operator Oversight](../flight.md)

## Objective

Add per-agent approval mode: an operator setting that holds a self-revision in
the `agent_revisions` queue as `pending` instead of applying it, with a truthful
non-looping result to the agent, a per-agent pending count the operator sees, and
approve/dismiss actions — where approve applies the revision only after a
fail-closed staleness check against the value the agent saw when it proposed.

## Context

- **DD2** — approval mode is `AgentConfig.self_revision_requires_approval: bool =
  False`, a new `agents` column (v35), set by an immediate-post operator control,
  unwritable by the agent (no write tool addresses it; the projection omits it).
  **The HIGH fix:** `update_agent` must preserve the column when a Studio Save
  omits it, or the Save silently resets approval mode to `False`.
- **DD3** — under approval mode `_apply_revision` branches: it enqueues a
  `pending` row (dedup one per agent+field) and returns
  `applied_to_store: false, effective: "pending_operator_approval"` **without**
  `save` or `pending.record`. Post-approval propagation is next-session only; the
  proposing turn's `apply` is moot and not replayed.
- **DD4** — approve is fail-closed: the pending row carries `base_value` (the
  field's value at capture); on approve the endpoint compares it to the current
  stored value. Unchanged → apply (load → `model_copy(one field)` → save);
  drifted → 409 returning current + proposed so the operator sees what
  re-approving would overwrite; an explicit override re-captures `base_value` to
  the current value and applies.
- **DD8** — disabling the surface marks the agent's outstanding `pending` rows
  `superseded`, so a revision proposed under a since-revoked surface can't be
  approved afterward. Agent deletion is already handled by Leg 1's FK cascade.
- **DD6** — the queue, count badge, and approve/dismiss reuse the connector
  peer-approval shape (`_transition` idempotent-on-self + raise-on-illegal →
  409; cross-ID 404 guard; field-projected list), ported per-agent into the
  Studio self-configuration tab.
- The `agent_revisions` table already carries the `pending`/`dismissed`/
  `superseded` states and the `(agent_name, status)` index from Leg 1's v34 — so
  the queue needs **new repository methods only, no revision-table migration**.
  The single migration this leg owns is the v35 `agents` column.

## Inputs

Post-Leg-1 state (all verified during Leg 2 recon):

- `AgentRevisionRepository` (`the_one/db/repositories.py:893`) with
  `append`/`get`/`list_for_agent`/`_row_to_model` (conn-only, no encryptor).
- `AgentRevision` model (`the_one/db/models.py:685`) already typing the four
  statuses and two sources.
- `_apply_revision` (`the_one/self_configuration/surface.py:177`) — loads config,
  captures `base_value`, saves, appends an `applied`/`self` row, records
  `next_turn` deferral; returns the direct result shape. The approval-mode read
  is free here (config already loaded).
- Connector template: `PendingApprovalRepository._transition`
  (`repositories.py:849`, idempotent-on-self, `ValueError`→409),
  `count_pending` (`:820`), `list_all_pending` (`:832`); endpoints
  `approve_peer_approval` (`api.py:3262`, cross-ID 404 at `:3301`, 409 at
  `:3304`), `dismiss_peer_approval` (`:3355`), `get_pending_approval_count`
  (`:3387`, returns `{"count": n}`), `list_pending_approvals` (`:3400`,
  `_frontend_fields` projection at `:3414`).
- Self-config endpoints `GET/POST/DELETE /agents/{name}/self-configuration`
  (`api.py:928/943/961`) delegating to `self_configuration_manage`
  `status`/`enable`/`disable` (`manage.py:88/131/201`). `disable` is async, tears
  down the MCP source row, takes `agent_store`/`mcp_repo` kwargs.
- `AgentConfig` (`the_one/agent/config.py:176`); Behavior-block fields
  `max_iterations` (`:284`), `chat_history_retention_days` (`:285`);
  `connector_always_listen` (`:281`) is the per-agent-operator-setting precedent.
- `update_agent` (`api.py:737`) — preserve block for `mcp_overrides` at
  `:759-771` (`_merge_preserved_mcp_credentials`, `api.py:129`), `model_validate`
  at `:773`, `save` at `:790`.
- `SQLiteAgentStore.save` (`repositories.py:190`) — INSERT column list, VALUES
  placeholder list (`:200`), ON CONFLICT SET, and value tuple (four edit sites);
  `_row_to_config` (`:297-343`), v30 `chat_history_retention_days` read at `:342`
  (a plain read; missing-column access on `aiosqlite.Row` raises `IndexError`,
  per the note at `:302-305`).
- v30 boolean/int ADD COLUMN migration template (`schema.py:1857-1861`); latest
  version is **v34** (Leg 1), so this leg is **v35**.
- Studio tab `self-configuration-tab.js` `renderSelfConfigurationTab(panel,
  agent, callbacks)` (`:30`) — immediate-post enable toggle (does not join
  `collectFormData()`, `:21-24`); host wiring `agent-editor.js:199-202`;
  callbacks in `areas/studio.js` (one directory up — there is no
  `areas/studio/studio.js`): `fetchSelfConfigurationStatus:1021`,
  `enableSelfConfiguration:1048`, `_refreshAgentAfterSelfConfigurationChange:
  1029`.
- `projection.py:64-75` — explicit allowlist dict (the new field stays omitted).
- `now_iso()` (`the_one/db/models.py:14`). Connector browser tests
  `tests/browser/test_flow_chat_pending_approval.py`,
  `test_flow_chat_pending_badge.py`.

## Outputs

- v35 migration adding `agents.self_revision_requires_approval INTEGER NOT NULL
  DEFAULT 0`.
- `AgentConfig.self_revision_requires_approval: bool = False`, threaded through
  `SQLiteAgentStore.save` (4 edit sites) and `_row_to_config` (plain read).
- `update_agent` preserves the field when the payload omits it.
- New `AgentRevisionRepository` methods: `count_pending(agent_name)`,
  `upsert_pending_revision(...)` (dedup one pending per agent+field),
  `mark_applied(id)` / `mark_dismissed(id)` / `_transition(...)` (idempotent-on-
  self, raise-on-illegal), `update_base_value(id, base_value)` (override
  re-capture), `supersede_pending(agent_name)` (bulk, DD8).
- `_apply_revision` approval-mode branch (enqueue vs persist).
- New endpoints under `/agents/{name}/self-configuration`:
  `PUT /approval-mode`, `GET /revisions`, `GET /revisions/pending-count`,
  `POST /revisions/{id}/approve` (with `override`), `POST /revisions/{id}/dismiss`.
- `manage.disable` marks outstanding pending rows superseded (DD8).
- `manage.status` returns `requires_approval` so the tab renders the toggle.
- Studio self-configuration tab: the approval-mode immediate-post toggle, the
  pending-revision queue (approve/dismiss cards with the staleness re-confirm),
  and a per-agent pending count.
- Unit + browser tests; docs updated.

## Acceptance Criteria

- [x] AC1 — A v35 migration adds `self_revision_requires_approval INTEGER NOT
      NULL DEFAULT 0` to `agents` (v30-style guarded `ALTER TABLE`, parameterized
      version stamp last, idempotent re-run). Existing agents backfill to `0`.
- [x] AC2 — `AgentConfig.self_revision_requires_approval: bool = False` round-
      trips through `save`/`load` (all four save edit sites — column list, VALUES
      placeholders, ON CONFLICT SET, value tuple — + a plain `_row_to_config`
      read mirroring `chat_history_retention_days`; the v35 `NOT NULL DEFAULT 0`
      backfill means no absent/NULL case). No `@field_validator` needed.
- [x] AC3 — **DD2 HIGH:** a `PUT /api/agents/{name}` whose body omits
      `self_revision_requires_approval` leaves the stored value unchanged (the
      preserve mirrors `mcp_overrides`). A test flips approval mode on, then does
      an unrelated agent Save, and asserts approval mode is still on.
- [x] AC4 — The agent cannot read or write the setting: `get_my_configuration`'s
      projection does not include it (assert absent from the tool result), and no
      write tool addresses it (unchanged from Flight 1 — the catalog shape).
- [x] AC5 — With approval mode ON, a write tool call enqueues a `pending`/`self`
      row (`base_value` = current stored value, `proposed_value` = the text,
      `resolved_at` NULL) and **does not** call `save` or `pending.record`; the
      stored config and the live agent are unchanged. The tool returns
      `{applied_to_store: false, effective: "pending_operator_approval", field,
      message: <truthful, non-retry-inducing>}`.
- [x] AC6 — Dedup: a second write to the **same field** while a pending row
      exists updates that row in place (`proposed_value`/`base_value`/`created_at`
      refreshed) rather than inserting a second — one pending row per
      `(agent_name, field)`. Different fields keep separate pending rows.
- [x] AC7 — With approval mode OFF, behavior is exactly Leg 1's (persist + log an
      `applied` row) — no regression.
- [x] AC8 — `GET /agents/{name}/self-configuration/revisions/pending-count`
      returns `{"count": n}` scoped to that agent. `GET .../revisions` returns
      that agent's revisions newest-first (full non-secret rows — description/
      system_prompt are plaintext, so `base_value`/`proposed_value` are safe to
      return; the operator needs them to decide). This is the intended reading of
      DD6's "field-projected — never `base_value` of unrelated concern": that
      phrase means never *another agent's* data, enforced by the name-scoped
      query + cross-ID 404 guard — not that the deciding operator is denied the
      before/after of their own agent's proposal (which criterion 6 requires).
- [x] AC9 — `POST .../revisions/{id}/dismiss` transitions a `pending` row to
      `dismissed` (idempotent on an already-dismissed row; 409 on
      applied/superseded). A revision id whose `agent_name` ≠ path `{name}` is a
      404 (cross-ID guard). Unknown id → 404.
- [x] AC10 — `POST .../revisions/{id}/approve` on a pending row whose
      `base_value` **equals** the current stored value applies the revision
      (load → `model_copy({field: proposed})` → save), transitions the row to
      `applied` (`resolved_at` set), and the change reaches new conversations
      next-session (persist path). Idempotent on an already-`applied` row; 409 on
      dismissed/superseded; 404 cross-ID/unknown.
- [x] AC11 — **DD4 staleness:** approve on a pending row whose `base_value` ≠ the
      current stored value returns **409** with a body carrying both the current
      value and the proposed value (and the stale base), and does **not** modify
      the store or the row. Re-issuing approve with `override` (e.g.
      `?override=true`) re-captures `base_value` to the current value, applies the
      proposed value, and transitions to `applied`.
- [x] AC12 — **DD8:** `DELETE /agents/{name}/self-configuration` (disable) marks
      every outstanding `pending` row for that agent `superseded` (`resolved_at`
      set), so a subsequent approve of such a row is a 409. Placed so it runs even
      when the surface row is already gone (above the early-return).
- [x] AC13 — Studio self-configuration tab: an immediate-post approval-mode
      toggle (like the enable toggle — not a `collectFormData()` field) that
      `PUT`s `/approval-mode` and reflects state from `status()`; a pending-queue
      list rendering approve/dismiss cards, each showing base→proposed; clean
      approve is one-click and dismiss is one-click, both followed by a re-render
      via `_refreshAgentAfterSelfConfigurationChange` (which re-fetches, so the
      resolved row leaves the pending list — no separate in-place badge swap); a
      staleness 409 renders current-vs-proposed with an explicit override/confirm
      affordance; a per-agent pending count is shown.
- [x] AC14 — Browser tests (mirroring `test_flow_chat_pending_*.py`) cover: the
      count reflects seeded pending rows; approve and dismiss in-place swaps; the
      staleness 409 renders both values; the approval-mode toggle persists.
- [x] AC15 — Accessibility: the toggle and queue cards meet the tab's existing
      bar (labelled controls, `role="status"`/`aria-live` for the count and
      status lines, keyboard-operable buttons, visible focus) — reviewed by the
      Accessibility Reviewer.
- [x] AC16 — `make test-unit` green (no regressions); relevant browser lane green;
      docs updated (`SECURITY-MODEL.md` gains approval mode and the residual-risk
      note that a prompt-injected agent's writes are now gated when approval mode
      is on; `CLAUDE.md`/`agents.md` note the new endpoints and setting).

## Verification Steps

- AC1/AC2 — migration test (fresh + v34→v35 upgrade, backfill=0, idempotent);
  `save`/`load` round-trip of the field true and false.
- AC3 — endpoint test: enable approval mode via `PUT /approval-mode`; issue a
  `PUT /api/agents/{name}` with a body that omits the field; `load` and assert
  still `True`.
- AC4 — call `get_my_configuration` and assert the key is absent.
- AC5/AC6/AC7 — over `_apply_revision` with the flag on/off: assert the enqueue,
  no-save (patch `save` to fail-on-call under approval mode and assert not
  called; or assert stored config unchanged), the result shape, the dedup
  (two writes → one pending row, values refreshed), and the off-path regression.
- AC8/AC9/AC10/AC11 — endpoint tests: seed pending rows via
  `upsert_pending_revision`; count; dismiss (+ idempotent/409/404); approve clean
  (applies + transitions); approve stale (409 + both values, store untouched);
  approve override (re-capture + apply). Assert propagation is next-session by
  checking the stored row changed and no live-turn mutation occurred.
- AC12 — enqueue a pending row, call disable, assert the row is `superseded` and
  a follow-up approve is 409.
- AC13/AC14/AC15 — browser lane against a dev instance (non-8484, scratch data
  dir): seed rows, drive the tab, assert the rendered-state swaps and the toggle
  persistence; Accessibility Reviewer pass on the new UI.
- AC16 — `make test-unit` + browser lane + docs.
- Test command: `PYTHON=.venv/bin/python bash scripts/run-tests.sh <files> -x
  --timeout 30` iterating, then `make test-unit` once at leg end.

## Implementation Guidance

1. **v35 migration** (`schema.py`, new `if version < 35:` after v34): guarded
   `ALTER TABLE agents ADD COLUMN self_revision_requires_approval INTEGER NOT
   NULL DEFAULT 0` (v30 template `:1857-1861`), parameterized stamp last.
2. **`AgentConfig`** (`config.py`): add the bool field in the Behavior block.
   **Thread it through `SQLiteAgentStore.save` at all FOUR textual edit sites**
   (`repositories.py:194-243`): the INSERT column list, the `VALUES (?, ?, …)`
   placeholder list (add the 19th `?` — this is a distinct edit, not part of the
   column list; omitting it fails at runtime with "19 columns but 18 values"),
   the ON CONFLICT SET clause, and the value tuple. And read it in
   **`_row_to_config`** with a **plain** `bool(row["self_revision_requires_
   approval"])`, mirroring the `chat_history_retention_days` read at `:342` —
   NOT a "column-present/NULL-safe" form: v35 adds the column `NOT NULL DEFAULT
   0` and backfills, so no absent/NULL row survives at load, and an inline
   missing-column access on `aiosqlite.Row` raises `IndexError` anyway (see the
   note at `repositories.py:302-305`).
3. **`update_agent` preserve** (`api.py`, before `model_validate` at `:773`):
   `if "self_revision_requires_approval" not in data: data["self_revision_
   requires_approval"] = existing.self_revision_requires_approval`. This is the
   DD2 HIGH fix — model after the `mcp_overrides` preserve just above it.
4. **Repository methods** on `AgentRevisionRepository` (`repositories.py:893`):
   - `count_pending(agent_name)` → `SELECT COUNT(*) ... WHERE agent_name=? AND
     status='pending'`.
   - `upsert_pending_revision(*, agent_name, field, proposed_value, base_value)`
     → SELECT an existing `pending` row for `(agent_name, field)`; UPDATE
     `proposed_value`/`base_value`/`created_at` in place if found, else `append`
     with `status='pending', source='self', resolved_at=None`. Return
     `(revision, created: bool)`, mirroring `upsert_pending`.
   - `_transition(revision_id, target: Literal['applied','dismissed'])` — copy
     `PendingApprovalRepository._transition` (`:849`): idempotent when already at
     target, `ValueError` on any non-`pending` non-target state, single UPDATE
     stamping `status`+`resolved_at=now_iso()`. `mark_applied`/`mark_dismissed`
     delegate.
   - `update_base_value(revision_id, base_value)` → UPDATE base_value (override
     re-capture).
   - `supersede_pending(agent_name)` → `UPDATE agent_revisions SET
     status='superseded', resolved_at=? WHERE agent_name=? AND status='pending'`.
5. **`_apply_revision` branch** (`surface.py:177`): after loading config and
   capturing `base_value`, read `config.self_revision_requires_approval`. If
   **True**: `await revisions.upsert_pending_revision(agent_name=..., field=...,
   proposed_value=text, base_value=base_value)`; return `{"applied_to_store":
   False, "effective": "pending_operator_approval", "field": field, "length":
   len(text), "message": <truthful>}`; do **not** save or `pending.record`. If
   **False**: existing Leg 1 path. Keep `_validate_write_input` and
   `_calling_agent` unchanged.
6. **Endpoints** (`api.py`, beside the self-config endpoints ~`:928-975`), each
   loading the agent (404) and, for revision routes, enforcing the cross-ID guard
   (`revision.agent_name != name → 404`):
   - `PUT /agents/{name}/self-configuration/approval-mode` body
     `{"requires_approval": bool}` → set via a **targeted** `UPDATE agents SET
     self_revision_requires_approval=? WHERE name=?` (a small `SQLiteAgentStore`
     method), **not** a full-row `save` — the immediate-post toggle touches only
     this operator-owned scalar, so a targeted update dodges the whole-row
     last-writer-wins window entirely (safe here, unlike the DD4 approve path
     which must re-load to avoid clobbering the revision target). Return
     `{"requires_approval": bool}`. The toggle is settable regardless of whether
     the surface is currently enabled (the field is independent of the surface
     row; it only *bites* once the agent can propose) — pre-setting is harmless
     and avoids coupling the control to enable state.
   - `GET /agents/{name}/self-configuration/revisions` →
     `revisions.list_for_agent(name)` as dicts (full rows; nothing secret).
   - `GET /agents/{name}/self-configuration/revisions/pending-count` →
     `{"count": await revisions.count_pending(name)}`.
   - `POST /agents/{name}/self-configuration/revisions/{id}/dismiss` → cross-ID
     guard, `mark_dismissed` in `try/except ValueError → 409`.
   - `POST /agents/{name}/self-configuration/revisions/{id}/approve` (query
     `override: bool = False`) → cross-ID guard; require `status=='pending'`
     (idempotent no-op if already `applied`; 409 otherwise); load config,
     `current = getattr(config, revision.field)`; if `current != base_value and
     not override` → **409** with `{"current_value": current, "proposed_value":
     revision.proposed_value, "base_value": revision.base_value}` and no writes;
     else: if override and drift, `update_base_value(id, current)` first; then
     `save(config.model_copy(update={field: revision.proposed_value}))` and
     `mark_applied(id)`; return the updated revision.
7. **`manage.disable` DD8** (`manage.py:201`): thread an
   `AgentRevisionRepository` (new `revisions_repo` kwarg passed from the DELETE
   endpoint at `api.py:961`); call `await revisions_repo.supersede_pending(
   agent_name)` **above** the `if row is None: return False` early-return so a
   disable always clears the queue. `manage.status` (`:88`): include
   `requires_approval` from the loaded config in **every** return branch that has
   a loaded config (enabled / row-None / orphaned) so the toggle renders
   consistently regardless of surface state.
8. **Studio UI** (`self-configuration-tab.js` + `studio.js` + `agent-editor.js`):
   - Approval-mode toggle: mirror the enable toggle's immediate-post pattern
     (`renderState`/`onclick`/disable-during-request/error-line). New callbacks
     `fetchStatus` already returns `requires_approval`; add `onSetApprovalMode(
     name, bool)` → `PUT /approval-mode` → refresh. Do **not** add it to
     `collectFormData()`.
   - Pending queue: render `revisions` filtered to `status==='pending'` as
     approve/dismiss cards (borrow `pending-approval-banner.js` shape). **Each
     card shows base→proposed on the clean path too** (for a non-stale row
     `base_value == current`, so "see what would change" is satisfied on the
     one-click path, not only the 409 path). On approve/dismiss click, `POST` the
     action; **clean approve is one-click** (values already visible); a
     **409-staleness** response renders current-vs-proposed with an explicit
     override/confirm button that re-POSTs with `override=true`. On success,
     **rely on `_refreshAgentAfterSelfConfigurationChange`** to re-render (it
     re-fetches, so the resolved row leaves the pending list) — do **not** also
     attempt an in-place badge swap: the refresh rebuilds the panel DOM
     (`studio.js:1029-1046` calls `doSelect`), which would discard a local swap.
     (`renderSelfConfigurationTab` currently fetches only `status`; the queue and
     count need their own fetch added on render.)
   - Count: render `count_pending` (fetch on tab render + after each action; an
     optional light poll may be added but is not required at operator-scale).
   - Give every new control a `data-testid` following the tab's convention.
9. **Docs**: update `SECURITY-MODEL.md` (approval mode as the gate on the
   mission's central write-risk; note the residual risk is now operator-gated
   when on), and note the new endpoints/setting in `CLAUDE.md`/`agents.md`.

## Edge Cases

- **Approve after the surface was disabled** — the row is `superseded` (DD8), so
  approve is a 409. Correct.
- **Approve when approval mode was turned OFF after queuing** — the pending row
  still exists; approve still works (it operates on the row, not the current
  flag). Turning approval off does not auto-apply the backlog; the operator
  approves or dismisses each. Acceptable and truthful.
- **Dedup update refreshing `base_value`** — on a re-propose, `base_value`
  becomes the latest current value; the staleness window resets to the latest
  proposal. Intended.
- **Override on a row that is no longer stale** (the field drifted back) —
  `current == base_value`, so approve applies normally without needing override;
  a spurious `override=true` is harmless (re-capture is a no-op).
- **`next_turn` chosen under approval mode** — the `apply` arg is accepted by the
  tool signature but moot; enqueue ignores it. Applied revisions propagate
  next-session (DD3). Do not `pending.record` under approval mode.
- **Concurrent approve + Studio edit** — the DD4 base compare closes the silent
  case; a genuine race between two approves of different fields is independent
  (separate rows, separate saves). Two approves of the *same* field can't
  coexist (dedup ⇒ one pending row).
- **Override branch not transactional** — `update_base_value` → `save` →
  `mark_applied` are three separate commits; a `save` failure after
  `update_base_value` leaves a pending row whose `base_value` was rewritten to
  the current value. Operator-scale-acceptable (the row is still pending and
  re-approvable), but note it in a code comment; do not reorder so `mark_applied`
  precedes `save`.

## Files Affected

- `the_one/db/schema.py` — v35 migration.
- `the_one/agent/config.py` — new field.
- `the_one/db/repositories.py` — `SQLiteAgentStore` save/load wiring; new
  `AgentRevisionRepository` methods.
- `the_one/self_configuration/surface.py` — approval-mode branch in
  `_apply_revision`.
- `the_one/self_configuration/manage.py` — `disable` supersede; `status`
  `requires_approval`.
- `the_one/interfaces/web/api.py` — `update_agent` preserve; five new endpoints;
  thread `revisions_repo` into the disable call.
- `the_one/interfaces/web/static/js/areas/studio/self-configuration-tab.js`,
  `the_one/interfaces/web/static/js/areas/studio.js`,
  `the_one/interfaces/web/static/js/areas/studio/agent-editor.js` — toggle,
  queue, count.
- `tests/` — unit (repo, branch, endpoints, staleness, preserve, disable) +
  browser (queue, badge, toggle).
- Docs: `SECURITY-MODEL.md`, `CLAUDE.md`/`agents.md`.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (`make test-unit` green; browser lane green)
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] (Not the final leg — do not land the flight or commit; review + single
      commit are deferred to flight end per /agentic-workflow.)

---

## Citation Audit

Verified against the working tree (Leg 1 landed-uncommitted) at Leg 2 design
review:

- Latest schema **v34** (`schema.py:1962`, `agent_revisions`) → v35 unclaimed;
  v30 ADD-COLUMN template `schema.py:1857-1861`. ✓
- `SQLiteAgentStore.save` four edit sites: column list `repositories.py:194-201`,
  `VALUES (?)` placeholders `:200`, ON CONFLICT SET, value tuple `:242`;
  `_row_to_config` `:297-343`, `chat_history_retention_days` plain read `:342`,
  missing-column `IndexError` note `:302-305`. ✓
- `update_agent` `api.py:737`; `mcp_overrides` preserve `:761-769`;
  `model_validate` `:773`; `save` `:790`. `create_agent` needs no preserve
  (new agents default False). ✓
- `_apply_revision` `surface.py:177`, `base_value` capture `:184`. ✓
- Connector: `_transition` `repositories.py:849`, `count_pending` `:820`,
  `list_all_pending` `:832`; `approve` `api.py:3262` (cross-ID 404 `:3301`,
  409 `:3304`), `dismiss` `:3355`, count `:3387`, list `:3400`
  (`_frontend_fields` `:3414`). ✓
- Self-config endpoints `api.py:928/943/961`; `manage.disable` `:201`
  (`row is None → return False` early-return), `status` `:88`, `enable` `:131`.
  DELETE endpoint `:961` can build `AgentRevisionRepository(await
  get_connection())`. ✓
- `AgentConfig` `config.py:176` (fields `:281/284/285`); `projection.py:64-75`
  explicit allowlist (new field stays omitted → AC4). ✓
- Studio callbacks live in `areas/studio.js` (not `areas/studio/studio.js`):
  `fetchSelfConfigurationStatus:1021`, `enableSelfConfiguration:1048`,
  `_refreshAgentAfterSelfConfigurationChange:1029-1046` (full re-render via
  `doSelect`); tab `self-configuration-tab.js:30`; host `agent-editor.js:199-202`.
  ✓
