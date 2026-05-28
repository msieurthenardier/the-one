# Flight: Pairing Resolution + Connectors-Screen Detach

**Status**: completed
**Mission**: [Discord Connector Depth & Robustness](../../mission.md)

## Contributing to Criteria

- [ ] **#8** — Pairing question resolved: ship BOTH flows per mission OQ default (c) — Discord-native one-click approval as primary; `PAIR <code>` text-prefix kept as fallback for out-of-band pre-approval. Substrate's pairing primitive unchanged so other connectors choose their own UX. HAT-validated against a real Discord DM from an unpaired account.
- [ ] **#9** — Operator can detach an attached agent from the Connectors screen without navigating to Studio's agent editor. Detach action revokes the agent's access immediately, persists across restart, and the connector account's agent-list updates without a page reload.

Indirect support:
- **#18** (15-min onboarding) — Discord-native approval removes a major out-of-band friction.
- **#19** (full-day daily-driver run) — peer-approval UX reduces operator intervention overhead.

Carry-forward fold-ins (per Phase 1b recon shared-surface analysis):
- **F7 Rec #3(a)** — `.tool-enable-switch` CSS default flip (n=4 override consolidation). Shares F9's detail-page CSS surface.
- **F7 Rec #3(c)** — studio-event-bus extraction (F7 cited at n=3; F9 reaches n=4+ with the new detach event). Operator-confirmed fold-in.
- **F8 action item** — Extend `provider-shape-portability` convention text at `agents.md:134` with the legacy-row AssertionError runbook (~5 LOC; F9 touches agents.md anyway).

Carry-forwards deferred to next routine-maintenance (separate-surface): F7 Rec #3(b) `_inbound.py` extraction, F7 Rec #3(d) field-row primitive, F7 plugin-author docs, F8 dead `content is None` branch.

---

## Pre-Flight

### Objective

Ship two scope items in one flight: (1) a Discord-native peer-approval flow that complements (does not replace) the existing `PAIR <code>` text-prefix primitive; (2) a one-click detach affordance on the connector account detail page that immediately revokes agent access.

**Cycle-1 Architect review surfaced two architectural facts the initial spec missed**: Discord plugin has no `resolve()` hook today (falls through to `_default_permit`); the existing codec at `db/codec.py:messages_to_ui_events` is Message-derived and cannot host non-Message events like pending-approval. The spec below incorporates both: F9 ADDS a new Discord `resolve()` hook (DM-only scope) AND a new persistence shape (separate `pending_approvals` table with its own codec projection path, not threaded through `messages_to_ui_events`).

### Open Questions

All planning-time OQs resolved at flight-design time:

- [x] **Pairing OQ (mission default c)** — dual-flow: Discord-native primary + PAIR text-prefix fallback. Operator-confirmed.
- [x] **Detach UI** — detail-page only; Connectors grid surfaces agent-count badge.
- [x] **Approval-flow event type** — new top-level `pending-approval` event type (not system-type variant). Operator-confirmed.
- [x] **Discord `resolve()` hook scope** — **DM-only**. Returns `NeedsPairing` only when inbound is a DM from a peer not in `account.config["allowlist"]["peers"]`. Guild-channel messages from non-allowlisted peers stay `Permit` (current behavior). Matches mission text "when an unknown user DMs the bot." Operator-confirmed.
- [x] **Approval authorization** — operator-only. Single-user local-tool security posture per mission constraints; no auth added; endpoint callable only via the local Studio UI. Locked at flight planning.
- [x] **Text-prefix precedence** — `PAIR` prefix takes precedence if detected; pending-approval flow activates only when no `PAIR` prefix is present. Matches current behavior; least-surprise default. Locked at flight planning.
- [x] **Convention codification proposal (former §10 dual-flow convention)** — **DROPPED** per architect review. n=1 by definition (Discord is the only platform); codify if/when a second connector platform earns the same pattern.
- [x] **HAT inclusion** — yes, optional final leg.
- [x] **Pending-approval persistence shape** — **new `pending_approvals` table** (operator-deferred to architect; cycle-1 architect flagged the codec-shape issue; flight director's call: separate table is the best long-term shape; cycle-2 architect validates). Independent lifecycle from chat_sessions; queryable by status; codec gains a dedicated projection path (NOT through `messages_to_ui_events`).
- [x] **Detach source-of-truth** — **agent-side `agents.connector_account_ids`** is the existing source (today mutated via `PUT /api/agents/{name}`). F9 DELETE endpoint lives on the agent-side resource path: `DELETE /api/agents/{agent_name}/connector-accounts/{account_id}`. UI surfaces (connector detail page button, grid badge) read the same source. No new write path; no source-of-truth duplication. Cycle-2 architect validates.

### Design Decisions

**§1. Discord `resolve()` hook is a NEW substrate-level addition** (architect cycle-1):
- The Discord plugin at `the_one/connectors/_discord.py` does not currently define `def resolve`. The dispatcher falls back to `_default_permit` (cited by architect at `_inbound.py:392`). Unknown DMs today reach `agent.step` directly.
- F9 L1 adds `def resolve(self, account, envelope) -> ResolveOutcome` to the Discord plugin (note: type name `ResolveOutcome` per actual ADT at `the_one/connectors/base.py:252`, NOT `OutboundOutcome`). Scope (operator-locked): DM-only NeedsPairing for peers not in `account.config["allowlist"]["peers"]`. Guild messages and already-allowlisted peers return `Permit`.
- Trade-off: limits F9's protection surface to DMs (mission text aligns). Guild-mention-of-unknown-bot stays in the existing flow. Future flight can widen scope if operator hits the case.

**§2. Pending-approval persistence: separate `pending_approvals` table** (flight director's call; cycle-2 architect ratified with caveats):
- New SQLite table (matching existing schema patterns including FK CASCADE and CHECK constraints — confirmed by cycle-2 architect via `db/schema.py:69, 88, 121`):
  ```
  pending_approvals (
    id TEXT PRIMARY KEY,                    -- uuid
    connector_account_id TEXT NOT NULL
      REFERENCES connector_accounts(id) ON DELETE CASCADE,
    peer_id TEXT NOT NULL,                  -- platform-id
    peer_name TEXT NOT NULL,                -- display name at receipt
    preview TEXT NOT NULL,                  -- first ~200 chars
    received_at TEXT NOT NULL,              -- iso8601
    status TEXT NOT NULL
      CHECK (status IN ('pending','approved','dismissed')),
    resolved_at TEXT                        -- iso8601, null while pending
  )
  ```
- **FK CASCADE rationale**: matches the precedent at `db/schema.py:69, 88, 121` (kb_items, knowledge_bases). If operator deletes a connector account, pending approvals for that account are useless; cascade removes them rather than orphaning.
- **CHECK constraint rationale**: enforces the three-state lifecycle (`pending → approved | dismissed`; terminal) at the storage layer; future maintainer can't add a fourth value silently.
- **Dedup at insert** (cycle-2 architect MEDIUM): the dispatcher's emit path at L2 MUST upsert rather than always-insert. If a `status='pending'` row already exists for `(connector_account_id, peer_id)`, UPDATE the preview + `received_at` rather than INSERT a new row. One pending row per (account, peer) while pending; approve/dismiss consumes it; subsequent DM from a now-non-allowlisted peer creates a fresh row. Dedup scope is status='pending' only; approved/dismissed rows remain historical and a new pending can co-exist with them.
- Codec gains a NEW projection path: `pending_approvals_to_ui_events(rows: list[PendingApproval]) -> list[dict]` separate from `messages_to_ui_events`. **Merge location locked: BACKEND** (cycle-2 architect MEDIUM). Mirrors existing replay pattern at `app.py:505, 631` — `_restore_session` queries both messages and pending_approvals, merges by timestamp, emits one ordered UI-event stream via WebSocket. Frontend `addMsg` receives a single ordered stream and dispatches on event type only.
- Rationale (best long-term, cycle-2 architect ratified): independent lifecycle from chat sessions; survives session reset; queryable by status; doesn't pollute the Message codec; future surfaces (e.g., Admin panel showing all pending approvals across accounts) inherit cleanly. Costs one migration + one table.
- Trade-off: more surface than reusing `session_metadata["audit"]` or threading audit lists through `messages_to_ui_events` callers — but those couple approval lifecycle to chat session lifecycle, which is the wrong coupling. Architect cycle-1 flagged this exactly.

**§3. Detach source-of-truth: agent-side `agents.connector_account_ids`** (flight director's call; cycle-2 architect ratified):
- Today, attach mutates `agents.connector_account_ids` via `PUT /api/agents/{name}` (cited by cycle-2 architect at `api.py:472`). That field is the source of truth for "which connector accounts is this agent attached to?"
- F9 DELETE endpoint shape: `DELETE /api/agents/{agent_name}/connector-accounts/{account_id}` — sub-resource path on agent. Mutates `agents.connector_account_ids` (removes the account_id from the list); releases the F2 account-keyed pool slot; audit-logged. Idempotent.
- UI surfaces (connector detail page button, grid badge) read derived state. **Confirmed by cycle-2 architect grep**: `account.config["attached_agents"]` does NOT exist in the codebase. The existing `GET /api/connector-accounts/{account_id}/attached-agents` (cycle-2 architect cited at `api.py:2573`) already derives from agent-side data — F9 detach UI reads the same source. No derived-cache update needed.
- Rationale (best long-term, cycle-2 architect ratified): single writer; matches existing attach semantics; no schema change for the source-of-truth field.
- Trade-off: detach endpoint URL is on the agent resource path even though the UI lives on the connector detail page. Operator-facing UX is unaffected (URL is internal); architectural cleanliness wins.

**§4. Pool release primitive**:
- F8 introduced the account-keyed pool primitive at `the_one/connectors/_pool.py`. Per cycle-1 architect, the public API has `agent_acquire(agent_name, account_id)` (line 748) and `account_acquire(account_id)` (line 830) but no public per-(agent, account) release.
- F9 L5 adds a public async release primitive. **Naming choice** (cycle-2 architect flagged): `release_agent_on_account(agent_name, account_id)` follows the verb-then-scope pattern, but `evict_agent_on_account(agent_name, account_id)` would mirror the existing `_evict_all_for_account` (line 365) family more tightly. L5 author picks consciously and documents in the leg log. Both are async; both call the existing private `_evict` (line 341).
- Tests: pool release after detach; subsequent attach re-acquires cleanly; idempotent (release-when-not-acquired is a no-op).

**§5. New top-level Chat UI event type `pending-approval`** (operator-confirmed):
- `static/js/areas/chat.js:addMsg` currently dispatches on 5 event types. F9 adds the 6th.
- Event shape:
  ```json
  {
    "type": "pending-approval",
    "approval_id": "<uuid>",
    "peer_name": "...",
    "peer_id": "...",
    "preview": "...",
    "received_at": "<iso8601>",
    "connector_account_id": "...",
    "status": "pending" | "approved" | "dismissed"
  }
  ```
- Render: interactive banner with peer name + preview + Approve button + Dismiss link. Click POSTs to `POST /api/connector-accounts/{account_id}/peer-approvals/{approval_id}/approve`.
- Trade-off: new event-type case in addMsg + new render method; matches the operator's choice for cleaner separation over system-type-with-discriminator.

**§6. Approval endpoint URL shape** (architect cycle-1 medium):
- `POST /api/connector-accounts/{account_id}/peer-approvals/{approval_id}/approve` — RESTful resource-create-then-action shape. Matches sibling routes' kebab-case noun convention (`pairing-code`, `attached-agents`).
- Body: empty (action is implicit in the URL path).
- Response: updated `pending_approval` record with `status: "approved"` + `resolved_at` set.

**§7. Audit-log `path` discriminator: DROPPED** (architect cycle-1 medium):
- The proposed addition of `path: "text-prefix" | "discord-native"` to audit entries was speculative for F11. F9 doesn't have a consumer; existing audit entries don't carry the key. F11 (audit-log inspector) introduces the discriminator when it ships its consumer.
- Trade-off: F11 will need to handle the absence-of-path case for legacy entries either way; F9 adding the key now offers no immediate value.

**§8. Studio-event-bus codification (F7 Rec #3(c) carry-forward)**:
- F7 cited n=3 inline-CustomEvent dispatch sites. Architect cycle-1 found 21 dispatch+listener references across `static/js/areas/studio/` (3 emit sites + N listener sites + indirect uses). L6 extracts a shared `studio-event-bus.js` module exposing `emit(name, detail)` and `on(name, handler)`. Refactors all sites to use it. The F9 detach event (`connector-agent-detached`) is the new emit site that triggers the codification.
- Trade-off: tiny abstraction over `document.dispatchEvent`; the value is in naming the bus + consolidating listeners.
- Convention citation in `agents.md` (no n-threshold framing per architect — cite F7 Rec #3(c) as the trigger).

**§9. `.tool-enable-switch` CSS default flip (F7 Rec #3(a) carry-forward)**:
- Per F7 debrief + architect cycle-1: `studio.css:750-761` has n=4 override rules; default is `position: absolute`. Flip default to `position: relative`; tile-corner consumers opt in via new `.tool-enable-switch--corner` modifier.
- Audit n=4 overrides; remove redundant ones; verify no visual regression via existing browser-test suite.

**§10. `provider-shape-portability` runbook extension (F8 carry-forward)**:
- Append one paragraph to `agents.md:134-151` covering operator-facing response when a legacy-row AssertionError surfaces in production.

### Prerequisites

- [x] F8 merged to main (PR #77 merged 2026-05-26; debrief commit `949142f`).
- [ ] **Create F9 branch**: `git checkout -b flight/09-pairing-resolution-and-detach` from current `main` (HEAD `949142f`) at L1 start.
- [ ] **Stray `docker-compose.yml` is now THIRD flight inheriting it** (F7 L12 → F8 → F9). Recommend operator stash/commit/restore BEFORE F9 starts. Otherwise F9 inherits and the Phase 2d commit must stage only F9 files (default).
- [ ] Pre-F9 baseline: 2669 passed (per F8 debrief). Re-pin at L1 implementation start via `make test-unit`.
- [ ] Discord test guild + ≥2 burner accounts available for HAT (one operator-already-paired; one UNpaired to drive the approval flow).
- [ ] Browser MCP available for L7 HAT (Chrome-driven walkthrough).

### Pre-Flight Checklist

- [x] All planning-time open questions resolved (10 of 10 OQs; 2 architectural calls locked by flight director and validated by cycle-2 architect; 4 OQs that the cycle-1 spec deferred are now locked at planning time).
- [x] Design decisions documented above (§1-§10).
- [ ] Prerequisites verified (operator handles docker-compose.yml; HAT environment ready; branch created at L1 start).
- [x] Validation approach defined (unit tests + browser tests + optional HAT).
- [x] Legs defined (see In-Flight § Legs).

**F7 `is_mention` hook interaction note**: F7's `is_mention` hook governs engagement inference at dispatcher step 11.5 (post-routing). F9's pending-approval emit lives at step 6 (pre-routing). The two are structurally upstream/downstream; no collision. Documented here so it isn't re-rediscovered at L2.

---

## In-Flight

### Technical Approach

F9 ships in **7 mandatory legs + 1 optional HAT leg**:

**L1 — Discord `resolve()` hook (DM-only NeedsPairing)** (`discord-resolve-hook`). Add `def resolve(self, account, envelope) -> OutboundOutcome` to `the_one/connectors/_discord.py`. Returns `NeedsPairing` when (a) the inbound is a DM (per `envelope.raw["is_dm"]` flag set by gateway) AND (b) the peer is not in `account.config["allowlist"]["peers"]`. Otherwise returns `Permit`. Tests: unit tests in `tests/test_connectors_discord.py` (or new file). No dispatcher change in L1.

**L2 — `pending_approvals` table + dispatcher emit** (`pending-approvals-storage-and-emit`). New table + migration in `the_one/db/schema.py`; new model in `the_one/db/models.py`; new repository helpers in `the_one/db/repositories.py` (insert, list-by-account, list-by-status, mark-approved, mark-dismissed). Extend `_inbound.py:410-449` NeedsPairing handler: when `_validate_pairing_prefix` returns `False` (no PAIR prefix or invalid), check if the cleaned message has NO `PAIR` prefix (i.e., this is a Discord-native candidate, not a failed pairing attempt); if so, INSERT a row into `pending_approvals` and emit a live-broadcast `pending-approval` event to any Chat UI session subscribed to this connector account. If PAIR prefix exists but invalid, fall through to existing Deny path. Tests: dispatcher emit; storage round-trip; existing PAIR-prefix tests pass unchanged.

**L3 — Approval API endpoint + allowlist mutation** (`approval-api-endpoint`). New endpoint `POST /api/connector-accounts/{account_id}/peer-approvals/{approval_id}/approve`. Flips `pending_approvals.status` from `pending` to `approved`; mutates `account.config["allowlist"]["peers"]` to add the peer (idempotent if already present); persists; audit-logged. Plus `POST /.../peer-approvals/{approval_id}/dismiss` for the secondary "Dismiss" link. Tests: endpoint unit tests; idempotency; concurrent-approve race (last-writer-wins).

**L4 — Chat UI `pending-approval` event type + render + click handler** (`chat-ui-pending-approval`). Extend `static/js/areas/chat.js:addMsg` with the 6th event-type case. Banner render (operator-style interactive UI; reuses existing CSS primitives where possible). Approve button click → fetch POST to L3 endpoint → re-render with `status: approved`. Dismiss link click → fetch POST to dismiss endpoint → fade-out. **Session-restore merge happens on the BACKEND** (per §2): `_restore_session` queries messages + pending_approvals, merges by timestamp, emits one ordered UI-event stream via WebSocket; the frontend `addMsg` receives a single ordered stream and dispatches on event type only. Tests: browser test for banner render + approve flow + dismiss flow + backend-ordered session-restore.

**L5 — Detach end-to-end** (`detach-end-to-end`). Backend: new endpoint `DELETE /api/agents/{agent_name}/connector-accounts/{account_id}` mutating `agents.connector_account_ids`. New public `pool.release_agent_on_account(agent_name, account_id)` in `_pool.py` (wraps existing `_evict`); endpoint calls it; idempotent; audit-logged. Frontend: `connector-account-editor.js` adds detach button per agent in the "Attached Agents" section (currently read-only at lines 19-20); inline confirm; on success emits `connector-agent-detached` CustomEvent; re-renders without page reload. `connectors-tab.js` adds per-account agent-count badge with click-through to detail page. Tests: API tests for DELETE; pool-release test; browser tests for detach + grid badge update.

**L6 — Studio-event-bus codification** (`studio-event-bus-codification`). F7 Rec #3(c) carry-forward. Extract `static/js/areas/studio/_studio_event_bus.js` exposing `emit(name, detail)` and `on(name, handler)`. Refactor the 4 emit sites (3 existing + L5's `connector-agent-detached`) AND the corresponding listener sites. Pre-count listeners at L6 design (architect noted 21 total dispatch+listener references across `static/js/areas/studio/`). Update `agents.md` with `studio-event-bus` convention citation (cite F7 Rec #3(c) as the trigger). Tests: existing browser tests pass unchanged.

**L7 — Small-housekeeping** (`small-housekeeping`). Two-axis fold-in leg:
- F7 Rec #3(a): `.tool-enable-switch` CSS default flip + n=4 override consolidation + `.tool-enable-switch--corner` opt-in modifier.
- F8 action item: extend `provider-shape-portability` convention text at `agents.md:134-151` with operator runbook paragraph.
Tests: existing CSS-touch browser tests must continue to pass.

**L8 (optional, recommended) — HAT for pairing + detach** (`hat-pairing-and-detach`). Guided walkthrough covering 8 steps (6 primary + 2 fallback):
1. DM bot from unpaired burner account.
2. Operator sees pending-approval banner in Chat UI.
3. Operator clicks Approve.
4. Burner sends follow-up DM; agent engages normally.
5. Operator navigates to connector detail page, clicks Detach on an attached agent.
6. Verify: detach badge updates; subsequent DM mentioning detached agent does not route.
7. From a different unpaired account: send `PAIR <code> hello` with correct code.
8. Verify: peer added via text-prefix path; audit-log shows path.

Inline-hotfix-during-HAT discipline (F7 L12 precedent). Operator-judged satisfaction gates flight-land.

### Checkpoints

- [x] **L1**: Discord plugin has `def resolve()` returning DM-only NeedsPairing; unit tests pass.
- [x] **L2**: `pending_approvals` table exists; dispatcher emits pending-approval event on unknown-DM-without-PAIR-prefix; existing pairing tests pass unchanged.
- [x] **L3**: approve + dismiss endpoints exist; allowlist mutation persists; idempotent.
- [x] **L4**: Chat UI 6th event type renders banner; approve flow works; dismiss flow works; session-restore merges by timestamp.
- [x] **L5**: DELETE endpoint + pool release + detail-page button + grid badge work end-to-end.
- [x] **L6**: studio-event-bus shared module; 4+ emit sites + N listener sites refactored; existing browser tests pass; convention codified.
- [x] **L7**: CSS default flipped; n=4 overrides consolidated; agents.md runbook paragraph added.
- [ ] **(optional) L8**: HAT 8-step walkthrough; any surfaced hotfixes landed inline.

### Adaptation Criteria

**Divert if**:
- L1 reveals the Discord plugin's `envelope.raw["is_dm"]` flag isn't reliably set (the spec assumes it is per recon; verify at L1 implementation start).
- L2's migration breaks F8's invariants (the `Message.__post_init__` assert from F8 L2 — verify the new `pending_approvals` codec path doesn't construct Message with non-str content).
- HAT (L8) surfaces a structural bug >80 LOC across multiple files — hotfix inline if bounded, divert to new leg if not.

**Acceptable variations**:
- L6 (event-bus) lands before L5 (detach) if the refactor surface is reviewable in isolation and L5 wants to use the shared module from the start.
- L7's two axes can land in either order; CSS first if visual regression is the concern, agents.md first if convention rationale needs early commit.
- The L4 click-handler may need to handle a race where the operator clicks Approve simultaneously on two sessions for the same pending-approval; default: last-writer-wins; idempotent on the backend; UI shows "approved" status on both sessions on next render.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses.

- [x] `discord-resolve-hook` — DM-only NeedsPairing in Discord plugin's new `resolve()` method.
- [x] `pending-approvals-storage-and-emit` — new table + migration + repo helpers + dispatcher emit.
- [x] `approval-api-endpoint` — approve + dismiss endpoints; allowlist mutation; audit.
- [x] `chat-ui-pending-approval` — Chat UI 6th event type + interactive banner + click handlers + session-restore merge.
- [x] `detach-end-to-end` — DELETE endpoint + pool release + detail-page detach button + grid badge.
- [x] `studio-event-bus-codification` — F7 Rec #3(c) carry-forward; extract shared module + refactor sites.
- [x] `small-housekeeping` — F7 Rec #3(a) CSS default flip + F8 agents.md runbook extension.
- [ ] `hat-pairing-and-detach` *(optional)* — guided UAT (8-step scenario + fallback).

---

## Post-Flight

### Completion Checklist

- [ ] All mandatory legs (L1-L7) completed; optional L8 HAT completed or explicitly skipped
- [ ] Mission criteria #8 (pairing) and #9 (detach) checked off in `mission.md`
- [ ] Criterion-coverage artifact updated for #8 + #9 (status → `closed-by-F9`; evidence pointers)
- [ ] Test suite baseline recorded vs F8's 2669 / 197.27s
- [ ] `agents.md` updated with: (a) `studio-event-bus` convention citation (L6); (b) extended `provider-shape-portability` convention with operator runbook (L7). NO new `dual-flow pairing` convention per cycle-1 architect (dropped).
- [ ] Flight-debrief written, including:
  - Whether dual-flow UX felt right at HAT
  - Discord `resolve()` hook scope adequacy (DM-only sufficient or do we need guild-mention scope?)
  - Architect cycle-2 decisions on persistence + detach source-of-truth — held up or surprised?
  - Test-metric delta vs F8 baseline 2669

### Verification

- **Tests**: `make test-unit` passes; new endpoint tests pass; browser tests for banner + detach pass; codec tests for `pending_approvals` projection pass; F8 baseline 2669 matched or improved.
- **End-to-end**: HAT (if L8 ran) passes 8-step scenario; operator judges shippable.
- **Carry-forwards**: F7 Rec #3(a) n=4 overrides consolidated; F7 Rec #3(c) event-bus module + listeners refactored; F8 agents.md runbook paragraph present.
- **Behavior preservation**: existing PAIR-prefix tests pass unchanged.

---

## Design-Review Cycle Log

**Cycle 1 (2026-05-27, Architect, Opus model)**: needs rework. Three HIGH-severity findings:
- Discord plugin has no `resolve()` hook — falls through to `_default_permit`; F9's pending-approval branch was unreachable. **Resolution**: promoted from L1 OQ to a Design Decision §1; locked DM-only scope; L1 is the new-hook leg.
- `messages_to_ui_events` is Message-derived; pending-approval is not a Message. **Resolution**: locked separate `pending_approvals` table + dedicated codec projection path; the message codec is unchanged.
- No existing attach endpoint to mirror; pool API lacks per-(agent, account) public release. **Resolution**: F9 DELETE endpoint lives on agent-side resource path (`DELETE /api/agents/{name}/connector-accounts/{account_id}`); new public `pool.release_agent_on_account` primitive added in L5.

Plus mediums:
- Approval URL pluralization → fixed to `peer-approvals/{approval_id}/approve` per RESTful convention.
- "n=4 threshold" framing → dropped; cite F7 Rec #3(c) as trigger.
- Audit `path` discriminator → dropped (speculative for F11).
- L3 four-seam concern → resolved by splitting into L2/L3/L5 (storage/endpoint/detach respectively).

Plus lows:
- Branch creation added to prereqs.
- Stray `docker-compose.yml` stronger callout (now F7→F8→F9 third inherit).
- F7 `is_mention` interaction documented as upstream-of-F9-emit (no collision).

Operator decisions during rework:
- Discord resolve scope: DM-only.
- Convention codification: dropped per architect (n=1 by definition).
- Persistence shape + detach source-of-truth: operator deferred to architect; flight director picks (new table + agent-side source) — cycle-2 architect validates.

**Cycle 2 (2026-05-27, Architect, Opus model)**: approve with changes. Both architectural picks **ratified**:
- Persistence shape (new `pending_approvals` table): ratified with three caveats (now folded into §2): FK CASCADE on `connector_account_id`; CHECK constraint on `status`; dedup at insert (UPDATE pending row in place rather than INSERT new when one exists for `(account, peer)` with status='pending').
- Detach source (agent-side `agents.connector_account_ids`): ratified. Confirmed by grep: no `account.config["attached_agents"]` field exists; existing `GET /api/connector-accounts/{id}/attached-agents` at `api.py:2573` already derives from agent-side data.

Cycle-2 MEDIUM fixes folded inline:
- §2: FK CASCADE + CHECK constraint + dedup-at-insert clauses added.
- §2/L4: session-restore merge location LOCKED to backend (mirrors `app.py:505, 631`).
- §1: type name corrected `OutboundOutcome` → `ResolveOutcome` (per `base.py:252`).
- §3: defensive language about non-existent `attached_agents` field removed (grep confirmed absent).
- §4: pool primitive naming choice flagged for L5 author (`release_agent_on_account` vs `evict_agent_on_account`).

Cycle-2 state-machine reachability findings:
- Lifecycle `pending → approved | dismissed` is terminal; no re-pending. Adequate for F9 scope.
- Post-removal-from-allowlist re-pending case structurally correct: old row stays `approved`; new DM creates fresh row.
- Approval-while-detach race surfaces as expected behavior (peer added to allowlist; no agent left to engage). Non-blocking; noted in L3/L5 design as expected.

Cycle-2 OQ audit: all 10 OQs locked at flight planning; no further deferrals to L1.

**Leg approved for operator Phase 6 walk-through.** No cycle 3 needed.
