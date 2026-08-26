# Flight: Operator Oversight

**Status**: in-flight
**Mission**: [Agent Self-Configuration](../../mission.md)

## Contributing to Criteria

- [ ] The operator sets, per agent, whether self-revisions apply directly or
      wait for approval — and an agent cannot change that setting for itself.
- [ ] Where approval is required, a revision has no effect until the operator
      accepts it, and the operator can see what would change before deciding.
- [ ] Every revision is recorded with what changed and when, and the operator can
      restore any earlier description or system prompt.

Criteria 1–4, 8 and 9 landed in Flight 1. Criterion 10 (external client access)
belongs to Flight 3.

---

## Pre-Flight

### Objective

Give the operator oversight of agent self-revision without changing how the
surface itself works. Add three things on top of Flight 1's direct-apply write
path: a revision log that records every revision (direct or approved) with its
before and after and when it happened; a per-agent approval mode that holds a
revision in a pending queue — with a count badge and approve/dismiss — instead
of applying it, so nothing takes effect until the operator accepts it and can
see exactly what would change; and restore, by which the operator returns a
description or system prompt to any earlier recorded value. The whole flight
reuses the pending/approve/dismiss shape the connector peer-approval flow
already establishes, ported from the Chat area into the agent's Studio
self-configuration tab. Approval mode is off by default, so Flight 1's
direct-apply behavior is unchanged until an operator turns it on.

### Open Questions

- [x] What backs the log, the queue, and restore — one table or several? → **DD1**
- [x] Where does the approval-mode setting live, and how is it kept out of the
      agent's reach? → **DD2**
- [x] How does a queued revision avoid persisting while still giving the agent a
      truthful, non-looping result? → **DD3**
- [x] What happens when the underlying field changed while a revision was
      pending (approving a stale diff)? → **DD4**
- [x] Does restore go through approval mode, and is it itself logged? → **DD5**
- [x] Where does the queue UI and its badge live, given the connector precedent
      sits in Chat and this surface sits in Studio? → **DD6**
- [x] Does a self-revision loop need a rate limit this flight? → **DD7**
- [x] What happens to a pending revision when the surface is disabled or the
      agent deleted while a proposal is outstanding? → **DD8** (agent deletion
      cascades via the FK; surface-disable marks outstanding pending rows
      `superseded` so a revision proposed under a since-revoked surface can never
      be approved after the fact). Confirmed against `PRAGMA foreign_keys=ON`
      (`db/connection.py:20`) — the cascade actually fires.

### Design Decisions

**DD1 — One `agent_revisions` table serves the log, the pending queue, and
restore at once — a single status-bearing table, mirroring `pending_approvals`.**

- Rationale: the log, the queue, and restore are three views of the same
  fact — "a proposed change to one field, in some state." The connector flow
  already proves a single table with a `status CHECK IN (...)` carries pending,
  resolved, and historical rows without a second table
  (`pending_approvals`, `db/schema.py:864`). A separate queue table would
  duplicate the columns and force a join to render the log. One table keeps
  "what changed, when, and in what state" answerable by a single query.
- Shape (new migration, template v31 `app_metadata` at `db/schema.py:1866-1880`):
  `id, agent_name, field CHECK IN ('description','system_prompt'),
  proposed_value, base_value, status CHECK IN
  ('applied','pending','dismissed','superseded'), source CHECK IN
  ('self','restore'), restored_from (nullable, references a prior revision id),
  created_at, resolved_at (nullable)`. `base_value` is the field's stored value
  at capture time — the before-image the log renders and the staleness check
  (DD4) compares against. `agent_name` carries `ON DELETE CASCADE` to `agents`
  so deleting an agent takes its revision history with it.
- Description and system prompt have **independent histories** — every row names
  its `field`, and restore (DD5) targets one field's timeline.
- Trade-off: rows accumulate unboundedly. Accepted for this flight — the volume
  is operator-scale, and `pending_approvals` sets no retention either. A
  retention policy, if ever needed, is a later servicing item, not a blocker.

**DD2 — Approval mode is a per-agent operator setting on `AgentConfig`, set by
an immediate-post control on the self-configuration tab, and unwritable by the
agent by construction.**

- Rationale: `self_revision_requires_approval: bool = False` on `AgentConfig`
  (`agent/config.py:176`), defaulting to `False` so Flight 1's direct-apply
  behavior and the mission's off-by-default posture both hold until the operator
  opts in. Persisted as a new column on `agents` (new migration; the closest
  template for a `NOT NULL DEFAULT 0` boolean is v30's guarded `ALTER TABLE
  agents ADD COLUMN … INTEGER NOT NULL DEFAULT 30`, `db/schema.py:1857-1862`,
  rather than v32's nullable `DEFAULT '{}'`).
- The agent cannot change it **because no write tool addresses it.** Flight 1's
  write allowlist is the tool catalog's *shape* — two tools, each passing a
  hardcoded field literal to `_apply_revision`'s `model_copy(update={field: …})`
  (`self_configuration/surface.py:209,222`). A new `AgentConfig` field is
  unwritable by the agent for free, exactly as the mission's "by construction"
  constraint intends. The invariant to hold: **do not add a third write tool or
  generalize `field`.**
- **Preserve-on-PUT is mandatory, or a Studio Save silently turns approval mode
  off.** `update_agent` (`api.py:737`) preserves only `mcp_overrides` against the
  stored row, then does a full-row `model_validate` + `save`. Studio rebuilds its
  payload from the DOM, and this control is deliberately not a form field — so an
  ordinary Save of *any other* field omits the key, Pydantic applies the `False`
  default, and the full-row upsert writes `False`, flipping approval mode off
  without the operator acting. This is the exact preserve-on-PUT bug class
  Flight 1's DD5 fixed for `mcp_overrides` (`_merge_preserved_mcp_credentials`,
  `api.py:759-770`); the enable-toggle analogy does **not** cover it, because the
  enable toggle's state rides `mcp_source_ids` which Studio round-trips, whereas
  a fresh scalar column has no such protection. **Leg 2 must extend the
  server-side preserve in `update_agent` to carry
  `self_revision_requires_approval` from the stored row when the payload omits
  it, and "approval mode survives an unrelated Studio Save" is an explicit Leg 2
  acceptance criterion.**
- The read projection **omits** the setting — the agent does not see whether it
  is in approval mode (`self_configuration/projection.py:64-75` lists fields
  explicitly, so a new field is invisible unless added). The agent learns its
  revision is under review only from the truthful queued result (DD3), never
  from a readable flag it might reason about adversarially.
- Set by an **immediate-post operator control** on the self-configuration tab —
  like the enable toggle (`studio/self-configuration-tab.js:21`), which posts on
  click and does not participate in `collectFormData()` dirty-tracking. It is
  **not** a Studio Save-staged form field, so an operator's unsaved edits to
  other fields never entangle with flipping approval mode.
- Trade-off: the setting rides `AgentConfig`, and the operator's PUT to
  `/api/agents/{name}` (`api.py:737`) is a full-row `model_validate` + `save`.
  The immediate-post control uses a dedicated endpoint, not the general PUT, to
  avoid clobbering concurrent Studio edits — mirroring how the enable toggle has
  its own `POST /agents/{name}/self-configuration`.

**DD3 — Under approval mode the write takes a non-persisting branch: it enqueues
and returns a truthful queued result, without touching the store or the live
agent.**

- Rationale: Flight 1's `_apply_revision` always persists (LD2) and returns a
  hardcoded `applied_to_store: True` (`surface.py:190`). This flight adds the
  branch LD4 anticipated but never built. When approval mode is on the tool:
  enqueues an `agent_revisions` row (`status='pending'`, `source='self'`,
  `base_value` = current stored value), and returns without calling
  `agent_store.save` and without `pending.record` — the live agent is not
  mutated and the store is not written.
- The queued result is **truthful and non-looping**:
  `{applied_to_store: false, effective: "pending_operator_approval",
  field, message: "Recorded and awaiting operator review; it will take effect
  once approved."}`. It does not claim a turn/session timing it cannot honor,
  and it does not tempt a retry: the pending queue **dedups one row per
  `(agent_name, field, status='pending')`** — an upsert-in-place, exactly the
  `upsert_pending` dedup contract (`repositories.py:721`). A second attempt at
  the same field updates the outstanding proposal rather than piling rows, so a
  looping agent cannot flood the queue.
- Direct mode (approval off) is unchanged behaviorally, **but now also writes an
  `applied` revision-log row** — the log captures direct revisions too, not only
  approved ones. This is the one behavioral addition to the Flight 1 path.
- **Post-approval propagation is next-session only, and the queued row does not
  carry the proposing turn's `apply` choice.** By the time the operator approves,
  the proposing turn is long over — there is no live turn to honor `next_turn`
  against. So the queued row records no timing; on approval the revision persists
  through the store and reaches conversations by the same persist-then-rebuild
  path `next_session` already uses (`_get_or_restore_session`, Flight 1 DD7).
  The agent's `apply` argument is still accepted at queue time (the tool's
  signature is unchanged) but is moot under approval mode and is not replayed.
  This is a Leg 2 acceptance criterion.
- Trade-off: the two modes diverge inside `_apply_revision`, which was a single
  straight-line path. Contained — one branch on one boolean, both arms already
  need the store handle they hold.

**DD4 — Staleness is fail-closed at approve-time by comparing the field's
current stored value against the `base_value` captured when the revision was
queued.**

- Rationale: `SQLiteAgentStore.save` is a full-row last-writer-wins upsert with
  no version guard — `INSERT … ON CONFLICT(name) DO UPDATE SET <every column>`
  (`repositories.py:189`), no `WHERE updated_at = ?`, no etag. Approving a diff
  captured earlier would silently overwrite any intervening edit — the mission
  names this "a real defect." So the pending row carries `base_value`, and on
  approve the endpoint compares it to the current stored value of that field:
  - **unchanged** → apply: persist the proposed value, mark the row `applied`,
    set `resolved_at`;
  - **drifted** → **409**, returning both the current value and the proposed
    value so the operator sees exactly what re-approving would overwrite; the
    operator must re-confirm explicitly to override, which re-captures
    `base_value` and applies.
- This is the **only** new concurrency apparatus, and it is scoped to the
  approval path — not a general optimistic-concurrency retrofit of
  `SQLiteAgentStore`. To avoid clobbering *other* fields between capture and
  apply, the approve path must re-load the current config and
  `model_copy(update={field: proposed})` only the target field, then `save` —
  the same load→copy→save `_apply_revision` already uses (`surface.py:175`).
  A targeted `UPDATE agents SET <field>=?` that skipped the fresh load would
  reintroduce the whole-row staleness this decision closes; do not write one.
- The transition repo is idempotent and rejects illegal transitions with a 409,
  reusing the connector `_transition` semantics
  (`repositories.py:842-863`): approving an already-applied row is a no-op;
  approving a dismissed row is a 409.
- Trade-off: an operator override still overwrites the interim edit — but now
  knowingly, having seen it. That is the mission's bar ("can see what would
  change before deciding"), not silent loss.

**DD5 — Restore is an operator-direct action: it applies immediately regardless
of approval mode, and is itself recorded as a new `applied` revision with
provenance.**

- Rationale: restore is the operator acting, and the operator is the approval
  authority — routing their own restore through the pending queue would be
  incoherent (who approves the approver?). So restore never queues, even when
  approval mode is on. It persists the chosen earlier value immediately via the
  same path a direct revision uses.
- Restore is **logged as a new row**, not a pointer rewind: `source='restore'`,
  `restored_from` = the id of the revision whose value is being reinstated,
  `base_value` = the pre-restore current value, `status='applied'`. The log
  stays a strict append-only timeline — "restored to the value from #N at time
  T" reads as an event, and a future reader can reconstruct the exact sequence.
- Description and system prompt restore independently; each targets its own
  `field` timeline (DD1).
- Trade-off: restoring re-persists a whole field value and so is subject to the
  same last-writer-wins as any write. Acceptable — restore is a deliberate
  operator action at a moment of their choosing, not a deferred proposal, so the
  staleness window that motivates DD4 does not apply.

**DD6 — The queue, the log, and restore live in the Studio self-configuration
tab; the pending-count badge surfaces in Studio, per agent — reusing the
connector flow's shape, not its location.**

- Rationale: the connector peer-approval pattern is fully realized and worth
  reusing wholesale — a per-scope count endpoint, a field-projected list
  endpoint, an idempotent approve/dismiss transition repo, a poller-driven
  badge, and a terminal-status-in-place button→badge swap
  (`api.py:3262-3413`, `static/js/app.js:14-38`,
  `areas/chat/pending-approval-banner.js`). But it lives in the **Chat** area
  and hangs off the Chat nav button; this surface is a **Studio** concern. Flight
  2 ports the *shape* into the agent editor's self-configuration tab, where the
  enable toggle and approval-mode control already sit.
- The count is **per agent** (a pending queue belongs to one agent's surface),
  unlike the connector badge's global count. Endpoints mirror the connector set,
  scoped by agent name:
  `GET  /agents/{name}/self-configuration/revisions` (log + pending, field-
  projected — never `base_value` of unrelated concern, never secret material),
  `GET  /agents/{name}/self-configuration/revisions/pending-count`,
  `POST /agents/{name}/self-configuration/revisions/{id}/approve`,
  `POST /agents/{name}/self-configuration/revisions/{id}/dismiss`,
  `POST /agents/{name}/self-configuration/revisions/{id}/restore`.
  Each write path carries the connector flow's cross-ID-smuggling 404 guard
  (`api.py:3301`): a revision id that does not belong to the named agent is a
  404, not a silent cross-agent action.
- Trade-off: the badge does not aggregate across agents into a single global
  indicator. Accepted — oversight here is per-agent, and a global count would
  imply a cross-agent queue the mission's per-agent scoping does not have.

**DD7 — No rate limit this flight; the revision log and approval mode are the
loop control.**

- Rationale: the mission left open whether a self-revision loop needs a rate
  limit or only needs to be visible. With the log making every revision
  observable and approval mode letting the operator gate cadence outright, the
  visibility is in place; a throttle would add a window, a knob, and its own edge
  cases for a harm not yet observed. The pending-row dedup (DD3) already stops a
  looping agent from flooding the queue.
- Revisit only if a loop proves harmful in practice — recorded as a possible
  future servicing item, not built speculatively.

**DD8 — Outstanding pending revisions are resolved when their surface goes away:
agent deletion cascades them off; surface-disable marks them `superseded`.**

- Rationale: two teardown paths can strand a pending row. **Agent deletion** is
  handled structurally by DD1's `ON DELETE CASCADE` to `agents(name)` — the
  cascade fires because `PRAGMA foreign_keys=ON` is set on the runtime connection
  (`db/connection.py:20`), the same basis `pending_approvals` relies on.
  **Surface-disable**, however, deletes only the MCP source row and would leave
  `agent_revisions` pending rows still approvable — so an operator could approve
  a revision the agent proposed under a surface that has since been revoked.
  Disable must therefore mark every outstanding pending row for that agent
  `superseded` (the status DD1 already carries), the same disable path that
  tears the source row down (`self_configuration/manage.py` `disable`).
- Trade-off: a revision the operator might still have wanted is dropped on
  disable rather than held. Accepted — disabling the surface is a deliberate
  withdrawal of the agent's ability to propose; honoring proposals made under it
  afterward would contradict the withdrawal.

### Prerequisites

- [x] Flight 1 landed and merged (PR #171) — the surface, the two write tools,
      `_apply_revision`, the projection, and the self-configuration tab all
      exist on `main`.
- [ ] Migrations are at v33 on `main`; this flight's new table and column take
      the next sequential versions. Confirm no other in-flight branch has
      claimed v34/v35 before implementing.
- [ ] The connector peer-approval implementation is the reference; its endpoints
      and repo (`api.py:3262`, `repositories.py:693`) are stable on `main`.
- [ ] For the optional HAT leg: a dev instance on a non-8484 port with a scratch
      data directory, an agent with the surface enabled and a working provider,
      and a browser apparatus (goldfinch preferred; chrome-devtools is the
      sanctioned fallback). Same environment Flight 1's behavior test used.

### Pre-Flight Checklist

- [x] All open questions resolved or deferred to a named leg
- [x] Design decisions documented
- [ ] Prerequisites verified
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

Three additive slices over Flight 1's write path, each self-contained:

1. **Revision log foundation (schema + logging the direct path).** Create the
   `agent_revisions` table (new migration, template v31) and its repository —
   append, list (field-projected), get-by-id-scoped-to-agent, count-pending, and
   the idempotent transition (approve/dismiss/supersede) reusing the connector
   `_transition` semantics. Wire the *existing direct* write path to append an
   `applied` row on every revision, so the log is populated before approval mode
   or restore exist. This is the hard-to-reverse, schema-shaped slice.

2. **Approval mode + pending queue + staleness.** Add the
   `self_revision_requires_approval` column (new migration, template v32) and its
   `AgentConfig` field; the immediate-post operator control on the
   self-configuration tab; the non-persisting queued branch in `_apply_revision`
   with the truthful queued result and pending-row dedup; the approve/dismiss
   endpoints with the fail-closed `base_value` staleness compare (409 +
   current-vs-proposed on drift, re-confirm to override); the per-agent count
   endpoint and badge; and the Studio queue UI (approve/dismiss cards,
   terminal-status in-place swap). The governance slice — the mission's central
   risk surface.

3. **Restore.** The operator-direct restore endpoint (immediate apply, logged
   with `source='restore'` + `restored_from` provenance, cross-ID 404 guard) and
   the log-view UI with per-version restore for each field's independent
   timeline.

All three reuse existing patterns rather than inventing: the connector flow for
queue/badge/transition, the enable toggle for the immediate-post control, and
Flight 1's `_apply_revision` persist path for both queued-apply and restore.

### Checkpoints

- [ ] `agent_revisions` table migrated and its repository unit-tested; direct
      revisions write an `applied` log row
- [ ] Approval mode holds a revision in the queue without persisting; the agent
      gets a truthful, non-looping queued result; the operator sees the pending
      count badge
- [ ] Approving a stale diff fails closed (409 + current-vs-proposed); approving
      a fresh diff applies and propagates per the revision's chosen timing
- [ ] Restore returns a field to any earlier recorded value, logged with
      provenance; description and system prompt restore independently
- [ ] The agent cannot read or write the approval-mode setting (projection omits
      it; no write tool addresses it)
- [ ] Docs updated (`SECURITY-MODEL.md`, `agents.md`/`CLAUDE.md`) to reflect
      approval mode, the revision log, and restore

### Adaptation Criteria

**Divert if**:
- The `agent_revisions` table cannot carry `base_value` and the current value in
  a way that survives the encrypted-column boundary cleanly (system_prompt and
  description are plaintext columns today — confirm before assuming). If either
  becomes secret-bearing, the projection and log-render allowlists must be
  revisited before proceeding.
- Approval mode's non-persisting branch cannot be isolated to `_apply_revision`
  without touching the live-turn deferral path (`pending.py`) — if the two
  "pending" concepts entangle, stop and re-scope the module boundary.

**Acceptable variations**:
- Endpoint URL shapes may adjust to match the router's existing conventions.
- The badge's poll interval and placement within the Studio tab are
  implementation detail.
- Combining the two migrations into one sequential block is fine if both land in
  the same leg's commit; keep table-create and column-add as distinct guarded
  steps regardless.

### Legs

> **Note:** Tentative until each is planned. Legs are sized by decision and risk,
> not effort.

- [x] `revision-log-foundation` — the `agent_revisions` table + migration, the
      revision repository, and wiring the direct write path to log every
      applied revision. (High-risk: schema + migration.)
- [x] `approval-mode-and-queue` — the approval-mode column + operator control
      (with the mandatory `update_agent` preserve, DD2), the non-persisting
      queued write branch, approve/dismiss with the fail-closed staleness compare
      (re-load-then-`model_copy`, DD4), the surface-disable supersede (DD8), the
      per-agent count badge, and the Studio queue UI. (**Highest risk tier —
      always design-reviewed**: state machine, the mission's central write-risk
      surface, security-sensitive, and the largest leg.) The new persisted
      concept is named distinctly (`agent_revisions` / "revision queue"); nothing
      is added to `self_configuration/pending.py` (the in-memory next-turn
      registry), and the queued branch must return before `pending.record` to
      keep the two "pending" concepts separate. Optional hardening: a partial
      unique index on `(agent_name, field) WHERE status='pending'` to make the
      dedup a DB invariant rather than an application-level SELECT-then-write.
      **Note:** the two Flight-1 debrief carry-overs (shutdown-drain-under-load,
      two-agent isolation) were initially folded here but pulled out at Leg 2
      design review — they are pool/lifecycle verification-debt orthogonal to
      approval governance, and belong in their own follow-up (squawks, logged at
      flight end) rather than in this leg.
- [x] `revision-restore` — operator-direct restore (logged with provenance) and
      the log-view UI with per-field restore. (Medium/high: touches the live
      persist path, additive over the Leg 1 table.)
- [ ] `uat-and-alignment` *(optional)* — guided HAT: the operator drives
      approve/dismiss, the staleness re-confirm, restore, and the badge
      end-to-end, with fixes applied inline.

---

## Post-Flight

### Completion Checklist

- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing (`make test-unit`; relevant browser lanes)
- [ ] Documentation updated

### Verification

- **Unit** — the revision repository (append, list projection, count, idempotent
  transitions, illegal-transition 409); the queued branch (no store write, no
  live mutation, truthful result, dedup); the staleness compare (unchanged →
  apply, drifted → 409 with both values); restore (logged, provenance,
  independent fields); the by-construction exclusions (projection omits the
  setting; no write tool reaches it).
- **Browser** — the connector flow's browser tests are the precedent
  (`tests/browser/test_flow_chat_pending_*.py`): the badge appears and clears,
  approve/dismiss swaps the card in place, the staleness 409 renders
  current-vs-proposed, restore updates the field. These cover criterion 6's
  "operator can see what would change before deciding" as a rendered-state
  observable.
- **Propagation** — on approval a revision persists and reaches conversations by
  the persist-then-rebuild path `next_session` already uses (DD3); the proposing
  turn's `apply` choice is moot and not replayed. That path is the one Flight 1
  behavior-tested (`tests/behavior/agent-self-revision-propagation.md`), so no
  new two-agent behavior test is warranted — the fresh-conversation observable
  there already covers next-session propagation. The optional HAT leg exercises
  the operator-facing approve→propagate flow live.
