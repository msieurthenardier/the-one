# Behavior Test: Agent Purge Now Clears History

**Slug**: `agent-purge-now-clears-history`
**Status**: active
**Created**: 2026-06-05
**Last Run**: 2026-06-05-20-16-35 (partial: 5 pass / 1 inconclusive — the inconclusive is a list-endpoint observability gap, not a behavior fault; see `runs/`)

## Intent

Verifies that the General-tab "Purge now" control deletes all of a target agent's conversations —
both interactive and connector-originated — but only after an explicit two-step confirm, and that
another agent's conversations are untouched. This is a real-environment flow: the rendered
arm-then-fire confirm UX, and the user-visible "history is gone" state observed through both the
HTTP read path and the Chat session list. Unit tests cover the deterministic data invariants
(connector sweep, cross-agent isolation, count, rename-then-purge); this test covers what only a
live run can: that the operator-facing control actually requires the confirm and that the deletion
is observable through the surfaces an operator uses.

## Preconditions

- the-one is running host-native on `http://localhost:8484`, on the Flight-2 branch
  (`make restart` after the F2 edits — a restart picks up source edits). Verified by an active probe.
- Two agents exist (the dev `mock` provider suffices): a **target** agent to purge and a
  **bystander** agent that must remain untouched. Their names are supplied at run time.
- Operator has the Chrome MCP browser session attached to that URL.
- (Per the flight's Pre-Flight prerequisites) the run executes in a session with SendMessage
  continuation for the live Executor + Validator; otherwise `/behavior-test` degrades to
  re-spawn-per-step.

## Observables Required

- browser (Studio Danger-Zone control state + the Chat-area session list — via chrome-devtools MCP)
- http (`GET /api/chat/sessions?agent_name=…` count; `POST /api/chat/sessions` seeding — via curl
  through Bash)

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | Via curl, seed the **target** agent with two sessions: one plain interactive session (`POST /api/chat/sessions` with `{agent_name, title}`) and one connector-keyed session (same endpoint with `platform`, `connector_id`, `channel_id` set — the POST returns 201 with an `id`, confirming the connector-keyed row was created). Seed the **bystander** agent with one session. | `GET /api/chat/sessions?agent_name={target}` returns **2** sessions; `GET /api/chat/sessions?agent_name={bystander}` returns **1**. (Setup + assert.) *Note: the list endpoint is a summary projection and does NOT echo `platform`/`connector_id`/`channel_id`; the connector row is confirmed created via its 201 POST `id`, and that it is swept is proven by the 2→0 drop in Step 4. The field-level connector round-trip + sweep is pinned deterministically by Leg 1 unit tests.* |
| 2 | Open `http://localhost:8484/`, go to Agent Studio, open the **target** agent's General tab, scroll to the Danger Zone. | A "Purge now" control is visible in the Danger Zone, visually and textually **distinct** from the "Delete Agent" button (it is about history, not the agent). |
| 3 | Click "Purge now" **once**. Do not click again. | The control **arms**: its visible label changes to the confirm prompt (e.g. "Confirm Purge?") — assert the rendered button text changed (DOM), AND that it did NOT delete: `GET /api/chat/sessions?agent_name={target}` still returns **2**. Both must hold. |
| 4 | Click the armed control a **second** time to confirm. | A success indication appears (e.g. a flash, optionally citing a deleted count). `GET /api/chat/sessions?agent_name={target}` now returns **0** — both the interactive AND the connector-keyed session are gone. |
| 5 | Check the bystander. | `GET /api/chat/sessions?agent_name={bystander}` still returns **1** — the purge did not affect another agent (criterion 5). |
| 6 | Navigate to the Chat area (full reload). Inspect the session list. | The target agent's purged sessions are **absent** from the Chat-area session list, consistent with the HTTP observation. *Note: the Chat sidebar is a flat cross-agent session list (the agent selector only routes new chats — there is no per-agent filtered list / per-agent empty-state). Assert by the **absence** of the purged session ids/titles for the target, not a global empty-state. A transient post-purge staleness may briefly appear via a WebSocket `session_list` push from un-evicted in-memory state (the DD2a accepted boundary) — verify on a clean reload; the REST `GET ?agent_name={target}=0` is authoritative.* |

**Notes:**
- Step 3 is the load-bearing confirm-gate check: a single click must NOT delete. If the first click
  deletes, the test fails regardless of step 4.
- The connector-keyed seed in step 1 is what proves the sweep covers connector-originated
  conversations (criterion 5) through the UI path, not only the unit test.

## Out of Scope

- The automated daily purge (Mission 13 Flight 3) and its scheduler.
- The full cross-agent isolation matrix and rename-then-purge composition — covered deterministically
  by Flight 2 Leg 1 unit tests.
- Retention-setting behavior — covered by `agent-retention-setting-roundtrip`.
- Purge-now UX polish (button placement, confirm wording, empty-state copy) — Mission 13 Flight 4
  (Alignment).

## Variants (optional)

None.
