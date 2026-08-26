# Leg: revision-restore

**Status**: completed
**Flight**: [Operator Oversight](../flight.md)

## Objective

Let the operator restore a description or system prompt to any earlier value the
field actually held — applied immediately (operator authority, never queued),
recorded as a new `applied`/`restore` revision with provenance — and surface the
full revision history in the Studio self-configuration tab with a per-entry
restore control.

## Context

- **DD5** — restore is operator-direct: it applies immediately regardless of
  approval mode (the operator is the approval authority, so routing their restore
  through the queue would be incoherent), and it is logged as a **new** row
  (`source='restore'`, `restored_from` = the id of the revision reinstated,
  `base_value` = the pre-restore current value, `status='applied'`) rather than a
  pointer rewind — the log stays a strict append-only timeline.
- **DD1** — description and system prompt restore **independently**; each restore
  targets one field's timeline.
- The `agent_revisions` schema (Leg 1 v34) already carries `source='restore'` and
  `restored_from`, and `AgentRevisionRepository.append`
  (`the_one/db/repositories.py:939`) already accepts `source`/`status`/
  `restored_from`/`base_value`/`created_at`/`resolved_at`. So restore needs **no
  migration and no new repository method** — it reuses `append` and the existing
  apply path.
- The apply path to mirror is the approve endpoint's clean arm
  (`the_one/interfaces/web/api.py:1082` `approve_agent_revision`): `store, config
  = await _load_agent_or_404(name)` → `config.model_copy(update={field: value})`
  → `store.save(...)`. Restore reuses exactly this, then appends the restore row.
- **LD1: restore is valid only against an `applied` revision.** Only `applied`
  rows represent values the field actually took. A `pending` row was never
  applied, a `dismissed` row was declined, a `superseded` row was orphaned by a
  surface-disable — reinstating any of their values would resurrect a value the
  field never held or the operator/agent explicitly did not enact. Restore
  therefore targets a revision whose `status='applied'`; a non-applied target is
  refused (409).
- **LD2: restore reinstates a *value node*, not only a `proposed_value` — so the
  original (pre-first-revision) value is reachable.** The distinct values a field
  has held are: the earliest applied revision's `base_value` (the original,
  authored by the human at agent-create or the last value before any
  self-revision) followed by every applied revision's `proposed_value`. If
  restore could only reinstate `proposed_value`s, the **original would be
  unreachable** — it is never a `proposed_value`, only a `base_value` — defeating
  the primary restore case (undo the agent's first change back to the human's
  original) and failing criterion 7's "restore **any** earlier … prompt". So the
  restore endpoint takes `side` (`"proposed"` default | `"base"`): `proposed`
  reinstates the target row's after-image, `base` reinstates its before-image.
  `side=base` on **any** applied row is always a valid restore — every applied
  row's `base_value` is a value the field genuinely held at that point — so no
  "which is earliest" logic is needed and no phantom value is reachable. (Note:
  the field can also change **out of band** — `PUT /agents/{name}` edits
  `description`/`system_prompt` directly with no revision row — so a mid-timeline
  `base_value` does **not** necessarily equal the prior row's `proposed_value`;
  it may be an operator-typed value. This is why `base` must be reachable on
  rows other than the earliest, not only for the original.)
- **LD2 UI — the history renders one Restore per *distinct value-node*.** To make
  "restore any earlier value" literally true without duplicate buttons, the tab
  computes the set of distinct values the field has held by deduping
  `base_value` and `proposed_value` across all `applied` rows (each value-node
  carries a `(revision_id, side)` that reinstates it — any one, if a value
  recurs). Each node gets one Restore control. This surfaces the original
  (earliest `base_value`) and any out-of-band operator-set value (a mid-row
  `base_value`) for free. `restored_from` records the chosen target revision id
  regardless of side; the reinstated value is self-describing in the new row's
  `proposed_value`.

## Inputs

Post-Leg-2 state:

- `agent_revisions` table + `AgentRevision` model + `AgentRevisionRepository`
  (`append`/`get`/`list_for_agent`/`count_pending`/transitions/…). `append`
  supports `source='restore'` + `restored_from`.
- `GET /agents/{name}/self-configuration/revisions` (`api.py:1035`
  `list_agent_revisions`) already returns the agent's full history newest-first
  (all statuses), full non-secret rows.
- `approve_agent_revision` (`api.py:1082`) — the clean apply arm to mirror;
  `dismiss_agent_revision` (`api.py:1058`) — the cross-ID 404 guard pattern.
- Helpers: `_load_agent_or_404(name) -> (store, config)` (`api.py:1006`);
  `_agent_revisions_repo()` (`api.py:265`); `now_iso()` (`db/models.py:14`).
- Studio self-configuration tab (`.../areas/studio/self-configuration-tab.js`) —
  Leg 2 added the pending queue + approval-mode toggle + count; callbacks in
  `.../areas/studio.js`; host `agent-editor.js`;
  `_refreshAgentAfterSelfConfigurationChange` re-renders after an action.

## Outputs

- `POST /agents/{name}/self-configuration/revisions/{revision_id}/restore`
  (query `side=proposed|base`) — operator-direct restore, applies immediately,
  logs an `applied`/`restore` row with provenance; cross-ID 404 guard; 409 if the
  target is not `applied`.
- Studio tab: a revision-history view (the full log, newest-first) with one
  Restore control per distinct value-node (dedup of base+proposed across applied
  rows — covering the original, each self-revised value, and any out-of-band
  operator-set value); description and system-prompt entries visually
  attributable to their field; restore triggers the endpoint and refreshes.
- Unit tests (restore applies + logs provenance, independent fields, non-applied
  target refused, cross-ID 404) + browser test (history renders, restore updates
  the field) + docs.

## Acceptance Criteria

- [x] AC1 — `POST .../revisions/{id}/restore` (default `side=proposed`) where
      revision `{id}` is `applied` loads the agent, sets the target field to that
      revision's `proposed_value` (`config.model_copy` → `store.save`), and
      appends a **new** row with `source='restore'`, `status='applied'`, `field`
      = the target's field, `proposed_value` = the reinstated value, `base_value`
      = the field's pre-restore current value, `restored_from` = `{id}`,
      `resolved_at` = `created_at`. Returns the new revision.
- [x] AC1b — **LD2 original reachable:** `POST .../revisions/{id}/restore?side=
      base` reinstates the target row's `base_value` (its before-image). Restoring
      with `side=base` against the **earliest applied revision** of a field
      returns the field to its **original** pre-first-revision value; a test
      pins that the original is reachable — agent created with description D0,
      approval mode **OFF** so the self-revision to D1 applies immediately (an
      `applied` row, not `pending` — else restore would 409), operator restores
      `side=base` of that row → field is D0 again, logged as an `applied`/`restore`
      row with `proposed_value=D0` **and** `base_value=D1` (the pre-restore
      current), `restored_from` = the D0→D1 revision id.
- [x] AC2 — Restore applies **immediately regardless of approval mode** — with
      `self_revision_requires_approval` ON, restore still persists and logs
      `applied` (it does not enqueue a pending row). (DD5.)
- [x] AC3 — The restore change reaches new conversations next-session (persist
      path; the live open conversation is not mutated — consistent with the
      surface's next-session semantics).
- [x] AC4 — A restore whose target revision is **not** `applied`
      (pending/dismissed/superseded) is refused with **409** and touches neither
      the store nor the log.
- [x] AC5 — Cross-ID guard: a `{id}` whose `agent_name` ≠ path `{name}` → 404;
      unknown id → 404 (mirroring dismiss/approve).
- [x] AC6 — Description and system prompt restore independently: restoring a
      description revision changes only `description` and logs a
      `field='description'` row; the system prompt is untouched; and vice versa.
- [x] AC7 — Restoring to a value equal to the current one still logs a
      `restore`/`applied` row (an honest record that the operator restored at time
      T) — restore is not silently skipped. (`base_value == proposed_value` in
      that row is acceptable.)
- [x] AC8 — Studio self-configuration tab renders a revision-history view (the
      full `GET /revisions` list, newest-first) distinct from the pending queue:
      each entry shows field, before→after, timestamp, source (`self`/`restore`)
      and status. The history renders one Restore control per **distinct
      value-node** — the dedup of `base_value` + `proposed_value` across all
      `applied` rows, each node restoring via an appropriate `(revision_id,
      side)` — so every value the field has held is restorable: the original
      (earliest `base_value`, `side=base`), each self-revised value
      (`side=proposed`), and any out-of-band operator-set value (a mid-row
      `base_value`). Criterion 7's "any earlier value" is literally met, with no
      duplicate buttons. Restore POSTs and refreshes via
      `_refreshAgentAfterSelfConfigurationChange`. Non-applied entries show their
      status without contributing a value-node.
- [x] AC9 — Accessibility: history entries and the Restore controls meet the
      tab's existing bar (labelled buttons, keyboard-operable, visible focus,
      history region announced) — reviewed by the Accessibility Reviewer at
      flight-end.
- [x] AC10 — `make test-unit` green (no regressions); relevant browser lane
      green; docs updated (`SECURITY-MODEL.md`/`CLAUDE.md`/`agents.md` note
      restore — operator-direct, logged, applied-only target).

## Verification Steps

- AC1/AC2/AC3 — endpoint test: seed an applied revision (or run a direct
  revision to create one), change the field, then restore to the earlier
  revision; assert the store now holds the restored value, a new
  `restore`/`applied` row exists with the right provenance and `base_value` =
  the value just before restore; assert it works with approval mode ON (no
  pending row created).
- AC4 — parametrize across **all three** non-applied statuses
  (pending/dismissed/superseded): seed each, restore → 409; assert store and log
  unchanged in each case.
- AC1b — seed the original→first-revision chain, restore `side=base` of the
  earliest applied row, assert the field returns to the original and the new
  row's `restored_from` resolves to an existing revision.
- AC5 — restore an id under agent B via agent A's path → 404; unknown id → 404.
- AC6 — restore description vs system prompt; assert field isolation.
- AC7 — restore to the current value; assert a row is still logged.
- AC8/AC9 — browser lane against a dev instance (non-8484 port, scratch data
  dir): render history, click Restore, assert the field updates and a history
  entry appears; Accessibility Reviewer pass.
- AC10 — `make test-unit` + browser lane + docs.
- Test command: `PYTHON=.venv/bin/python bash scripts/run-tests.sh <files> -x
  --timeout 30` iterating, then `make test-unit` once at leg end.

## Implementation Guidance

1. **Endpoint** (`the_one/interfaces/web/api.py`, beside the other revision
   routes ~`:1035-1160`): `POST /agents/{name}/self-configuration/revisions/
   {revision_id}/restore`, query `side: Literal["proposed", "base"] =
   "proposed"` — a Literal (not a plain `str`) so FastAPI auto-422s an invalid
   value, the enum analog of the `override: bool = False` query param on approve
   (`api.py:1082-1084`); a plain `str` would let a typo like `side=basе` fall
   silently into the else-branch and restore the wrong side.
   - `store, config = await _load_agent_or_404(name)`; `revisions_repo = await
     _agent_revisions_repo()`.
   - `revision = await revisions_repo.get(revision_id)` in `try/except KeyError →
     404`; cross-ID guard `if revision.agent_name != name: 404` (copy the
     dismiss/approve pattern verbatim).
   - `if revision.status != "applied": raise HTTPException(409, detail=f"Revision
     {revision_id} is {revision.status}; only an applied revision can be
     restored")` (LD1).
   - `reinstated = revision.proposed_value if side == "proposed" else
     revision.base_value` (LD2).
   - `base_value = getattr(config, revision.field)` (pre-restore current value).
   - `await store.save(config.model_copy(update={revision.field: reinstated}))`.
   - `ts = now_iso()`; `restored = await revisions_repo.append(agent_name=name,
     field=revision.field, proposed_value=reinstated, base_value=base_value,
     source="restore", status="applied", restored_from=revision_id,
     created_at=ts, resolved_at=ts)`.
   - `return restored.model_dump()`.
   - Do **not** consult `self_revision_requires_approval` — restore never queues
     (DD5).
2. **Studio history view** (`self-configuration-tab.js` + `areas/studio.js` +
   `agent-editor.js`): add a history section rendering the full `GET /revisions`
   list (the tab may already fetch it for the queue — reuse that fetch; the queue
   is the `status==='pending'` subset, the history is the whole list). For each
   entry show field / before→after / timestamp / source / status; render a
   Restore button (`data-testid`, labelled) on `applied` entries only. Wire an
   `onRestore(name, revisionId)` callback → `POST .../restore` → on success
   `_refreshAgentAfterSelfConfigurationChange`. Register new `data-testid`s in
   `docs/ui-testid-registry.md` (Leg 2's convention).
3. **Docs**: note restore in `SECURITY-MODEL.md` (operator-direct, never
   agent-invokable — there is no restore *tool*, only the operator endpoint) and
   `CLAUDE.md`/`agents.md` (the new endpoint + the applied-only rule).

## Edge Cases

- **Restore of a `restore` row** — a prior restore is itself an `applied`/
  `restore` row, so it is a legal target; restoring it reinstates its
  `proposed_value` and chains `restored_from` to it. Fine — the timeline stays
  coherent.
- **Concurrent operator edit during restore** — restore is a deliberate,
  immediate operator action (not a deferred proposal), so the DD4 staleness
  window does not apply; it takes last-writer-wins like any direct write. Do not
  add a base-compare to restore.
- **Restoring after the surface was disabled** — restore is an operator endpoint
  on the agent, independent of whether the self-configuration surface is enabled;
  it remains available (the operator can always restore). It does not require or
  re-enable the surface.
- **No agent-facing restore** — there is no restore MCP tool; the write allowlist
  (the tool catalog's shape) is unchanged, so the agent cannot restore itself.
  This is the mission's "by construction" boundary held.

## Files Affected

- `the_one/interfaces/web/api.py` — the restore endpoint.
- `the_one/interfaces/web/static/js/areas/studio/self-configuration-tab.js`,
  `the_one/interfaces/web/static/js/areas/studio.js`,
  `the_one/interfaces/web/static/js/areas/studio/agent-editor.js` — history view
  + Restore control.
- `tests/` — endpoint unit tests + a browser test.
- Docs: `SECURITY-MODEL.md`, `CLAUDE.md`/`agents.md`, `docs/ui-testid-registry.md`.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (`make test-unit` green; browser lane green)
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] This is the **last autonomous leg** — do NOT land the flight or commit here;
      the flight-end Reviewer (+ Accessibility Reviewer) and the single deferred
      commit run after this leg lands, per /agentic-workflow Phase 2d.

---

## Citation Audit

Verified against the working tree (Legs 1-2 landed-uncommitted) across two design
review cycles:

- `AgentRevisionRepository.append` `repositories.py:939` (kwargs
  source/status/restored_from/base_value/created_at/resolved_at, resolved_at
  required). ✓
- `agent_revisions` schema `schema.py:1980-1992` (source/status CHECK,
  restored_from self-FK, base_value/proposed_value NOT NULL). ✓
- Endpoint helpers: `_load_agent_or_404` → (store, config) `api.py:1006`;
  `_agent_revisions_repo` `api.py:265`; approve clean arm `api.py:1082`
  (apply `:1141-1143`), `override: bool = False` query precedent `:1082-1084`;
  dismiss cross-ID 404 `api.py:1058`; list `api.py:1035`; `now_iso` models.py:14. ✓
- Out-of-band field edit: `PUT /agents/{name}` `api.py:745`, `store.save`
  `:806` — no revision row appended (drives LD2's value-node UI). ✓
- Studio tab already fetches the full revisions list
  (`fetchRevisions`/`fetchSelfConfigurationRevisions`), queue = pending subset;
  `_refreshAgentAfterSelfConfigurationChange` re-renders; `docs/ui-testid-
  registry.md` exists (Leg 2). ✓
