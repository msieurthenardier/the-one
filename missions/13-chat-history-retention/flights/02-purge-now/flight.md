# Flight: Purge Now

**Status**: completed
**Mission**: [Chat History Retention](../../mission.md)

## Contributing to Criteria
- [x] A "Purge now" control deletes all of that agent's conversations, but only after the
  operator explicitly confirms the destructive action.
- [x] Purge (both manual and automated) removes entire conversations — including
  connector-originated ones — and never affects another agent's conversations. *(F2 covers the
  **manual** half; the automated daily sweep is Flight 3.)*

---

## Pre-Flight

### Objective

Add an agent-wide "delete all conversations for this agent" capability: a
`ChatSessionRepository.delete_all_for_agent(agent_name)` repository primitive, a
`DELETE /agents/{name}/chat/sessions` API endpoint, and a "Purge now" control in the General-tab
Danger Zone that deletes the agent's entire chat history (interactive **and** connector-originated)
only after an explicit two-step confirm. No retention/scheduler logic (that is Flight 3). While in
the two frontend files this flight already edits, also land two carried-forward shared-surface
items from the F1 debrief: the DD6 inline comment in `studio.js` and the `system_prompt` textarea
accessibility-label fix in `general-tab.js`.

### Open Questions

- [x] **Endpoint key — name or id?** → Resolved: **agent name**. There is no agent id —
  `agents.name` is the primary key (`db/schema.py:47–48`), `chat_sessions.agent_name` keys on it,
  and every existing agent endpoint is `/agents/{name}`. See DD1.
- [x] **Rename safety of a name-keyed delete** → Resolved: rename is already handled. The existing
  `SQLiteAgentStore.rename()` cascade re-points all of an agent's `chat_sessions` rows (interactive
  + connector) to the new name in the same transaction (`db/repositories.py:219–222`), so the
  name-keyed purge always targets the renamed agent's sessions. Locked by a rename-then-purge
  composition test in Leg 1. See DD1.
- [x] **Connector-originated conversations swept?** → Resolved: yes. Connector sessions are
  `chat_sessions` rows with `agent_name` set (`connectors/_session.py:181–195`), so a single
  `DELETE FROM chat_sessions WHERE agent_name = ?` removes them too (criterion 5). See DD2.

No open questions remain for this flight.

### Design Decisions

**DD1 — Endpoint keyed by agent name; delete-by-`agent_name` + count; no existence-404**: The
endpoint is `DELETE /agents/{name}/chat/sessions`. It runs
`DELETE FROM chat_sessions WHERE agent_name = ?` and returns `{"status": "ok", "deleted": N}`. It
does **not** verify the agent exists first.
- Rationale: agents are name-keyed (no id column; `schema.py:47`), consistent with every other
  agent endpoint. Skipping an existence check makes the operation idempotent and also clears
  sessions orphaned by a prior agent deletion (sessions survive agent deletion since v5 dropped the
  FK). The button only surfaces for existing agents, so the bad-name case is not a real UI path.
- Rename safety: name-keying is safe because `rename()` already re-points `chat_sessions.agent_name`
  in the same transaction (the `UPDATE chat_sessions SET agent_name = ? WHERE agent_name = ?` at
  `repositories.py:222`); an immutable id would be rename-proof too but does not exist and would need
  a new column + migration for zero added safety over the existing cascade.
- Trade-off: a name-keyed delete trusts the rename cascade to keep `agent_name` consistent — locked
  by an explicit rename-then-purge composition test (Leg 1).

**DD2 — No schema change; row deletion only**: Unlike F1, this flight adds no DDL and needs no
migration.
- Rationale: purge is a `DELETE` of existing rows. The `agent_name`-scoped delete sweeps
  connector-originated conversations (they are `chat_sessions` rows with `agent_name` set,
  `connectors/_session.py:181–195`) and, because it filters on `agent_name`, never touches another
  agent's rows (criterion 5). (`SCHEMA_V1` still defines the `chat_sessions.agent_name` FK, but the
  v5 migration drops it, so on any running DB — version ≥ 5 — the delete neither cascades nor is
  blocked, and sessions already survive agent deletion.)
- Trade-off: none — no schema surface touched.

**DD2a — In-memory `_sessions` are NOT evicted on purge (accepted boundary)**: The endpoint deletes
DB rows only; it does not reach into the app-layer live-session registry (`_sessions`, `app.py`).
- Consequence: if an operator has a Chat tab open on a session whose history is purged from another
  tab, that in-memory `Session` keeps working until the idle reaper evicts it (no subscriber + TTL),
  and a turn taken in that window will **not persist** — `_save_session_to_db` catches the missing
  row, logs a WARNING, and returns without persisting (`app.py:847–849`). The next inbound to a
  purged connector channel simply
  creates a fresh row (`find_most_recent_by_external_key` → no match → new session), restarting that
  channel's thread context — consistent with the mission's "superseded rows age out" stance.
- Rationale: "Purge now" is a deliberate operator wipe; evicting live `_sessions` would force the
  endpoint to cross into app-layer state (a structural boundary crossing) for a niche
  purging-while-actively-chatting case. Accept-and-document is the lighter discipline (project
  precedent). Recorded here so the boundary is explicit, not discovered later.
- Trade-off: the niche concurrent-chat case loses an unpersisted turn (with a logged WARNING, not
  silently). If judged
  unacceptable, the endpoint would additionally evict matching `_sessions` entries — left out of
  F2 scope deliberately; revisit in Flight 4 if the UX warrants.

**DD3 — Reuse the `App.confirmDelete` arm-then-fire pattern for "Purge now"**: The button uses the
canonical two-step destructive-confirm helper (`confirm.js:38`), exactly as the Danger-Zone Delete
Agent button does (`studio.js:1619`), with a distinct `confirmLabel: 'Confirm Purge?'`.
`handlePurgeHistory` mirrors `handleDeleteEditor` (`studio.js:1616–1643`) but **keeps the agent
selected** (only its history is removed, not the agent): it does NOT call
`selectAgent`/`renderEmptyEditor` and does NOT need `loadAll()` (the agent list is unchanged) — it
re-renders/flashes the deleted count in place. The button HTML MUST include a
`<span data-confirm-title>Purge now</span>` child, because `App.confirmDelete` swaps the label via
the `[data-confirm-title]` selector (`confirm.js:44`); without it the first click silently arms with
no visible label change and the behavior test's arm-not-fire step would be unobservable.
- Rationale: criterion 3 requires an explicit confirm; the arm-then-fire helper is the established,
  tested pattern with three existing consumers. Reusing it gives the confirm step for free.
- Trade-off: two destructive buttons now sit in the Danger Zone (Delete Agent + Purge now) — they
  must be visually and label-distinct so an operator can't confuse "wipe history" with "delete the
  agent." Distinct button text + confirm labels handle this.

**DD4 — Coverage split: deterministic invariants in unit tests, rendered flow in the behavior
test**: The connector-row sweep, cross-agent isolation, the returned count, and the
rename-then-purge composition are asserted in repo/API **unit tests** (deterministic, fast). The
rendered **confirm → history-gone** UI flow (with one connector-seeded session) is the **behavior
test** `agent-purge-now-clears-history`.
- Rationale: the cross-agent matrix and rename composition are pure data invariants best pinned by
  unit tests; the behavior test's unique value is the live two-step-confirm UX and the user-visible
  "history is gone" observation. Avoids duplicating the heavy matrix in a flaky live run.

**DD5 — Behavior-test apparatus, both axes (premise-audited)**: The confirm→gone flow is driven
through the Studio UI.
- **Act path**: seed sessions via `POST /api/chat/sessions` (`api.py:3624`, validates
  `ChatSession` — accepts connector fields `platform`/`connector_id`/`channel_id`, so a
  connector-keyed session is seedable by curl); drive the Danger-Zone "Purge now" button + confirm
  via chrome-devtools.
- **Observe path**: `GET /api/chat/sessions?agent_name=X` (`api.py:3597`) returns the agent's
  sessions — count drops to 0 after purge (http apparatus); the Chat-area session list for the
  agent renders empty (browser). Both read paths exist today; no test-only seam is introduced.

**DD6 — Bundle the two shared-surface pull-ins into Leg 2**: While editing `studio.js` and
`general-tab.js` for the purge button, also land (a) the F1 DD6 inline comment at the
`chat_history_retention_days` `collectFormData` branch (`studio.js:1930–1932`) and (b) an
accessibility label for the `system_prompt` textarea (`general-tab.js:113`, currently no
`<label for>`/`id` — WCAG 1.3.1/4.1.2).
- Rationale: both are tiny, both live in the two files Leg 2 already touches — the "shared-surface
  leg" guidance. Bundling avoids a separate flight/leg for two one-line changes.
- a11y approach: add `id="studio-system-prompt"` to the textarea and an associated `<label
  for="studio-system-prompt">System Prompt</label>` (a real label, not `aria-label`), consistent
  with the `field-row`/`label for` idiom the Behavior inputs use.
- Trade-off: mixes housekeeping into a feature leg; kept honest by separate, explicitly-labelled
  acceptance criteria. The `aiosqlite` teardown warning and the `agents.md` convention docs do
  **not** share this flight's surface and are deliberately excluded (they remain for the
  end-of-mission maintenance flight).

### Prerequisites
- [x] Project initialized; Mission 13 active; Flight 1 (`chat_history_retention_days`) landed and
  merged to `main`.
- [x] `ChatSessionRepository.delete(session_id)` (per-session) exists (`repositories.py:1030`); no
  agent-wide delete primitive exists yet (this flight adds it).
- [ ] the-one dev environment available (Docker + Makefile, Python 3.11+, SQLite).
- [ ] **Live behavior-test execution prerequisites** (this flight names two behavior tests as
  acceptance gates — the new `agent-purge-now-clears-history` and the deferred F1
  `agent-retention-setting-roundtrip` entry gate). Per Pre-Flight Rigor, both halves must hold at
  execution and be probed at planning:
  - **Apparatus-audited environment**: running rebuilt instance on `http://localhost:8484`; live
    Chrome MCP session; a seedable agent + the `mock` provider; curl for seeding/observation.
  - **Crew-execution capability**: a session with multi-turn sub-agent continuation (SendMessage)
    for the live Executor + Validator. Without it `/behavior-test` degrades to re-spawn-per-step.
    **Execute/accept this flight in a continuation-capable session** so the gates are reachable —
    this is the explicit lesson carried from the F1 deferral.

### Pre-Flight Checklist
- [x] All open questions resolved
- [x] Design decisions documented
- [x] Prerequisites verified (code surfaces; behavior-test execution prerequisites recorded)
- [x] Validation approach defined (unit + behavior test + browser test)
- [x] Legs defined

---

## In-Flight

### Technical Approach

Two legs. No migration.

**Leg 1 — `agent-purge-backend`**: Add `ChatSessionRepository.delete_all_for_agent(agent_name:
str) -> int` near the per-session `delete` (`repositories.py:1030`), capturing the cursor via the
house `async with self.conn.execute(...) as cur:` pattern and reading `count = cur.rowcount` —
`async with self.conn.execute("DELETE FROM chat_sessions WHERE agent_name = ?", (agent_name,)) as
cur:` then `count = cur.rowcount`, then `await self.conn.commit()`; return `count`. (`rowcount` is
new to this repo but valid — aiosqlite/sqlite3 populates it for a DELETE; the per-session `delete`
at `:1030` doesn't capture the cursor, so this is a small, deliberate extension.) Add
`DELETE /agents/{name}/chat/sessions` (`api.py`, near the chat-session routes at `:3649`) returning
`{"status": "ok", "deleted": N}`. Tests: repo method deletes all of an agent's sessions including a
connector-keyed row, leaves another agent's sessions intact, returns the correct count, and is a
no-op (count 0) for an agent with no sessions; a **rename-then-purge composition** test (rename an
agent with interactive + connector sessions, purge by the new name, assert all gone and a second
agent untouched); API test for the endpoint shape + count. Run `make rebuild` then the touched unit
suites; `ruff` clean.

**Leg 2 — `purge-now-button`**: This wires through **three** frontend files (the callback chain is
`studio.js` options bag → `agent-editor.js` forward → `general-tab.js` render):
1. `general-tab.js` — add a "Purge now" button to the Danger-Zone section (`:128–139`),
   visually/label-distinct from Delete Agent, with a `<span data-confirm-title>Purge now</span>`
   child (DD3), and wire its click to `callbacks.onPurge` alongside the existing `.delete-btn`
   wiring (`:147–149`).
2. `agent-editor.js` — forward `onPurge: callbacks.onPurge` in the `renderGeneralTab(...)` call
   (`:154–157`, which currently threads only `onTestProvider` + `onDelete`). **Without this the
   callback never reaches `general-tab.js`** — this is the bridge, not `studio.js:1505`.
3. `studio.js` — add `handlePurgeHistory` mirroring `handleDeleteEditor` (`:1616–1643`):
   `App.confirmDelete(purgeBtn, fn, { confirmLabel: 'Confirm Purge?' })`,
   `fetch('/api/agents/' + encodeURIComponent(name) + '/chat/sessions', {method:'DELETE'})`, flash
   the deleted count, keep the agent selected (no `loadAll()`/`selectAgent`); register
   `onPurge: handlePurgeHistory` in the `renderAgentEditor` options bag (near `onDelete` at `:1505`).

**Shared-surface pull-ins (DD6)**: add the DD6 inline comment at `studio.js:1930` and the
`system_prompt` `<label for="studio-system-prompt">` + matching textarea `id` in
`general-tab.js:113`. Browser test: the Purge-now button renders in the Danger Zone, is label-distinct
from Delete Agent, and carries the `data-confirm-title` span (placement/DOM check — the full two-step
confirm→gone flow is the behavior test's job, not duplicated here). Run `make rebuild`; browser suite
via the `-m browser` marker (`pyproject.toml:76` addopts deselects `browser` by default — a bare
`pytest tests/browser/...` runs zero tests).

### Checkpoints
- [x] `delete_all_for_agent` deletes interactive + connector sessions for the target agent, returns
  the count, leaves other agents intact; rename-then-purge composition holds.
- [x] `DELETE /agents/{name}/chat/sessions` returns `{status, deleted:N}`; verified against the live
  DB.
- [x] "Purge now" renders in the Danger Zone, distinct from Delete Agent, and requires a two-step
  confirm before any deletion.
- [x] DD6 comment + `system_prompt` label landed; `ruff` clean; browser suite green (no regression).
- [x] Behavior test `agent-purge-now-clears-history` passes (5/6, 1 inconclusive spec-gap, 0 fail);
  the deferred `agent-retention-setting-roundtrip` entry gate passes (6/6, after the error-rendering
  fix).

### Adaptation Criteria

**Divert if**:
- The chat-session API routes or `ChatSessionRepository` have been restructured such that the cited
  anchors (`api.py:3649`, `repositories.py:1030`) no longer hold — re-locate before editing.
- The rename cascade (`repositories.py:219–222`) has changed shape — re-verify name-keying safety
  before relying on it.

**Acceptable variations**:
- Exact "Purge now" button label / confirm wording and its placement within the Danger Zone
  (cosmetic; Flight 4 owns UX polish).
- Endpoint path spelling (`/agents/{name}/chat/sessions` vs `/agents/{name}/sessions`) if a clearer
  convention is found — keep it agent-name-scoped and sessions-only (never the agent itself).

### Legs

> **Note:** Tentative; legs are created one at a time as the flight progresses.

- [x] `agent-purge-backend` - `delete_all_for_agent` repo method + `DELETE /agents/{name}/chat/sessions`
  endpoint + tests (connector sweep, cross-agent isolation, count, rename-then-purge composition).
- [x] `purge-now-button` - Danger-Zone "Purge now" button + `handlePurgeHistory` confirm-then-fire
  wiring across three files (`general-tab.js`, `agent-editor.js` forward, `studio.js`) + browser
  test; plus the DD6 comment and `system_prompt` a11y label (shared-surface).

---

## Post-Flight

### Completion Checklist
- [x] Both legs completed
- [x] Purge verified against the live DB (sessions actually gone, including a connector-keyed row —
  confirmed in the behavior test's 2→0 sweep and again during throwaway-agent cleanup via the live endpoint)
- [x] `make test` green (unit + browser): 191 repo + ChatSessionAPI + 2964 broad unit; 477 browser
  (+ the new purge + retention-error tests); `ruff check` + `ruff format --check` clean
- [x] Behavior test `agent-purge-now-clears-history` passes (5/6, 1 inconclusive spec-gap, 0 fail)
- [x] Entry gate: `agent-retention-setting-roundtrip` (F1 deferred) passes (6/6, after the error-rendering fix)
- [x] Code + artifacts committed together

### Verification

- **Unit**: `delete_all_for_agent` (connector sweep, cross-agent isolation, count, empty no-op,
  rename-then-purge) + the API endpoint shape — `make test-unit`.
- **Behavior test (new)**: `/behavior-test agent-purge-now-clears-history` — seed interactive +
  connector sessions, drive the two-step Purge-now confirm, observe the agent's history gone (and a
  second agent's intact) via `GET /chat/sessions?agent_name=…` + the Chat session list.
  Spec: [tests/behavior/agent-purge-now-clears-history.md](../../../../../tests/behavior/agent-purge-now-clears-history.md).
- **Behavior test (entry gate)**: `/behavior-test agent-retention-setting-roundtrip` — the F1
  deferred Witnessed test, run here to close the live-acceptance gap before purge UX layers on top.
- **Browser test**: Purge-now button renders in the Danger Zone and is two-step.
