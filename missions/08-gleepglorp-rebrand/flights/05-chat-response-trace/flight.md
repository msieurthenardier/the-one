# Flight: Chat Response Trace

**Status**: landed
**Mission**: [GleepGlorp AI Rebrand & UX Polish](../../mission.md)

## Contributing to Criteria

- [ ] In Chat, tool-call and tool-result events are presented as part of a per-response trace attached to the assistant turn, rather than as inline messages in the conversation stream, and the same trace structure renders on session rejoin from persisted history (not just live broadcast)
- [ ] The M07 OAuth `auth_required` pause-and-replay flow (consent button surfaced in Chat, pause snapshot on rejoin) continues to work after the chat trace restructure
- [ ] All existing functionality (M01–M07 capabilities) continues working after the rebrand and polish passes — no regression in agent CRUD, provider management, chat persistence, MCP integration, etc.
- [ ] Automated browser tests pass after the rebrand and polish work; local visual-snapshot baselines regenerate cleanly post-palette-swap and snapshot tests fail meaningfully on subsequent regression

---

## Pre-Flight

### Objective

Restructure the chat conversation stream so that tool-call and tool-result events become part of a **per-assistant-turn trace** attached to each assistant response, rather than full inline messages competing with the actual reply. The trace is a Linear/Cursor-style collapsible container that folds beneath the assistant message; the live "thinking" indicator becomes part of the trace shell rather than a sibling element. The restructure spans both the live broadcast path (`_process_and_broadcast` / `_broadcast_one`) and the persisted-history hydration path (`messages_to_ui_events`), so that rejoin renders the same trace shape as live broadcast. The M07 OAuth `auth_required` pause-and-replay flow must continue to surface its consent button and re-emit the pause snapshot on reconnect. Before any of the trace work begins, a **test-stability sweep** triages and quarantines the chronic hangs that have been bleeding into every flight since F1, so the trace work — and every flight after it — runs against a reliable suite. Extended-thinking blocks from Anthropic's `thinking_blocks` API surface are explicitly out of scope; this flight lays the trace shell that a future provider-shape change could populate.

### Open Questions

- [x] **Trace presentation style** → Resolved: per-response collapsible inline trace, Linear/Cursor-style (trace folds beneath the assistant message). See Design Decisions.
- [x] **Trace event-shape design** → Resolved: discriminator metadata (`parent_message_id`) on existing `tool_call` / `tool_result` events plus a frontend grouping layer. See Design Decisions.
- [x] **Hanging-test triage as a leg of F5 vs separate flight** → Resolved: Leg 01 of F5. The chat-trace work depends on a reliable test suite for verification anyway; attaching the sweep to F5 keeps it tethered to a deliverable rather than orphaning it as a maintenance flight that competes for attention.
- [x] **Thinking indicator placement** → Resolved by mission spec: lift into the trace shell as part of the live trace; remove from sibling DOM position.
- [x] **`app_with_agent` `.session-agent-badge` race** (mission Known Issue #1) → Resolved: fold into Leg 04 baseline regeneration. We are already regenerating `chat_with_messages` pixel baselines after the trace restructure; fixing the fixture race is what unblocks the regeneration anyway.
- [x] **Closing alignment HAT** → Resolved: included as Leg 04 even though F5 is structural rather than polish. The chat surface is the highest-touch operator surface and an operator-driven HAT pays for itself on a restructure of this size.

### Design Decisions

**Trace presentation: collapsible inline beneath the assistant turn (Linear/Cursor-style)**
- Choice: Each assistant turn renders as a normal message bubble with a collapsible trace shell directly beneath it. The trace shell contains the tool-call / tool-result events for that turn and the live thinking indicator during in-flight rendering.
- Rationale: Matches operator's mental model from mature LLM clients. Side-panel debugger would over-engineer for a single-pane chat UI; hybrid would add complexity without paying for itself at this stage.
- Trade-off: Trace state (collapsed vs expanded) is per-turn, not globally persisted across sessions. Acceptable — the trace is an inspection affordance, not a long-lived data structure.

**Event-shape: `parent_message_id` discriminator on existing events (Mission OQ option b)**
- Choice: Add a `parent_message_id` field (string, the id of the parent assistant message) to `tool_call` and `tool_result` events on broadcast AND in the `messages_to_ui_events` projection. Frontend groups events by that id into a per-assistant-turn trace container.
- Rationale: Minimal protocol change — no new event type, no new persisted shape, no migration of historical rows. The M07 OAuth pause-snapshot walk reads `agent.messages` directly (not the event stream), so it is untouched by an event-stream discriminator. Round-trip through `messages_to_ui_events` is trivial: project the parent assistant message id alongside each tool event as the function already walks the message list.
- Trade-off: Frontend takes on a grouping responsibility (walk events, bucket by `parent_message_id`, render each bucket as a trace shell). Acceptable — the alternative (a new top-level `trace` event keyed by parent id, persisted alongside existing events) requires both protocol AND persistence changes for a small UX-side gain.
- Backward compat: events without `parent_message_id` (legacy DB rows) render at top level outside any trace shell. Leg 03 picks the visual treatment for unattributed events (recommended: render as a top-level "Legacy" trace shell, or as standalone bubbles).

**`tool_call_id` is plumbed alongside `parent_message_id`**
- Today's `tool_call` and `tool_result` events do NOT carry `tool_call_id` even though `ToolCall.id` and `ToolResult.tool_call_id` are persisted on the `Message`/`ToolResult` dataclasses (verify against `the_one/db/codec.py:11-25, 102-113` and `the_one/interfaces/web/app.py:646-668, 741-779`). The frontend currently pairs a result to its call by ordering within the iteration. Once events get grouped under a trace, the frontend needs `tool_call_id` to pair-within-trace robustly (otherwise a multi-tool-call assistant turn becomes ambiguous if the WS reorders or a result arrives out of order).
- Choice: Add `tool_call_id` to both `tool_call` (sourced from `ToolCall.id`) and `tool_result` (sourced from `ToolResult.tool_call_id`) events at every construction site, mirrored in `messages_to_ui_events`. Six sites total: `app.py:646-652` and `app.py:664-670` (`_broadcast_one`), `app.py:741-743` and `app.py:773-779` (`_process_and_broadcast`), `codec.py:103-104` and `codec.py:107-113` (`messages_to_ui_events`). One-line addition at each; removes a hidden second event-shape coupling L03 would hit anyway.
- Architect-flagged: this is paired with `parent_message_id`; the spec treats the two as a single discriminator-pair change to avoid touching the same code sites twice.

**`session.history` carries both discriminator fields on the live side**
- `session.add_event` is called at the boundary the WebSocket-send is also called from. Both `parent_message_id` and `tool_call_id` must be present at the `add_event` call site, not just at the WebSocket-send call site — otherwise live broadcast and rejoin produce divergent event streams (the live history is what the server replays in `session_joined`'s `history` field).

**Discriminator id source: projection-time, not a new `Message.id` dataclass field**
- Pre-committed (not deferred to L02): `parent_message_id` is computed at projection time. On the broadcast side (`_broadcast_one`, `_process_and_broadcast`), it is derived from the immediately-preceding assistant Message in the same iteration (reference identity is available — the assistant Message that yielded the tool_calls is in scope). On the replay side (`messages_to_ui_events`), the rule is symmetric: walk the message list; when projecting tool events, look back to the most recent assistant Message and use its id. The id itself is a uuid4 minted at the point of projection and cached on the event object (broadcast) or on a position-keyed dict (replay) for the duration of the iteration / projection — NOT persisted on the `Message` dataclass.
- Rationale: adding a field to `Message` has cross-cutting impact — every provider in `the_one/llm/` constructs `Message` instances from API responses (Anthropic, OpenAI, Ollama, mock), `encode_messages`/`decode_messages` round-trip every row (historical rows have no id), and the agent loop's iteration semantics (`agent/core.py`) index into `messages`. Projection-time computation avoids all of that — the id only exists at the event-stream layer, which is where it's actually consumed. The Adaptation Criteria preserves a back-out path if implementation reveals a hidden need for a persisted id, but the working assumption is projection-time.
- Stability: a uuid4 minted at projection time is NOT stable across rejoins — rejoining the same session generates fresh ids. This is correct: the trace grouping is structural (which tool events attach to which assistant turn), not identity-bearing across sessions. The frontend treats ids as opaque grouping keys, not as persistent record ids.

**M07 `auth_required` event preserves the discriminator**
- `_auth_required_event_from_metadata` (`app.py:566-591`) builds the pause-surface event INSTEAD of a `tool_result` event. The replaced event must still carry `parent_message_id` AND `tool_call_id` so the eventual resumed `tool_result` groups under the same assistant turn. Leg 02 wires this through the caller of `_auth_required_event_from_metadata` (the metadata payload itself carries `tool_call_id` already; `parent_message_id` is added at the caller).
- **Resume path also carries the discriminator**: `_resume_paused_session` (`app.py:812-868`) re-enters `_broadcast_one` with messages yielded by `Agent.resume_after_auth()`. Those tool-result messages get projected against the same `agent.messages` list, so the projection rule (look back to the most recent assistant Message) yields the same `parent_message_id` the original (paused) `tool_call` carried — automatically. Leg 02 includes an integration test that verifies this against a fixture that pauses on `auth_required`, resolves, and re-emits.

**Live thinking indicator is rendered INSIDE the in-flight trace shell**
- When the assistant turn opens, the trace shell is created in its in-flight state with the thinking indicator inside it. Subsequent `tool_call` / `tool_result` events append to the same shell. On `done`, the indicator is removed; the shell stays as the persistent trace for the turn. On rejoin to an in-flight turn (`is_processing: true`), the rejoin must reconstruct the in-flight shell with the indicator inside.

**Test-stability sweep is a Leg of F5, not a separate maintenance flight**
- Choice: Leg 01 (`test-stability-sweep`).
- Rationale: F5's mission criteria include "automated browser tests pass after the rebrand." A reliable suite is a precondition for verifying every subsequent leg. Treating it as an F5 leg keeps the work tethered to a deliverable.
- Trade-off: F5 grows from the ~2-leg forecast in the mission spec to 4 legs. The flight is bigger, but each leg is independently completable and the test-stability work pays back across the rest of the mission.

**1-at-a-time test invocation; serial execution against the shared container, parallel only at triage analysis**
- Methodology: each test runs as its own `timeout 30 docker exec the-one pytest <file>::<test> -x -q` invocation. Host-side `timeout` is SIGKILL-able even when pytest-timeout can't reach the wedged subprocess (F4 debrief observation).
- **Pre-committed serialization rule** (architect-flagged for concretization): TEST INVOCATIONS against the shared `the-one` container are serial — never two `pytest` processes against the container at once. Spawned Developer agents fan out at the TRIAGE ANALYSIS layer (root-cause investigation per hang, fix-or-quarantine decisions, KI authoring) but they coordinate around a single serial test-execution queue. Given F4 evidence that the broad-pytest WAL anomaly is a session-scoped DB-fixture artifact, even file-level parallel test execution risks colliding state. Triage-time parallelism (agents reasoning about different hangs simultaneously) is safe and gives most of the wall-clock benefit.
- Alternative considered and rejected: spawning per-agent scratch containers via `make rebuild` would eliminate collisions but is heavyweight (~minutes per agent rebuild) and would block on Docker daemon contention. Serial invocation against the shared container is simpler and faster overall.

**Per-symptom-class investigation budget, not per-test**
- Architect-flagged: when multiple tests hang with the same root-cause signature (e.g. the SQLite WAL fingerprint), L01 burns the investigation budget on the symptom class ONCE — fix or quarantine all members of the class with a single decision. Per-test 5-minute budgets apply only to hangs with distinct signatures. F4 evidence supports this: the 2 hangs in `test_flow_provider_setup` and `test_flow_agent_crud` likely share a root cause and should be triaged as a pair.

**L01 new-skip budget**
- Architect-flagged: L01 may add up to **5 new `pytest.mark.skip` markers** beyond the F4 baseline of 35 skipped. Each new skip carries a precise `reason="…"` referencing the L01 investigation note + a corresponding Known Issue entry. Any skip count above 5 escalates to operator review before L01 exits. (The 5-cap is a guardrail — not a target. If L01 fixes every hang in place, the new-skip count is 0 and that's the win.)

### Prerequisites

- [ ] F4 (Studio Polish) committed and merged (commit `19d9a58`) — confirmed
- [ ] F3.5 shell-chrome polish committed and merged — confirmed
- [ ] Host-side `timeout NN docker exec` testing posture is documented or adopted at the start of L01 (F4 debrief recommendation #4)
- [ ] Container `the-one` is running and reachable via `docker exec` for the duration of L01
- [ ] All currently-passing baselines for non-chat pixel snapshots are captured before L01 starts (so L01's quarantine work doesn't accidentally mask a real regression)

### Pre-Flight Checklist

- [ ] All open questions resolved
- [ ] Design decisions documented
- [ ] Prerequisites verified
- [ ] Validation approach defined (per-leg automated tests + Leg 04 operator HAT + post-leg browser smoke after each leg touching globally-rendered chat elements)
- [ ] Legs defined

---

## In-Flight

### Technical Approach

**Phase 1 — Test stability (Leg 01).** Spawn N Developer agents in parallel from the Flight Director. Each agent is given a slice of test files and the instruction: enumerate every test in the slice, run each as a separate `timeout 30 docker exec the-one pytest <file>::<test> -x -q` invocation, catalog the result as `pass | fail | hang | error`, and surface a triage matrix. For hangs: each agent attempts root-cause investigation within a fixed per-test budget (e.g. 5 minutes of investigation per hang); if root cause is identified and tractable, fix in place; if not, quarantine with `@pytest.mark.skip(reason="…")` and a precise comment naming the symptom + last-known good context. The chronic broad-pytest SQLite WAL anomaly chronicled F1→F4 is the headline target — it has gated meaningful broad-suite measurement for 5 flights running. L01 also retires or updates `.gitignore` for any test artefacts that are creating noise. Exit: every suite invocation either completes within its declared budget OR has a documented `skip` with a Known Issue entry.

**Phase 2 — Backend event-shape and persistence hydration (Leg 02).** Introduce `parent_message_id` AND `tool_call_id` (paired discriminator change) on `tool_call` / `tool_result` events at every site they are constructed in `_broadcast_one` (`app.py:646-668`) and `_process_and_broadcast` (`app.py:741, 773-777`). Source `parent_message_id` from the immediately-preceding assistant Message at projection time (NOT a new `Message.id` field — see Design Decisions). Source `tool_call_id` from the existing `ToolCall.id` / `ToolResult.tool_call_id` already on the dataclasses. Mirror both fields in `messages_to_ui_events` (`db/codec.py:85-114`) so DB replay produces the same event stream as live broadcast for the discriminator-pair specifically. (Pre-existing diffs between live and replay — e.g. the `tool_result.content[:2000]` truncation in live vs untruncated in replay — are out of L02 scope; they become a Known Issue.) Update `session.add_event` callers so both fields are present in `session.history` for the `session_joined` replay path. Preserve the M07 `auth_required` event: the caller of `_auth_required_event_from_metadata` (`app.py:566-591`) attaches both fields so the resumed `tool_result` groups under the same trace. Extend `tests/test_db_codec.py` with codec round-trip tests for the new fields; add a focused integration test for the WS broadcast shape against a fixture session with multiple turns including a paused-and-resumed `auth_required` turn (verifies that the resumed tool_result inherits the original tool_call's `parent_message_id`). Grep verification: `_process_and_broadcast`'s `result_messages` return shape is a separate consumer (`app.py:693, 752, 780, 809`); confirm via grep it's discarded by callers (`_spawn_message_processing` at `app.py:222` discards) and that no test inspects the shape — if any test does, L02 either extends it or excludes the field.

**Phase 3 — Frontend trace UI + thinking-indicator reposition (Leg 03).** Replace the current `addMsg('tool', …)` inline tool-bubble rendering in `chat.js` (~lines 701-713 for live, ~207-208 for replay) with a per-assistant-turn trace shell. New frontend module: `the_one/interfaces/web/static/js/areas/chat/trace-shell.js` exposing `App.chat.renderTrace` / `App.chat.appendToTrace` — symmetric with the existing `chat/message-bubble.js`, `chat/thinking-indicator.js`, `chat/history-buckets.js` module layout. On `assistant` / `assistant_chunk` for a new `parent_message_id`: append the assistant bubble + an associated trace shell (initially in in-flight state with the thinking indicator inside). On `tool_call` / `tool_result` events carrying that `parent_message_id`: append into the matching trace shell, paired by `tool_call_id`. On `done`: remove the in-flight indicator from the shell but leave the shell present (collapsed by default once tool events were emitted; absent entirely if no tool events fired). On replay (`renderHistory` at `chat.js:192-215`): walk `data.history`, bucket events by `parent_message_id`, render each assistant turn with its trace shell. Legacy events without `parent_message_id` (DB rows from before L02 landed) render as standalone bubbles or under a single synthetic "Legacy" trace shell — L03 design picks the visual treatment. The streaming bubble path (`assistant_chunk`, pacing queue, markdown finalize) stays inside the assistant bubble; the trace shell is its sibling. Thinking indicator's `createThinking` / `removeThinking` helpers are rewired so their parent is the trace shell rather than `.messages` directly. CSS class additions land in `chat.css`: `.trace-shell`, `.trace-shell.collapsed`, `.trace-shell.in-flight`, `.trace-shell .msg.tool` overrides for the in-trace context. WCAG: trace-shell collapse/expand affordance must be keyboard-operable (`<button>` toggle or `<details>`/`<summary>` element) with focus-visible styling, and the live trace must remain perceivable by `aria-live="polite"` users (announce tool events inside the shell, or move the existing `aria-live` from `.messages` to whichever element semantically owns the live content).

**Phase 4 — Alignment HAT + snapshot regeneration (Leg 04).** Operator-driven HAT across the chat surface: golden path (short single-tool turn), multi-tool turn (3+ tool calls per response), error turn (tool error projects into the trace), M07 `auth_required` turn (consent button surfaces, popup flow runs, resumed tool result groups under the same trace), multi-turn session with mid-turn hard refresh (rejoin reconstructs in-flight trace shell with the thinking indicator). Apply inline fixes for any defects surfaced. Fix the `app_with_agent` fixture `.session-agent-badge` race that has been gating the 2 `chat_with_messages` pixel baselines since F1 (mission KI #1). Regenerate pixel baselines for the chat surface. Run post-leg browser regression smoke (`pytest tests/browser/ -q -m browser 2>&1 | tail -3`) per F4 debrief recommendation #5.

### Checkpoints

- [ ] L01: triage matrix captured for every test file in the test tree
- [ ] L01: every suite invocation either completes inside its declared budget or has a documented `skip` + KI entry
- [ ] L01: broad pytest (`-m "not browser and not pixel"`) runs to completion at least once after the sweep — first time across F1→F5
- [ ] L01: new-skip count ≤ 5 above F4's 35 baseline (escalate if more before L01 exits)
- [ ] L02: `parent_message_id` AND `tool_call_id` flow through broadcast, `session.history`, codec round-trip, and `messages_to_ui_events`
- [ ] L02: M07 `auth_required` pause snapshot path verified (rejoin to a paused session still renders the consent button; the resumed `tool_result` carries the same `parent_message_id` as the original paused `tool_call`)
- [ ] L02: backend unit tests for codec round-trip and integration test for WS broadcast shape (multi-turn fixture, with at least one paused-and-resumed `auth_required` turn), both passing
- [ ] L03: live trace shell renders for in-flight + completed turns; thinking indicator inside the shell; tool events grouped under their parent assistant turn; results paired to calls by `tool_call_id`
- [ ] L03: rejoin from persisted history renders the same trace structure as live broadcast (modulo pre-existing live-vs-replay diffs noted as KIs)
- [ ] L03: streaming bubble (chunk + markdown finalize) path untouched and still working
- [ ] L03: trace-shell collapse/expand affordance keyboard-operable; `aria-live` semantics preserved
- [ ] L04: operator HAT signed off across golden + edge paths
- [ ] L04: `app_with_agent` `.session-agent-badge` race fixed; `chat_with_messages` pixel baselines regenerate cleanly (10 → 12 of 12 passing on re-run)
- [ ] L04: post-leg browser regression smoke clean — no new failures vs the F4 baseline as adjusted by L01's skip delta

### Adaptation Criteria

**Divert if**:
- L01 surfaces hangs whose root cause is a genuine product bug (not test infrastructure) and the bug landed during F1–F4 — that's a regression that probably warrants its own narrow-scope leg or a divert to a maintenance flight rather than absorbing it into the test-stability sweep
- L01 cannot complete its sweep within the new-skip budget (>5 skips required) without operator review — pause for explicit go/no-go
- L02 implementation reveals projection-time `parent_message_id` derivation has a gap the spec didn't anticipate (e.g. resume path messages don't have an assistant Message in scope to project against) — back out to introducing a `Message.id` field, accepting the cross-cutting impact described in Design Decisions
- L02 surfaces that the M07 `auth_required` walk DOES depend on event-shape (contradicting current reading) — re-scope L02 to cover the OAuth flow's discriminator path explicitly
- L04 HAT surfaces a trace-shape defect that requires backend-shape revision — kick back to L02

**Acceptable variations**:
- L01 hang root causes that are quick to fix (single-line config or fixture tweaks) get fixed in place rather than quarantined
- L03's chosen collapsible-trace HTML shape (e.g. `<details>`/`<summary>` vs custom `<div>` + `aria-expanded`) is implementation choice and need not gate the flight
- L03's choice of how to render legacy events without `parent_message_id` (standalone bubbles vs synthetic "Legacy" trace shell) is implementation choice
- L02's choice of how to inject `parent_message_id` into the M07 `auth_required` event (new parameter to `_auth_required_event_from_metadata` vs caller-side dict mutation after construction) is implementation choice
- L04 can absorb additional small chat-surface polish items if they surface during HAT and are quick wins; non-trivial items get logged as KIs for F6 (Chat Polish)

**Note for L02 leg-design**: the integration test asserting cross-path equivalence should assert ONLY on `parent_message_id` and `tool_call_id` field presence + equality across live and replay event streams — NOT full dict-equal. Pre-existing live-vs-replay diffs (e.g. `tool_result.content` truncation) will fail full dict-equal and are intentionally out of L02 scope.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `test-stability-sweep` - Methodical 1-test-at-a-time triage of chronic hangs across browser + broad-pytest + pixel suites; parallelized via spawned Developer agents; fix where tractable, quarantine the rest with documented KIs
- [x] `trace-event-shape-and-hydration` - Add `parent_message_id` discriminator to `tool_call` / `tool_result` events on broadcast + history-event projection; preserve M07 `auth_required` pause-snapshot walk; codec round-trip tests + WS broadcast integration test
- [x] `chat-trace-ui-and-thinking-reposition` - Collapsible inline trace shell per assistant turn; group tool events by `parent_message_id`; move live thinking indicator into the trace shell; rejoin reconstructs the same shape
- [x] `alignment-hat-and-snapshot-regen` - Operator HAT across golden + edge chat paths; fix `app_with_agent` fixture badge race; regenerate `chat_with_messages` pixel baselines; post-leg browser regression smoke

---

## Post-Flight

### Completion Checklist

- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing (no new browser-suite failures vs F4's 315p/35s baseline)
- [ ] `chat_with_messages` pixel baselines regenerate cleanly on re-run (closes mission KI #1)
- [ ] Documentation updated (agents.md F5 subsection covering the trace event-shape contract + the test-stability sweep methodology)

### Verification

How to confirm the flight achieved its objective:

1. **Trace structure on live broadcast**: send a user message to an agent that emits at least one tool call; verify the chat surface renders the assistant message bubble with a trace shell beneath it containing the tool-call + tool-result events, NOT inline messages competing with the assistant reply.
2. **Trace structure on history replay**: refresh the browser mid-session OR rejoin a completed session; verify the same trace shape renders from persisted history. Bug-bait: did the rejoined trace lose any events vs the live render?
3. **Thinking indicator in trace shell**: send a user message; verify the live "thinking" indicator appears INSIDE the trace shell, not as a sibling chat element.
4. **M07 OAuth flow**: trigger an `auth_required` pause on an MCP source that uses OAuth; verify the consent button surfaces, the popup flow runs, the resumed `tool_result` groups under the SAME trace shell as the paused tool call. Refresh mid-pause; verify the consent button re-surfaces on the rebound websocket.
5. **No regression in M01–M07 capabilities**: narrow gate + browser suite + pixel suite all run cleanly. Browser suite: ≥ 315 passing vs F4's baseline, skip count = 35 + L01 delta (the 35 are F4-deferred Studio tests not in F5 scope; L01's new skips are capped at +5 with each documented as a Known Issue).
6. **Test suite reliability**: the broad pytest (`-m "not browser and not pixel"`) runs to completion. This has hung since F1 — its completion is the headline L01 verification.
7. **Chat snapshot baselines regenerate**: pixel suite 12/12 passing on re-run after Leg 04 (closes the 2 carried-forward `chat_with_messages` KIs from F1).

### Notes on Future Surface Extensions

**Anthropic `thinking_blocks` are out of scope for this flight.** The mission spec is explicit. The `parent_message_id` design accommodates a future flight that surfaces them: introduce a new event type (e.g. `assistant_thinking`) also carrying `parent_message_id`, grouping under the same trace shell as `tool_call` / `tool_result`. No protocol re-work required when that flight arrives.

**`Session.message_count` semantics are unchanged.** The summary metric (`app.py:172-180`) reports `message_count: len(self.history)`. Once tool events get grouped under traces visually, the operator may expect a "trace counts as one" reading, but the metric still counts every event including trace contents. If a future flight surfaces this count in UI in a way that matters, that flight redefines it then; F5 does not.
