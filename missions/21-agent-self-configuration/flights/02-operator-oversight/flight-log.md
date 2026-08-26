# Flight Log: Operator Oversight

**Flight**: [Operator Oversight](flight.md)

## Summary

Flight in planning. Spec authored with seven design decisions (DD1–DD7) and
three legs plus an optional HAT leg. Not yet executed.

---

## Leg Progress

### 2026-08-25 — Leg 1 (revision-log-foundation) — landed

Built the `agent_revisions` revision-log foundation (AC1–AC9, all checked off):

- **Migration v34** (`the_one/db/schema.py`): new `if version < 34:` block
  after v33, following the v31 `app_metadata` new-table template. Creates
  `agent_revisions` with the full AC1 column/CHECK set (all four `status`
  values, both `source` values), the `idx_agent_revisions_agent_status`
  `(agent_name, status)` index, then the parameterized `INSERT OR IGNORE …
  VALUES (?)` `(34,)` stamp last (partial-apply safe). `CURRENT_VERSION`
  bumped 33 → 34.
- **Model** (`the_one/db/models.py`): `AgentRevision` mirroring the columns
  (`restored_from`/`resolved_at` optional), styled after `PendingApproval`.
- **Repository** (`the_one/db/repositories.py`): `AgentRevisionRepository(conn)`
  — no encryptor, mirroring `PendingApprovalRepository`. Log-facing methods
  only: `append` (mints `id` as `uuid.uuid4().hex`, commits, returns the row),
  `get` (`KeyError` on miss), `list_for_agent` (`ORDER BY created_at DESC,
  id DESC`), `_row_to_model`. Queue transitions / `count_pending` deliberately
  NOT added (Leg 2).
- **Wired the direct path** (`the_one/self_configuration/surface.py`
  `_apply_revision`): captures `base_value = getattr(config, field)` before
  `model_copy`, and after a successful `save` appends one `applied`/`self` row
  on the same `conn`, with a single `now_iso()` value for both `created_at`
  and `resolved_at`. Tool return shape, `pending.record`, and `next_turn`
  behavior unchanged. `pending.py` untouched.

Tests (host-native, repo venv):

- `tests/test_db_migration.py::TestSchemaV34` — 5 tests (fresh-DB shape,
  field/status/source CHECK enforcement, index columns, idempotent re-run,
  v33→v34 upgrade path).
- `tests/test_db_repositories.py::TestAgentRevisionRepository` — 6 tests
  (append/get round-trip, `KeyError` on miss, newest-first ordering, same-
  timestamp `id DESC` tiebreak, per-agent scoping, FK cascade against the
  `foreign_keys=ON` `conn` fixture with an in-test `PRAGMA foreign_keys == 1`
  assertion — AC8).
- `tests/test_self_configuration_write.py::TestRevisionLogWrite` — 5 tests
  (one `applied` row per description/system-prompt revision with correct
  before/after images, two fields independent, empty-`""` base default,
  save-failure leaves no orphan log row — AC7).

Full `make test-unit` green (4396 passed pre-change; one pre-existing test
regressed only on the version-head bump and was corrected — see Deviations).

**Test outcome**: 16 new tests, all passing; full unit lane green, no
regressions.

---

## Decisions

_Runtime decisions will be recorded here during execution._

---

## Deviations

### 2026-08-25 — Leg 1: stale schema-head literal in a v33 test

`tests/test_db_migration.py::TestSchemaV33::test_v33_fresh_db_has_secrets_column_and_plan_type`
asserted the schema head with a chained literal `row[0] == CURRENT_VERSION == 33`.
Bumping `CURRENT_VERSION` to 34 (the intended v34 migration) made that literal
comparison fail. Relaxed it to `row[0] == CURRENT_VERSION` (the `== 33` was a
fossil from when 33 was the head; the test's own v33 column/CHECK assertions are
unchanged). This is the "no pre-existing tests regress" cleanup that necessarily
accompanies a schema-version bump, not a scope expansion.

---

## Anomalies

_None yet._

---

## Session Notes

### 2026-08-25 — Flight planned

- Flight 1 (Self-Configuration Surface) landed and merged as PR #171; `main`
  synced to `3ab11d0` before planning against merged code.
- Codebase reconnaissance mapped six surfaces: the connector peer-approval flow
  (the reusable pending/approve/dismiss/badge template, in the Chat area),
  Flight 1's always-persist write path (`_apply_revision`, LD2), agent config
  storage (no history table exists — greenfield), the Studio self-configuration
  tab (vanilla-JS immediate-post enable toggle), the two-field write allowlist
  (the tool catalog's shape, not an enumerated list), and the total absence of
  optimistic concurrency (full-row last-writer-wins upsert).
- Operator resolved four design forks: **staleness** fail-closed (capture
  `base_value`, 409 + re-confirm on drift) → DD4; **restore** operator-direct and
  logged with provenance → DD5; **loop control** visibility-only, no rate limit →
  DD7; **optional HAT leg** included.
- Key hazard recorded for execution: the existing `self_configuration/pending.py`
  is an in-memory *live-turn deferral* registry, not an approval queue, yet lives
  in the exact subpackage where the operator-approval queue belongs. The queue
  module and repository must take distinct names to avoid the collision.

### 2026-08-25 — Architect design review (approve with changes)

- Architect verified every spec citation against `main`. Verdict: **approve with
  changes**. FK/cascade, plaintext-column, by-construction, and connector-reuse
  claims all confirmed; a few line-number drifts corrected in-spec.
- **HIGH incorporated → DD2**: a later Studio Save would silently reset the new
  `self_revision_requires_approval` column to `False` (the operator control is
  not a form field; `update_agent` full-row `model_validate` + `save` applies the
  default on omission). Fix folded in: Leg 2 must extend the `update_agent`
  server-side preserve to carry the setting from the stored row, with "approval
  mode survives an unrelated Studio Save" as an explicit Leg 2 AC. Same bug class
  Flight 1's DD5 closed for `mcp_overrides`.
- **MEDIUM incorporated → DD3 / Verification**: post-approval propagation is
  next-session only (no live turn at approve-time); the queued row carries no
  timing and the proposing turn's `apply` is not replayed. Verification line
  corrected from the overstated "same next_turn/next_session machinery."
- **MEDIUM incorporated → DD4**: concurrency evidence re-cited to the full-row
  upsert at `repositories.py:189` (the earlier `:1279`/`:1330` citations were in
  `ChatSessionRepository`, not the agent store); made explicit that the approve
  path re-loads current config and `model_copy`s only the target field (never a
  targeted `UPDATE … SET field=?`).
- **Gap incorporated → DD8 (new)**: surface-disable marks outstanding pending
  rows `superseded` so a revision proposed under a since-revoked surface cannot
  be approved after the fact; agent deletion is handled by the FK cascade.
- **LOW incorporated**: field literals re-cited to `surface.py:209,222`; boolean
  column migration template changed to v30's `NOT NULL DEFAULT` shape.
- **Suggestions folded into Leg 2**: highest design-review risk tier; the two
  Flight-1 carry-overs (shutdown-drain-under-load, two-agent isolation) picked up
  here since Leg 2 touches the same pool/lifecycle code; distinct queue naming
  with the `pending.py` boundary preserved; optional partial unique index for the
  dedup. No secret-leak exposure (description/system_prompt are plaintext).
- Changes are the reviewer's exact prescribed fixes (spec-text incorporation, no
  novel design), so a second full review cycle was not spent.

---

## Flight Director Notes

### 2026-08-25 — Flight execution begins (/agentic-workflow)

- Phase file `leg-execution.md` loaded and validated (Crew / Interaction
  Protocol / Prompts all present). Developer = Sonnet, Reviewer = Haiku,
  optional Accessibility Reviewer = Sonnet (spawn for the UI legs 2 and 3).
- Mission `active`, flight moved `ready` → `in-flight`. Branch
  `flight/02-operator-oversight` created off `main` (`3ab11d0`, post-#171 merge).
- Leg plan (3 autonomous + 1 optional HAT), sized by decision/risk:
  1. `revision-log-foundation` — HIGH (schema + migration).
  2. `approval-mode-and-queue` — HIGHEST (state machine, central write-risk,
     security, largest leg).
  3. `revision-restore` — MEDIUM/HIGH (touches live persist path).
  4. `uat-and-alignment` — optional HAT.
- Deferred code review + single commit to flight end (2d), per skill.

### Leg 1 (revision-log-foundation) — design

- **Risk tier: HIGH.** Rationale: creates migration v34 (`agent_revisions`
  table) — schema change; defines the status/source state values later legs
  reach; and modifies the shared `_apply_revision` write choke point. Design
  review spawned (Developer, Sonnet).
- Scope boundary set: Leg 1 builds the table (all CHECK values), the model, and
  the log-facing repo methods (append/get/list_for_agent) + wires the direct
  path to log `applied` rows. The queue transitions + count_pending are held for
  Leg 2's state machine; restore provenance for Leg 3. Keeps the leg a clean
  "the log exists and captures direct revisions" slice.

- **Leg 1 design review: approve with changes** (Developer, Sonnet). All items
  minor/precision — incorporated without a second cycle:
  - [medium] AC8 cascade test routed explicitly to a `foreign_keys=ON` fixture
    (`test_db_repositories.py:35`), away from `test_schema.py`'s `:memory:`
    fixtures that omit the pragma, with an in-test pragma assertion.
  - [low] `_apply_revision` cite corrected `:174`→`:175`; version stamp made
    parameterized `VALUES (?),(34,)` to match v30–v33; timestamp helper named
    directly (`now_iso()`, `models.py:14`); id minting fixed to
    `uuid.uuid4().hex` in the repo `append` (per `repositories.py:761`);
    `resolved_at`/`created_at` captured as one `now_iso()` value.
  - Citation Audit appended to the leg. Leg → `ready`.
- Leg 1 → **implementation** (Developer, Sonnet).

### Leg 1 → landed (legs_completed 1/3)

- Developer implemented to AC1–AC9; full unit lane **4397 passed, 10 skipped**,
  16 new tests, ruff clean. Leg status `landed`; state consistent (flight-log
  entry present, changes uncommitted per deferred-commit model).
- Disclosed in-scope deviation: `TestSchemaV33`'s chained `== CURRENT_VERSION ==
  33` literal relaxed to `== CURRENT_VERSION` for the v34 head bump — the
  expected "invert a test the new schema head breaks" cleanup, not a regression.
- Proceeding to Leg 2 design against the as-built repo/model shapes.

### Leg 2 (approval-mode-and-queue) — design

- **Risk tier: HIGHEST.** Rationale: owns migration v35 (agents column, wired
  through save/load); opens the mission's central write-risk surface (the
  approval gate on self-revision); security-sensitive (DD2 preserve-on-PUT, else
  a Studio Save silently disables the gate); and is the largest leg (backend
  state machine + 5 endpoints + Studio UI). Design review spawned (Developer,
  Sonnet).
- Scope: v35 column + AgentConfig field + save/load wiring + update_agent
  preserve (DD2); AgentRevisionRepository queue methods (count/upsert-dedup/
  transitions/supersede); the _apply_revision approval branch (DD3); the five
  per-agent endpoints incl. fail-closed staleness approve (DD4); disable-
  supersede (DD8); Studio toggle + queue + count (DD6). AC16 folds the two
  Flight-1 verification-gap carry-overs, guarded to split to a squawk if they
  balloon. Accessibility Reviewer will run at code-review time (UI leg).

- **Leg 2 design review: approve with changes** (Developer, Sonnet). Nearly all
  citations verified accurate; incorporated without a second cycle:
  - [medium] save wiring is **four** edit sites, not three — the `VALUES (?)`
    placeholder list is a distinct edit (19th `?`); named explicitly.
  - [medium] `_row_to_config` read is a **plain** `bool(row[...])` mirroring
    `chat_history_retention_days` (v35 NOT NULL DEFAULT backfills; missing-column
    access on aiosqlite.Row raises IndexError) — dropped the "NULL-safe" framing.
  - [low] Studio callbacks live in `areas/studio.js`, not `areas/studio/studio.js`
    — path corrected in Inputs/Files/guidance.
  - [low] AC8/DD6 reconciled (DD6's "never base_value" = never another agent's).
  - [low] `_refreshAfterSelfConfigurationChange` full-re-renders (doSelect), so
    "in-place badge swap" was dropped in favor of relying on the re-render;
    queue+count get their own fetch on render; clean approve is one-click.
  - Adopted: targeted `UPDATE ... SET self_revision_requires_approval` for the
    toggle endpoint (dodges the whole-row LWW window; safe for a lone operator-
    owned scalar); `status()` returns `requires_approval` in all config-loaded
    branches; override-branch non-transactional edge case documented; dismiss
    cite `:3355`.
  - **Sizing: split the two Flight-1 carry-overs out of Leg 2** (reviewer
    recommendation). They are pool/lifecycle verification-debt orthogonal to
    approval governance; folding them into the highest-risk leg invited shallow
    treatment. AC16-carryover removed; they will be logged as squawks at flight
    end. Flight spec Leg 2 note updated.
  - Citation Audit appended; Leg 2 → `ready`.
- Leg 2 → **implementation** (Developer, Sonnet). Accessibility Reviewer to run
  at flight-end code review (UI leg).

### Leg 2 — approval-mode-and-queue: implementation complete (landed, uncommitted)

Built to AC1–AC16, following the leg's Implementation Guidance steps 1–9 in
order, testing after each backend chunk.

**Backend**
- **v35 migration** (`db/schema.py`, `CURRENT_VERSION`→35): guarded ADD COLUMN
  `agents.self_revision_requires_approval INTEGER NOT NULL DEFAULT 0` on the v30
  template (PRAGMA-guarded, defensive table-missing skip, stamp last).
- **`AgentConfig.self_revision_requires_approval: bool = False`** (Behavior
  block) threaded through **all four** `SQLiteAgentStore.save` edit sites
  (column list, the 19th `VALUES (?)` placeholder, ON CONFLICT SET, value tuple)
  + a **plain** `_row_to_config` read; new targeted
  `set_self_revision_requires_approval` UPDATE for the toggle.
- **`update_agent` preserve** (DD2 HIGH): PUT that omits the field keeps the
  stored value (mirrors `mcp_overrides`).
- **`AgentRevisionRepository` queue methods**: `count_pending` (per-agent),
  `upsert_pending_revision` (dedup one per agent+field, returns `(rev, created)`),
  `_transition`/`mark_applied`/`mark_dismissed` (copied from
  `PendingApprovalRepository._transition` — idempotent-on-self, ValueError→409),
  `update_base_value` (override re-capture), `supersede_pending` (bulk, DD8).
- **`_apply_revision` branch** (DD3): approval-mode ON → enqueue pending +
  truthful `pending_operator_approval` result, no save / no `pending.record`;
  OFF → unchanged Leg-1 persist+log path.
- **Five endpoints** under `/agents/{name}/self-configuration`: `PUT
  /approval-mode` (targeted UPDATE), `GET /revisions`, `GET
  /revisions/pending-count`, `POST /revisions/{id}/approve` (`?override`, DD4
  fail-closed staleness → 409 with current+proposed+base), `POST
  /revisions/{id}/dismiss` — all with the cross-ID 404 guard and 409-on-illegal.
- **`manage.disable` DD8**: new `revisions_repo` kwarg (threaded from the DELETE
  endpoint) calls `supersede_pending` **above** the row-None early-return.
  **`manage.status`** returns `requires_approval` in every config-loaded branch.

**Studio UI** (`self-configuration-tab.js` + `studio.js` + `agent-editor.js`):
immediate-post approval-mode toggle (mirrors enable toggle, not a
`collectFormData()` field), pending-revision queue (approve/dismiss cards each
showing base→proposed on the clean path, one-click clean approve, a 409
staleness panel with an explicit override button), per-agent pending count.
Every new control carries a `data-testid`; all registered in
`docs/ui-testid-registry.md`. On any action the tab relies on
`_refreshAgentAfterSelfConfigurationChange` (doSelect re-render) rather than an
in-place swap.

**Docs**: `SECURITY-MODEL.md` (approval mode as the operator gate on the
mission's central write-risk; residual-risk bullet now notes injected writes are
gated when approval mode is on), `CLAUDE.md` + `the_one/agents.md` (new endpoints
+ setting; a full L02 subsection in agents.md).

**Tests / outcomes**
- Unit: added TestSchemaV35 (4), AgentConfig save/load round-trip + targeted
  UPDATE (4), AgentRevisionRepository queue methods (10), approval-mode branch
  (AC5/6/7, 5), all five endpoints incl. staleness/override/supersede
  (AC3/8/9/10/11/12), projection AC4 assertion. All touched-file slices green.
- Browser: `tests/browser/test_studio_self_configuration_queue.py` (5) — count +
  cards, clean approve, dismiss, staleness 409 + override, toggle persistence —
  all green; existing `test_studio_self_configuration_tab.py` (3) still green.
- `make test-unit`: green after fixing one static guard (`test_ui_guards.py`
  testid-registry sync) by registering the 17 new testids — 4436 passed on the
  first full run with that single doc-sync failure, re-run clean.

**Deviations / notes**
- One pre-existing Leg-1 migration test (`test_v34_upgrade_from_v33_creates_table`)
  assumed v34 was the head; adding v35 meant its "rewind to v33" (deleting only
  version=34) left 35 as MAX so v34 never re-ran. Updated it to rewind `>= 34`
  and assert `CURRENT_VERSION` — a consequence of the new migration, not a scope
  expansion.
- Three existing self-config API status assertions were exact-equality on
  `{"enabled": ...}`; updated to include the new `requires_approval` key.
- The two Flight-1 debrief carry-overs (shutdown-drain-under-load, two-agent
  isolation) were **not** implemented — pulled out at design review; to be logged
  as separate squawks.
- AC15 (Accessibility Reviewer): new controls meet the tab's existing bar
  (labelled controls, `role="status"`/`aria-live` on count + status lines,
  `role="alert"` on the staleness warning, native keyboard-operable `<button>`s,
  visible focus inherited). A dedicated Accessibility Reviewer pass is deferred to
  flight-end code review per the flight plan.

### Leg 2 → landed (legs_completed 2/3)

- Developer implemented to AC1–AC16; full unit lane **4437 passed, 10 skipped**;
  new browser suite `test_studio_self_configuration_queue.py` (5) green. ruff
  clean. Leg `landed`, checked off in flight.md; state consistent.
- Deviations (all principled): v34-rewind test updated for the v35 head; three
  self-config status assertions extended for the new `requires_approval` key;
  DD8 supersede threaded into BOTH surface-disable paths (the DELETE
  /self-configuration endpoint AND DELETE /mcp-sources/{id} on a surface row).
- AC15 (Accessibility) met against the tab's existing bar; a dedicated
  Accessibility Reviewer pass is deferred to flight-end code review (UI leg).
- `CURRENT_VERSION` now 35. Approve endpoint (`api.py:1082`) established the
  clean apply-path (load→model_copy(field)→save→mark_applied) that Leg 3's
  restore mirrors. `GET /revisions` (`api.py:1035`) already returns full history.
- Proceeding to Leg 3 (revision-restore) design.

### Leg 3 (revision-restore) — design

- **Risk tier: HIGH.** Rationale: writes the agent-config persist path (mission's
  central write-risk domain) and introduces a new leg decision — restore is valid
  only against an `applied` revision (a state-machine-reachability question about
  which source rows are restorable). No migration, no interface break,
  operator-only. Design review spawned (Developer, Sonnet).
- Scope: one operator-direct restore endpoint (mirrors approve's clean apply
  arm; never queues, DD5; logs source='restore' + restored_from provenance) +
  the Studio history view with per-applied-entry Restore. Reuses Leg-1 `append`
  (no new repo method, no migration).

- **Leg 3 design review (cycle 1): approve with changes** (Developer, Sonnet).
  Endpoint mirror, repo surface, DD5 never-queue, and UI wiring all verified
  correct. One [high] design gap: the pre-first-revision **original** value was
  unreachable (it lives only as the earliest row's `base_value`, never a
  `proposed_value`) — failing criterion 7's "restore ANY earlier value" and the
  primary undo-the-agent's-first-change case.
  - Resolved (reviewer's option a, not the narrow-and-sign-off option) → **LD2**:
    restore reinstates a *value node*; the endpoint takes `side=proposed|base`;
    the earliest applied row's `base` is the original; the UI exposes a Restore
    for every distinct value incl. the original. Added AC1b + verification.
  - [low] append citation `:912`→`:939` fixed. AC4 parametrized across all three
    non-applied statuses.
  - Substantive change on the central write path → running one focused cycle-2
    re-review of the value-node/side design before implementation.

- **Leg 3 design review (cycle 2, focused): approve with changes** (Developer,
  Sonnet). The value-node/`side` fix closes the cycle-1 [high] gap. Incorporated
  (cycle 2 of 2 — proceeded to implementation):
  - [medium] `side` typed `Literal["proposed","base"] = "proposed"` for FastAPI
    auto-422 (the enum analog of approve's `override: bool`), removing the silent
    bad-value→base fall-through.
  - [medium] LD2 rationale corrected: `PUT /agents/{name}` edits the field with
    NO revision row (`api.py:745/806`), so a mid-timeline `base_value` need not
    equal the prior `proposed` — an operator out-of-band value. Strengthened
    framing (every applied row's base_value is a genuine held value) + UI made
    complete: the history renders one Restore per **distinct value-node** (dedup
    base+proposed across applied rows), so the original AND out-of-band values are
    all restorable — "any earlier value" literally met.
  - [low] AC1b tightened (assert restore row base_value==D1; approval-mode-OFF
    explicit so the target is `applied`).
  - Citation Audit appended; Leg 3 → `ready`.
- Leg 3 → **implementation** (Developer, Sonnet). Last autonomous leg.

- **Leg 3 built (Developer, Opus).** Restore endpoint + Studio revision-history
  view + docs, all ACs met.
  - **Endpoint** `POST .../revisions/{id}/restore` (`api.py`), `side:
    Literal["proposed","base"]="proposed"` (FastAPI auto-422). Mirrors approve's
    clean apply arm → `store.save(model_copy(update={field: reinstated}))` → a
    NEW `source='restore'`/`status='applied'` row via `append` (restored_from,
    base_value=pre-restore current, resolved_at==created_at). LD1 non-applied
    target → 409; cross-ID/unknown → 404; never consults approval mode (DD5). No
    new repo method, no migration. Added `Literal` to the `typing` import.
  - **Studio UI**: revision-history section (full list newest-first; field /
    before→after / timestamp / source / status) below the pending queue, reusing
    the queue's single `fetchRevisions`. One Restore control per **distinct
    value-node** (dedup base+proposed across `applied` rows, walked oldest-first
    so the earliest holder of each value wins → original reachable via
    `side=base`; out-of-band operator values reachable). `restoreSelfConfiguration
    Revision` (studio.js) → `onRestore(name,id,side)` → refresh. New data-testids
    registered in `docs/ui-testid-registry.md`.
  - **Docs**: SECURITY-MODEL.md (operator-direct, no restore MCP tool, allowlist
    unchanged), CLAUDE.md + agents.md (endpoint, side param, applied-only rule).
  - **Tests**: +10 unit (`TestRestoreEndpoint` in `test_self_configuration_api.py`
    — AC1 proposed, AC1b original-via-side=base, AC2 approval-ON-still-applies,
    AC4 parametrized pending/dismissed/superseded→409 store+log untouched, AC5
    cross-ID/unknown 404, bad-side 422, AC6 field independence, AC7 restore-to-
    current still logs) + 2 browser (`test_studio_self_configuration_history.py`
    — history renders + distinct value-node controls; Restore updates field and
    appends a restore entry). `make test-unit` green (4447 passed, 10 skipped, no
    regressions); studio browser lane green (262 passed, 3 skipped).
  - **Deviations/anomalies**: none. AC3 (next-session propagation) is inherent in
    the persist path (`store.save`) — same next-session semantics the surface
    already documents; not separately re-tested. AC9 accessibility met at the
    tab's existing bar (labelled `aria-label` Restore buttons, keyboard-operable,
    history region `role="log"`/`aria-live` announced) — full pass is the
    flight-end Accessibility Reviewer's.
  - Leg 3 → **landed** (uncommitted; last autonomous leg — flight-end Reviewer +
    Accessibility Reviewer + single deferred commit run after this).

### Leg 3 → landed (legs_completed 3/3 — all autonomous legs done)

- Developer implemented to AC1–AC10; `make test-unit` **4447 passed, 10 skipped**
  (+10 unit); studio browser lane **262 passed, 3 skipped** (+2 browser). ruff
  clean. Leg `landed`, checked off; state consistent. No squawks raised.
- History UI walks applied rows oldest-first so the earliest holder wins the
  value-node dedup (original reachable via side=base). 8 new data-testids
  registered.

### Phase 2d — flight-end review + commit

- All three legs landed-uncommitted; entering deferred review. Spawning the code
  Reviewer over ALL uncommitted changes + the Accessibility Reviewer (Legs 2-3
  added Studio UI), in parallel.
- **Model deviation (logged):** crew file sets Reviewer=Haiku; bumped to Sonnet
  for this flight's code review given the security-sensitive approval gate, two
  schema migrations (v34+v35), and the staleness state machine. Accessibility
  Reviewer=Sonnet per crew. (Opus never used for review.)

- **Accessibility review: changes-requested** (Sonnet). 4 blocking + 1
  non-blocking:
  1. [blocking] Focus lost on every approve/dismiss/restore/toggle — the full
     `doSelect` re-render (`renderAgentEditor` innerHTML rebuild) drops focus to
     body; disabling the focused button compounds it. (SC 2.4.3.)
  2. [blocking] Action-error lines (`approvalError`, per-card `actionError`,
     `nodeError`) are plain `<p hidden>` with no `role="alert"`/aria-live — silent
     on failure (unlike the staleness warning, which is correct). (SC 4.1.3.)
  3. [blocking] `historyList` `role="log" aria-live=polite` + full innerHTML
     rebuild re-announces the entire history on every action. (SC 4.1.3.)
  4. [blocking — also a real functional bug] approve/dismiss/restore/override
     buttons use non-existent CSS classes `.btn-primary`/`.btn-outlined`; correct
     classes are `.btn-filled-primary`/`.btn-outlined-primary` — render unstyled,
     lose focus ring.
  5. [non-blocking] Restore/approve buttons share identical aria-labels across
     value-nodes/cards — indistinguishable by SR rotor. (SC 2.4.6.)
- Holding to batch with the code Reviewer's findings into one Developer fix pass.

- **Code review: changes-requested** (Sonnet, flight-end). Full lane re-run green
  (4447 passed, 10 skipped, 0 failed); ruff clean; all DDs (DD1-DD8), the 4
  save-edit sites, agent-unreachability, and non-vacuous tests verified in code.
  ONE blocking finding: the value-node dedup (`self-configuration-tab.js:517-524`)
  keys `seen` by raw value only, not `(field, value)` — `description` and
  `system_prompt` both default to empty-string, so the first field processed
  claims the shared value and the second field's original-restore control is
  silently dropped (any cross-field value collision, not just empty). Missing-
  control gap vs AC8/LD2; UI-only (endpoint acts on revision_id, so no wrong-field
  mutation). Fix: scope the dedup key by field.
- Both reviews' issues (1 code blocking + 4 a11y blocking + 1 a11y non-blocking),
  all in `self-configuration-tab.js` (+ focus wiring), handed to one Developer
  fix pass.

### 2026-08-25 — Flight-end fixes (Developer)

All 5 blocking findings + the 1 non-blocking finding fixed in
`self-configuration-tab.js`; no other file touched (source-wise) other than
the new browser test and the testid registry.

1. **[code, blocking] Value-node dedup collides across fields** — `seen` is
   now keyed by `JSON.stringify([rev.field, value])` instead of the raw
   value, so `description` and `system_prompt` (both defaulting to `""`,
   DD1) no longer contend for the same dedup slot. Added
   `test_restore_controls_independent_per_field_with_shared_value` to
   `tests/browser/test_studio_self_configuration_history.py`: seeds an
   applied revision on each field sharing `base_value=""`, with
   `system_prompt`'s row created strictly after `description`'s (the exact
   order the old raw-value dedup dropped), and asserts both fields expose
   their own `side=base` restore node (4 total value-nodes). Extended
   `_seed_applied_revision` with an optional `created_at` param (default
   unchanged) to make the seeding order deterministic.
2. **[a11y, blocking, SC 2.4.3] Focus lost on every action** — added a
   cross-render "pending action" bridge: each action handler (enable/
   disable, approval-mode toggle, approve, override, dismiss, restore)
   stashes a short summary in a module-level variable keyed by agent name
   right before calling its callback; the next render of the tab for that
   agent (if the action actually triggered `_refreshAgentAfterSelfConfigurationChange`
   — a stale-detected or failed action does not) consumes it into a new
   `self-configuration-action-status` element and calls `.focus()` on it.
   The element is `tabIndex=-1`, first child of the panel. Covered the
   enable/disable toggle too, even though the finding named only
   approve/dismiss/restore/override/approval-toggle — it resolves through
   the identical `_refreshAgentAfterSelfConfigurationChange` path and had
   the same bug; leaving it unfixed would have been an inconsistent sibling
   control right next to the fixed ones.
3. **[a11y, blocking, SC 4.1.3] Action-error lines silent** — added
   `role="alert"` to `approvalError`, the per-card `actionError`, and the
   per-node `nodeError`, matching the staleness warning's existing pattern.
   Also added it to the top-level enable/disable `errorLine`, which shares
   the identical unannounced-error shape but wasn't named in the finding —
   same opportunistic-consistency call as #2.
4. **[a11y, blocking, SC 4.1.3] History live-region floods** — removed
   `role="log"`/`aria-live="polite"` from `historyList` (changed to
   `role="group"`, keeping the `aria-label` as a named region without
   live-announcing); the new `self-configuration-action-status` element
   (role="status", aria-live="polite") — the same one used for #2's focus
   target — now carries the concise one-line per-action summary instead
   (e.g. "Approved the system prompt revision.", "Restored description to
   an earlier value.").
5. **[a11y, blocking, functional] Non-existent CSS button classes** —
   confirmed via `grep -rn "btn-filled-primary\|btn-outlined-primary"
   the_one/interfaces/web/static/css/` that only `.btn-filled-primary` /
   `.btn-outlined-primary` exist anywhere in the CSS (components.css,
   admin.css, chat.css, studio.css); renamed `approveBtn`/`overrideBtn`
   from `btn-primary` → `btn-filled-primary` and `dismissBtn`/`restoreBtn`
   from `btn-outlined` → `btn-outlined-primary`. Grepped the whole
   `static/js/` tree afterward to confirm no other stray `btn-primary`/
   `btn-outlined` reference remains.
6. **[a11y, non-blocking, SC 2.4.6] Undistinguished accessible names** —
   Approve/Dismiss/Overwrite-and-approve buttons now carry an `aria-label`
   folding in the field name + a ≤40-char snippet of the revision's
   proposed value (e.g. `Approve system prompt revision: "…"`); each
   Restore button's `aria-label` folds in the field name + a snippet of its
   own (already per-field-deduped, so unique) value, replacing the old
   field-only label.

**Test outcome**: `tests/browser/test_studio_self_configuration_queue.py` (5)
+ `tests/browser/test_studio_self_configuration_history.py` (4, incl. the new
dedup regression test) — all 8 green via
`PYTHON=.venv/bin/python bash scripts/run-tests.sh ... -m browser -x
--timeout 60` (the wrapper needs `-m browser` — the repo's default `addopts`
deselects the `browser` marker otherwise). Full `make test-unit`: **4447
passed, 10 skipped** — identical to the pre-fix baseline, no regressions
(only JS + the new browser test + the testid-registry doc were touched, so
the unit lane's headcount was expected to be unchanged). `node --check` on
the edited file confirms valid syntax. Registered the new
`self-configuration-action-status` testid in `docs/ui-testid-registry.md`.

No finding turned out to be a non-issue — all 6 were confirmed real by
inspection before fixing (button-class mismatch confirmed by grep against
actual CSS; the others by reading the flagged code directly).

Not committed per instruction — working tree left as landed-but-uncommitted
for the flight-end commit step.

- **Flight-end fixes applied** (Developer, Sonnet). All 6 findings fixed, all
  confirmed real (no no-ops), all in `self-configuration-tab.js`:
  1. dedup keyed by `(field, value)` via `JSON.stringify([field, value])`; new
     browser test `test_restore_controls_independent_per_field_with_shared_value`
     (fails-old/passes-new).
  2. focus restored after re-render via a `pendingAction` bridge → new
     `self-configuration-action-status` element (`tabIndex=-1`, focused
     post-render); extended to the enable/disable toggle too.
  3. `role="alert"` on approvalError / per-card actionError / per-node nodeError
     (+ top-level errorLine).
  4. `historyList` demoted to `role="group"` (no live region); the new action-
     status live region carries the concise per-action summary.
  5. button classes corrected to `.btn-filled-primary`/`.btn-outlined-primary`.
  6. approve/dismiss/override/restore aria-labels fold in field + value snippet.
  - Tests: 8 browser green (incl. new dedup test, via `-m browser`); `make
    test-unit` 4447 passed / 10 skipped — no regression. testid registered.
- Re-review: focused Accessibility re-review of the changed tab (cycle 2). Code
  side's lone finding is pinned by its new fail-old/pass-new test + green lane.

- **Accessibility re-review (cycle 2): 4 of 5 confirmed; 1 non-blocking remains**
  (Sonnet). Dedup, the three `role="alert"` regions, the history-flood fix
  (`historyList` → `role="group"`), the aria-label naming, and the CSS-class
  rename (verified against `components.css:449/479` focus-ring rules) all correct,
  no new issues. One non-blocking: `actionStatus` is simultaneously the SC-2.4.3
  focus target AND a `role="status"`/`aria-live` region, always fired together —
  a documented NVDA/JAWS double-speak anti-pattern. Fix: drop the redundant
  live-region attributes; the focus move alone conveys the summary. Applying via
  a minimal Developer pass before commit.

- **Flight-end fix applied (double-announcement, non-blocking finding from
  cycle 2)** (Developer, Sonnet). Removed `role="status"` / `aria-live="polite"`
  from the `actionStatus` element in `self-configuration-tab.js` (kept
  `tabIndex=-1` and `.focus()`, and its `data-testid`/text-setting logic
  unchanged); updated the two stale comments describing the removed live
  region. No other element touched (`role="alert"` regions, `historyList`
  `role="group"`, etc. unchanged). `node --check` passes; both browser suites
  (`test_studio_self_configuration_queue.py`, `..._history.py`) green, 8/8, no
  regression — neither test asserted on this element's ARIA attributes, so no
  test changes were needed. Unit lane not re-run (attribute-only change).
  Left uncommitted per instruction.

- **Final a11y refinement applied** (Developer, Sonnet): removed the redundant
  `role="status"`/`aria-live` from `actionStatus` (focus-move alone carries the
  summary); 8/8 browser tests green, node --check passes. Flight-end review loop
  complete — all findings resolved.

### Phase 2d/3 — commit, PR, flight landed

- All three leg statuses → `completed`; legs checked off in flight.md.
- Single deferred commit `417786d` (code + all artifacts). Branch pushed.
- Draft PR **#172** opened (https://github.com/msieurthenardier/the-one/pull/172),
  all three legs checked; optional HAT left unchecked.
- Docs verified updated (SECURITY-MODEL.md, CLAUDE.md, agents.md) by the legs.
- Flight status `in-flight` → `landed`; Flight 2 checked off in mission.md.
- **Pre-commit gate:** full unit lane last verified green at 4447 passed / 10
  skipped after the 6-finding fix pass; subsequent changes were attribute/comment
  only (browser-verified 8/8), which cannot affect the Python unit lane.
- **[COMPLETE:flight]** — Flight 2 landed. Debrief (→ completed) runs separately
  via /flight-debrief.
- **Carry-forward:** the two pulled-out Flight-1 verification-gap items
  (shutdown-drain-under-load; two-agent-simultaneous isolation) remain to be
  logged as squawks — to be done at flight debrief (Phase 6) or on request.

### Leg 4 (uat-and-alignment) — HAT session

- Optional HAT opted in by operator. Leg → in-flight.
- Isolated env: scratch instance on **port 8485**, scratch data dir
  `/tmp/the-one-hat/data` (NEVER 8484 / prod data dir). Seeded offline
  (no provider needed — operator-oversight UX): `hat-agent` with current
  description "Revised assistant", approval mode ON, surface enabled; queue of 2
  (system_prompt clean base==current; description stale base!=current) + applied
  history "Original assistant"→"Revised assistant" (original restorable).
- Auth: background `serve` + `rotate-api-credential` created the credential;
  authenticated browser via one-time `/api/session/handoff` URL (gate covers
  GET too). Verified seeded state over bearer GETs before handing off.
- Seed helper: scratchpad `hat_seed.py` (offline; used the app-order import to
  dodge the squawk-0003 first-touch circular import). Guiding operator now.

- **HAT functional pass (operator-driven, server-verified):** AC1 approval toggle,
  AC2 queue+count, AC3 approve-clean (SPARROW persisted), AC4 staleness panel +
  override (base re-captured to real current, not stale base), AC5 dismiss (not
  applied, logged dismissed), AC6 history + restore-to-**original** (logged
  applied/restore with restored_from provenance), AC8 keyboard/focus — all PASS.
  AC7 (approval-off direct-apply) needs a live agent turn to trigger from the UI;
  covered by Leg 2 unit tests, noted.
- **AC9 UX pass:** operator screenshot → UX review agent produced a 12-item punch
  list. Operator decisions: **accept bugs 1-5** (run-on field/source text; restore
  rows lack visible field label; restore-value list fused with the chronological
  log; raw ISO timestamps; redundant empty-state) + **enh 6** (before→after diff
  highlighting), **8** (group restore nodes by field), **9** (side-by-side restore
  rows), **10** (paginate/collapse long history + stronger section separation);
  **plus** replace the enable/disable + approval on/off **buttons with slider/
  switch toggles**; and **review the app design language** so all of it matches
  existing conventions. Declined: 7 (button hierarchy), 11 (status badges), 12
  (toast). Design-language recon spawned before implementing (also satisfies the
  HAT multi-surface trigger — the switch/section styling touches shared CSS).

### HAT UX fixes

Implemented the operator-approved punch list from the AC9 UX pass above.
Presentation-only — no backend/endpoint/behavior changes. Files touched:
`self-configuration-tab.js`, `studio.css`, `docs/ui-testid-registry.md`, the
three `test_studio_self_configuration_*.py` browser suites.

- **Bug 1 (run-on field/source text):** inserted an explicit `" — "` text
  node between the field-name span and the source/status/time span in each
  history entry's head row (a literal text separator, not just a CSS gap, so
  it reads correctly under copy/paste or a linearized screen-reader pass).
- **Bug 2 (restore rows lack a visible field label):** folded into fix 8 —
  each restore row now sits under a visible "Description" / "System prompt"
  group heading (`.self-configuration-restore-group-label`) instead of
  carrying the field name only in `aria-label`.
- **Bug 3 (restore list fused with the chronological log):** two distinct
  visible subheadings — "Restore to an earlier value"
  (`.self-configuration-subheading`) above the restore-node list, and the
  collapsible's own "History (N)" `<summary>` (fix 10) for the chronological
  log — replacing the single shared "Revision history" heading.
- **Bug 4 (raw ISO timestamps):** copied the relative-time idiom from
  `chat/message-bubble.js` (`fmtTs`'s sibling pattern) as an inline
  `formatTimeAgo(epochSeconds)` — no shared formatter exists app-wide. Each
  meta line now reads e.g. "self-revised · applied · 3 hours ago"; the full
  ISO string stays on `title=`.
- **Bug 5 (redundant empty state):** `renderQueue` now hides the
  `pending-count` line (`hidden = true`, tested) when the pending list is
  empty, leaving only the dedicated `pending-queue-empty` notice.
- **Enh 6 (before→after diff highlighting):** new small primitive,
  `diffSegments` (common-prefix/common-suffix split, not a general LCS) +
  `renderDiffedValues`, applied to both the queue card's base/proposed pair
  and each history entry's before/after pair. `.diff-del`/`.diff-add`
  (studio.css) style the changed run only; unchanged prefix/suffix stay
  plain text for context. Tokens: `.diff-del` uses `--status-danger` +
  `--status-danger-bg-soft` (both exist) with strikethrough; `.diff-add`
  uses `--status-success` with underline only — there is no
  `--status-success-bg-soft` token (only warning/danger have a `-bg-soft`
  variant), so rather than fabricate one, add-highlighting relies on
  color+underline (never color alone).
- **Enh 8 (group restore nodes by field):** `RESTORE_FIELD_ORDER =
  ['description', 'system_prompt']` drives two subgroups under the existing
  per-(field,value) dedup — unchanged dedup logic, just grouped output. A
  field with zero nodes contributes no subgroup.
- **Enh 9 (side-by-side restore rows):** `.self-configuration-restore-node`
  is a flex row (studio.css) — value takes the remaining width and wraps,
  the Restore button (`.btn-outlined-primary.btn-sm`, per the operator's
  explicit ask) pins right and never shrinks.
- **Enh 10 (collapse long history):** the chronological log now renders
  inside `<details class="advanced-collapsible" data-testid=
  "revision-history-details">` (components.css primitive, zero JS) with a
  `<summary data-testid="revision-history-summary">History (N)</summary>`.
  Closed by default. The restore-node list stays outside it, always
  visible, per the spec.
- **Switches (operator's explicit addition):** both the enable/disable and
  approval-mode buttons became `.tool-enable-switch` checkbox inputs
  (admin.css, already dual-scoped `.area-admin, .area-studio` — no new
  CSS needed for the switch itself), built the way
  `design-language/surfaces-section.js`'s `toggleSwitch(on, ariaLabel)`
  does. Testids (`self-configuration-toggle-btn`,
  `approval-mode-toggle-btn`) stayed put, just moved from the retired
  `<button>` onto the `<input>` — registry updated to note the move, no
  rename. Immediate-post behavior preserved: `change` fires after the
  browser has already flipped `.checked`, which the handler treats as the
  new desired state (mirrors the old `onclick`); on failure it reverts
  `.checked` and re-enables. The `:disabled` in-flight state during the
  POST comes free from `.tool-enable-switch input:disabled` (admin.css).
  Accessible name is a static `aria-label` (e.g. "Enable
  self-configuration") rather than dynamic text, matching the
  `tools-grid.js` switch convention — checked/unchecked state is conveyed
  natively by the real `<input type="checkbox">`.
- **Match design language:** every previously-unstyled
  `self-configuration-*`/`revision-*`/`history-entry-*` class got either an
  existing primitive or new token-built `.area-studio`-scoped CSS:
  `.code-block` for all read-only value `<pre>` blocks (queue base/
  proposed, staleness current/proposed, restore-node preview, history
  before/after); `.revision-value-label` (caption + `--fg-muted` + mono)
  for the small "Base"/"Proposed"/"Current" labels; `.banner.banner-warning`
  for the staleness-panel drift advisory (previously a bare, unstyled `<p>`
  despite `role="alert"`); `.indicator-led--success/--warning/--idle`
  (mapped from `applied`/`pending`/`dismissed`+`superseded`) paired with the
  status word already in the visible meta text, so the LED is
  `aria-hidden` per the existing indicator-led a11y contract. `.editor-
  section` + `.section-title` were already on-convention and untouched.
- **Declined items not implemented:** 7 (button hierarchy re-weighting),
  11 (status badges on section titles), 12 (toast styling) — left as-is
  per operator decision.
- **A11y preserved, unchanged:** all 5 `role="alert"` error/warning regions
  (enable/disable error, approval error, card action error, staleness
  warning, restore-node error); `historyList`'s `role="group"` (not a live
  region); the cross-render `pendingAction` → `self-configuration-action-
  status` focus-restoration bridge — verified still works with the switch
  inputs (the `change` handler stashes `pendingAction` before calling the
  API, same as the old `onclick`, so the next render's focus-move is
  unaffected by the button→switch swap).
- **No conflicts found** with any existing convention or prior a11y fix —
  everything reused an existing primitive/token/testid pattern the recon
  surfaced; nothing needed forcing.

**Tests:** `node --check` passes on the JS. All three browser suites green
after updating them for the new switch markup (`to_be_checked()`/
`not_to_be_checked()` instead of button `to_have_text()`), the collapsible
history (`revision-history-details`/`revision-history-summary`, opening it
before asserting `revision-history` visibility), and an added assertion
that `pending-count` hides at zero (fix 5):

```
tests/browser/test_studio_self_configuration_tab.py ...       [ 27%]
tests/browser/test_studio_self_configuration_queue.py .....   [ 72%]
tests/browser/test_studio_self_configuration_history.py ...   [100%]
11 passed
```

Also re-ran the repo's CSS/token/testid-registry guards (`test_ui_guards.py`,
`test_token_definitions.py`, `test_design_tokens_a11y.py`) — 162 passed —
confirming the new `.area-studio`-scoped CSS has no hardcoded hex, no
undefined `var()` refs, and the registry stays in sync with source. Python
unit lane not run (out of scope — presentation-only change, per the task).

[HANDOFF:review-needed]

- **HAT UX pass — operator sign-off.** Restyle reviewed live on the scratch
  instance and accepted ("all very good, pass"): slider switches, diff-highlighted
  before/after, grouped+labelled restore rows, collapsible history, formatted
  timestamps, fixed run-on text + empty state. Green: 11 browser tests + 162
  token/guard tests. AC1-AC6, AC8, AC9 PASS; AC7 covered by unit tests. Leg 4 →
  completed; checked off in flight.md. UX follow-up committed on the flight branch
  (presentation-only; no backend change).
