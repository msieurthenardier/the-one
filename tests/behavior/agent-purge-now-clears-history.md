# Behavior Test: Agent Purge Now Clears History

**Slug**: `agent-purge-now-clears-history`
**Status**: active
**Created**: 2026-06-05
**Last Run**: 2026-06-05-20-16-35 (partial: 5 pass / 1 inconclusive — the inconclusive is a list-endpoint observability gap, not a behavior fault; see `runs/`)
**Updated**: 2026-10-05 (M25 F4 leg 8: step 6 reads the Chats list, a cross-agent history grouped by recency)

## Intent

Verifies that the General-tab "Purge now" control deletes all of a target agent's conversations
but only after an explicit two-step confirm, and that another agent's conversations are untouched.
This is a real-environment flow: the rendered arm-then-fire confirm UX, and the user-visible
"history is gone" state observed through both the HTTP read path and the Chats list. Unit
tests cover the deterministic data invariants (cross-agent isolation, count, rename-then-purge);
this test covers what only a live run can: that the operator-facing control actually requires the
confirm and that the deletion is observable through the surfaces an operator uses.

## Preconditions

- the-one is running host-native on a **non-default port with a scratch data directory**
  (never the operator's default `:8484` instance), on the Flight-2 branch (`make restart`
  after the F2 edits, against that same instance — a restart picks up source edits).
  Verified by an active probe. **Note**: this spec's Steps literally write
  `http://localhost:8484` — treat that as a placeholder for this instance's actual base
  URL (stated at run time), never as a literal instruction to target port 8484.
- Two agents exist (the dev `mock` provider suffices): a **target** agent to purge and a
  **bystander** agent that must remain untouched. Their names are supplied at run time.
- Operator has the Chrome MCP browser session attached to that URL, reached via
  CLAUDE.md's "Behavior-test credential convention" (a handoff-authenticated navigation
  establishing a session cookie, not a bare `goto`).
- **Credential**: this instance is gated (Mission 20 Flight 1). Read the long-lived
  credential from the instance's data directory per the convention above; attach it as
  `Authorization: Bearer <credential>` for the `curl` steps, and mint a fresh handoff for
  each browser navigation to the app root (a handoff is single-use).
- (Per the flight's Pre-Flight prerequisites) the run executes in a session with SendMessage
  continuation for the live Executor + Validator; otherwise `/behavior-test` degrades to
  re-spawn-per-step.

## Observables Required

- browser (the agent editor's Danger-Zone control state + the Chats list `chats-list` — via chrome-devtools MCP)
- http (`GET /api/chat/sessions?agent_name=…` count; `POST /api/chat/sessions` seeding — via curl
  through Bash)

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | Via curl, seed the **target** agent with two plain interactive sessions (`POST /api/chat/sessions` with `{agent_name, title}`, using distinct titles — each POST returns 201 with an `id`). Seed the **bystander** agent with one session. | `GET /api/chat/sessions?agent_name={target}` returns **2** sessions; `GET /api/chat/sessions?agent_name={bystander}` returns **1**. (Setup + assert.) |
| 2 | Open `http://localhost:8484/`, click the rail's "Agents" link, open the **target** agent's General tab, scroll to the Danger Zone. | A "Purge now" control is visible in the Danger Zone, visually and textually **distinct** from the "Delete agent" button (it is about history, not the agent). |
| 3 | Click "Purge now" **once**. Do not click again. | The control **arms**: its visible label changes to the confirm prompt (e.g. "Confirm Purge?") — assert the rendered button text changed (DOM), AND that it did NOT delete: `GET /api/chat/sessions?agent_name={target}` still returns **2**. Both must hold. |
| 4 | Click the armed control a **second** time to confirm. | A success indication appears (e.g. a flash, optionally citing a deleted count). `GET /api/chat/sessions?agent_name={target}` now returns **0** — both target sessions are gone. |
| 5 | Check the bystander. | `GET /api/chat/sessions?agent_name={bystander}` still returns **1** — the purge did not affect another agent (criterion 5). |
| 6 | Navigate to the Chats destination (`#chats`, full reload). Inspect the Chats list (`chats-list`). | The target agent's purged sessions are **absent** from the Chats list: no row (`chat-row`) carries a purged session's `data-id`, and no row shows a purged title with the target agent on its second line. The bystander's session row (its `data-id`) is still listed. This matches the HTTP observation. *Note: the Chats list is one cross-agent history grouped by recency (Today, Yesterday, Last 7 days, Last 30 days, Older), with a New chat button that opens the agent picker; there is no per-agent filtered list and no per-agent empty state. Assert by the **absence** of the purged session ids/titles for the target, not a global empty state. Since M25 F4 the agent editor's Purge now also invalidates the client's `sessions` store. A transient post-purge staleness may briefly appear via a WebSocket `session_list` push from un-evicted in-memory state (the DD2a accepted boundary) — verify on a clean reload; the REST `GET ?agent_name={target}=0` is authoritative.* |

**Notes:**
- Step 3 is the load-bearing confirm-gate check: a single click must NOT delete. If the first click
  deletes, the test fails regardless of step 4.
- The two seeded target sessions in step 1 prove the purge clears every conversation for the
  agent in one action (criterion 5) through the UI path, not just a single row.

## Out of Scope

- The automated daily purge (Mission 13 Flight 3) and its scheduler.
- The full cross-agent isolation matrix and rename-then-purge composition — covered deterministically
  by Flight 2 Leg 1 unit tests.
- Retention-setting behavior — covered by `agent-retention-setting-roundtrip`.
- Purge-now UX polish (button placement, confirm wording, empty-state copy) — Mission 13 Flight 4
  (Alignment).

## Variants (optional)

None.
