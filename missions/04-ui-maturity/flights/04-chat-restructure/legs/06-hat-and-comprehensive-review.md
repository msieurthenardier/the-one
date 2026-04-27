# Leg: 06-hat-and-comprehensive-review

**Status**: completed
**Flight**: [Chat Restructure — Components, Streaming & Markdown](../flight.md)

## Objective

Interactive Human Acceptance Test (HAT) for Flight 04. Walk the user through the full restructured chat surface in both themes, exercising the new component library, streaming infrastructure, and markdown rendering. Apply token retunes / small CSS adjustments inline if anything looks off. Confirm no regressions in F3-closed accessibility / keyboard work. User explicitly approves before flight closes.

This leg is INTERACTIVE — the Flight Director guides the human through verification steps one at a time. No autonomous Developer/Reviewer agents are spawned. Failures discovered during HAT trigger inline diagnose-and-fix (spawning a Developer agent if code changes are needed); fixes are committed separately.

## Context

- Legs 01-05 landed in commit `474b2e2` (PR #16, draft). All 407 unit + 123 browser tests pass.
- This is the LAST leg of Flight 04. Once approved, flight transitions to `landed`; flight-debrief runs separately via `/flight-debrief`.
- F2/F3 precedent: HAT is a required final leg for any flight that ships user-facing chat changes.
- F3 lesson: when the user surfaces "while we're here..." additions during HAT, weigh divert-to-F5 explicitly. F4 scope is closed; new functional requirements belong in F5 (alignment) or future flights.

## Inputs

- The committed flight branch `flight/04-chat-restructure` (PR #16) checked out and the dev server running locally.
- Mock provider (with `stream_chunks` knob) for deterministic streaming exercises.
- At least one configured streaming provider (Anthropic / OpenAI / Ollama) for real-world streaming validation. If only the mock is available, exercise streaming via mock-with-`stream_chunks` and note the deferred real-provider verification in the flight log.
- Both themes (light / dark) accessible via the existing theme toggle.

## Outputs

### `the_one/agents.md`

- Optional updates if new patterns emerge during HAT (e.g., a CSS retune that's worth documenting). Otherwise no changes.

### `missions/04-ui-maturity/flights/04-chat-restructure/flight-log.md`

- Append a `### hat-and-comprehensive-review` block under `## Leg Progress` summarising:
  - Verification steps performed
  - Any issues discovered + how they were fixed (with commit hashes for inline fixes)
  - Any "while we're here..." items that were diverted to F5
  - Final user approval timestamp / acknowledgement

### `missions/04-ui-maturity/flights/04-chat-restructure/flight.md`

- Status: `in-flight` → `landed` after user approval
- Check off the F4 flight in `missions/04-ui-maturity/mission.md`

### `missions/04-ui-maturity/mission.md`

- Check off the F4 flight in the flight checklist (post-HAT bookkeeping)

## Acceptance Criteria

The HAT passes when ALL of the following are verified by the human:

### Welcome canvas (4 states)

- [ ] **No providers configured** → Welcome canvas shows "Add a provider to get started" guidance with link to admin area
- [ ] **Providers configured but no agents** → Welcome canvas shows "Create an agent to get started" guidance with link to studio area
- [ ] **Providers + agents but no recent sessions** → Welcome canvas shows the agent picker
- [ ] **Ready state with recent sessions** → Welcome canvas shows agent picker + recent sessions list grouped by date bucket (Today, Yesterday, Earlier this week, Earlier this month, Older)

### Streaming + markdown rendering

- [ ] **Mock provider streaming**: send a message to a mock-provider agent configured with `stream_chunks=["Hello, ", "**world**", "!"]` + `delay_ms=200`. Observe:
  - Thinking indicator appears immediately
  - Thinking indicator clears on first chunk arrival
  - Bubble accumulates plain text chunk-by-chunk (visible in DevTools: `textContent` updates, no `<strong>` mid-stream)
  - On `done`, the bubble's content swaps to markdown-rendered: `Hello, <strong>world</strong>!`
- [ ] **Real streaming provider**: send a message to an Anthropic / OpenAI / Ollama agent. Observe smooth chunk-by-chunk text arrival; markdown renders on `done`. (If only mock is available, document deferred verification.)
- [ ] **Code block rendering**: send a message that elicits a code-block response (e.g., "show me a python hello-world"). Observe:
  - Code renders as `<pre><code class="language-python">` (or appropriate language)
  - Copy-to-clipboard button visible on hover/focus
  - Click copy button → "Copied!" flash appears, clipboard contains the code
  - Keyboard reach: Tab to copy button, Enter activates it
- [ ] **User message stays literal**: type `**bold**` in the input and send. The user bubble shows `**bold**` as literal text (no `<strong>` tag).
- [ ] **Tool message stays literal**: trigger a tool call (e.g., agent that calls `get_current_time`); tool output renders as `textContent` (preserves any tool-internal formatting verbatim).

### Per-message attribution

- [ ] User messages show "You" attribution
- [ ] Assistant messages show the agent name (or fallback "agent")
- [ ] Tool messages show the tool name
- [ ] Attribution renders consistently across streaming and non-streaming paths

### Thinking indicator behavior

- [ ] **Streaming providers**: indicator clears on first `assistant_chunk` arrival
- [ ] **Default-impl single-chunk**: send to a provider that doesn't natively stream (or use mock with NO `stream_chunks` set). The indicator appears briefly, then clears on the lone chunk arrival.
- [ ] **Tool call**: indicator clears on `tool_call` event, doesn't reappear before the tool result

### Telemetry overlay

- [ ] Usage tokens (input / output / total) update at end-of-stream (not start) for streaming providers
- [ ] Cost calculation reflects the configured provider pricing
- [ ] Overlay still positions correctly in both themes
- [ ] Overlay updates don't flicker / jitter during chunk arrival

### History bucketing + dropdown

- [ ] Session list groups by Today / Yesterday / Earlier this week / Earlier this month / Older
- [ ] New session appears in "Today" bucket immediately on creation
- [ ] Agent dropdown reflects the current session's agent (or "select an agent" for new sessions)
- [ ] Agent dropdown change creates a new session with the selected agent

### Session restore (persistence contract)

- [ ] Send a streaming message with markdown content (e.g., `**bold**`, code block, list)
- [ ] Reload the page (or navigate away and back via hash)
- [ ] On rejoin, the historical assistant message renders via markdown (NOT as raw `**bold**` text)
- [ ] The synthesized server-side accumulated text is what gets persisted (verify by inspecting DB if any concerns arise)

### Keyboard accessibility (no F3 regression)

- [ ] Tab order: agent select → input → send button → session list items (top to bottom) → message bubbles → message-bubble copy buttons (where present)
- [ ] Enter on session-item joins the session
- [ ] Enter on input sends the message (if non-empty)
- [ ] Shift+Enter inserts a newline in the input
- [ ] Esc closes any open delete-confirm overlay
- [ ] All `:focus-visible` rings visible on every interactive element
- [ ] Screen reader announces "Copied!" flash via the existing `aria-live` mechanism (no regression from F3 a11y polish)

### Hash routing

- [ ] `/#chat` → loads chat area at welcome canvas
- [ ] `/#chat/sessions/abc123` → loads chat area joined to session abc123
- [ ] `/#studio` / `/#admin` → loads correct area; switching back to `/#chat` preserves WS connection
- [ ] Page reload preserves the current session via the URL hash

### Both themes

- [ ] Light theme: all message bubbles, code blocks, copy buttons, attribution legible
- [ ] Dark theme: same, with appropriate contrast
- [ ] Theme toggle works without page reload
- [ ] Markdown-rendered code blocks have appropriate background contrast in both themes

### Visual snapshot regeneration (optional, local-only)

- [ ] Run `pytest --snapshot-update -m pixel` locally. Snapshots will drift due to markdown rendering changes (paragraph margins, code-block structure). Per project policy, snapshots are gitignored — local-only artifact.
- [ ] If significant unexpected drift (e.g., layout breakage), STOP and diagnose before approving HAT.

### F3 lessons applied

- [ ] If "while we're here..." items surfaced during HAT, evaluate each: in-scope inline fix (token retune, small CSS adjustment) vs out-of-scope (defer to F5 or a future flight)
- [ ] Document each diversion in the flight log under `### Diversions to F5`

### User approval

- [ ] User explicitly approves the F4 flight as complete

## Verification Steps

The Flight Director presents one step at a time; the human performs it and reports the result.

1. **Start the dev server**: `just dev` (or the project's standard dev command). Wait for "running on http://localhost:..." line.

2. **Welcome canvas — 4 states**:
   - State A (no providers): if a configured provider exists, temporarily disable it via admin UI to test the "no providers" state.
   - State B (no agents): if agents exist, temporarily disable them.
   - State C (ready, no sessions): with at least one provider + one agent configured, navigate to a fresh `/#chat` (no session in hash). Confirm agent picker visible.
   - State D (ready with sessions): create a session, then navigate back to `/#chat` (no session hash). Confirm agent picker + recent sessions list.

3. **Streaming + markdown** (mock provider):
   - In studio, create or use a mock-provider agent; configure `stream_chunks=["Hello, ", "**world**", "!"]`, `delay_ms=200`.
   - Start a new session with that agent. Send "test".
   - Observe: thinking indicator → clears on first chunk → bubble accumulates `Hello, **world**!` as plain text → on `done`, swaps to `Hello, <strong>world</strong>!` (rendered).
   - Inspect DevTools: bubble.innerHTML should contain `<strong>world</strong>`.

4. **Code block + copy button**:
   - Send a message that elicits a code-block response (or use a mock-provider agent configured with `stream_chunks=["\`\`\`python\\n", "print('hello')\\n", "\`\`\`"]`).
   - Hover over the code block: copy button visible.
   - Click copy: "Copied!" flash appears.
   - Tab to the copy button via keyboard: focus ring visible.
   - Press Enter: copies again.
   - Paste somewhere external: verify clipboard contains the code.

5. **User message literal + tool message**:
   - Type `**bold**` in the input, send. Confirm user bubble shows `**bold**` literally.
   - Use an agent with a tool (e.g., `get_current_time`). Send "what time is it?". Confirm tool message renders as `textContent` (no markdown).

6. **Thinking indicator (streaming vs single-chunk)**:
   - Test streaming: with a real streaming provider OR mock with `stream_chunks`, send a message. Observe indicator clears on first chunk.
   - Test single-chunk: with mock NO `stream_chunks`, send a message. Observe indicator briefly visible, clears on the lone chunk arrival.

7. **Telemetry overlay**:
   - Send a streaming message. Observe usage tokens update at end-of-stream (not start).
   - Switch theme; observe overlay still positions and renders correctly.

8. **History bucketing + dropdown**:
   - Create a new session today. Observe it appears in "Today" bucket.
   - Change agent via dropdown on a fresh session. Observe new session with selected agent.

9. **Session restore**:
   - Send a streaming message with markdown content.
   - Reload (Cmd-R / Ctrl-R).
   - Observe historical assistant message renders as markdown (NOT raw `**bold**`).

10. **Keyboard accessibility**:
    - Tab through the chat area. Note the order.
    - Enter on a session-item: joins.
    - Enter on input: sends.
    - Esc on delete-confirm: closes.
    - Tab to a code-block copy button: focus ring visible.

11. **Hash routing**:
    - `/#chat` → welcome
    - Click a session → `/#chat/sessions/{id}` → chat view
    - `/#studio` → studio area
    - Back to `/#chat/sessions/{id}` → session restored
    - Reload at `/#chat/sessions/{id}` → session restored after reload

12. **Both themes**:
    - Toggle theme via UI. Observe everything legible.
    - Check code block contrast specifically (background vs foreground).

13. **Visual snapshots** (optional):
    - `pytest --snapshot-update -m pixel`. Confirm no unexpected layout breakage.

14. **F3 "while we're here..." discipline**:
    - If anything was deferred to F5 during HAT, document each in the flight log.

15. **User approval**:
    - User confirms F4 is acceptable for landing.

## Implementation Guidance

**Flight Director runs this leg interactively — do NOT spawn an implementation Developer.**

For each verification step:
1. Present the step to the user (one at a time)
2. Wait for the user to perform it and report the result
3. If the user reports a failure:
   - Diagnose inline (read source, check DevTools, etc.)
   - If a code change is needed, spawn a Developer agent with a focused prompt describing the issue + the file:line target. The Developer makes the fix and commits a SEPARATE commit.
   - Re-verify the failed step before moving on
4. If the user reports success, mark the step `[x]` and proceed to the next

When all steps pass:
- Update flight-log.md with the `### hat-and-comprehensive-review` block
- Update leg 06 status to `completed`
- Check off leg 06 in flight.md
- Flip flight.md status to `landed`
- Check off F4 in mission.md
- Update PR body to mark leg 06 done
- Mark PR ready for review (`gh pr ready 16`)
- Signal `[COMPLETE:flight]`

If the user surfaces an out-of-scope concern, document it in the flight log under `### Diversions to F5` and continue HAT.

## Edge Cases

- **No real streaming provider available** (only mock): document the deferred real-provider verification in flight log; HAT can still complete with mock-only validation.
- **Snapshot regeneration breaks unexpectedly**: STOP HAT, diagnose layout breakage before declaring complete. Likely a CSS issue from the leg 05 markdown resets.
- **User reports issue mid-HAT**: pause, diagnose, fix (spawn Developer if needed), re-verify the failed step, then continue from where we paused.
- **User wants to add scope**: F4 is closed; new functional work goes to F5 or future flights. Apply F3 lessons-learned discipline.
- **HAT takes multiple sessions**: that's fine — leg 06 status stays `in-flight` across sessions. The flight log captures progress.

## Files Affected

- `missions/04-ui-maturity/flights/04-chat-restructure/legs/06-hat-and-comprehensive-review.md` — UPDATED (status `planning` → `in-flight` → `completed`; verification steps checked off as completed)
- `missions/04-ui-maturity/flights/04-chat-restructure/flight-log.md` — UPDATED (leg progress entry; F3 diversions if any)
- `missions/04-ui-maturity/flights/04-chat-restructure/flight.md` — UPDATED (status `in-flight` → `landed`; leg 06 checked off)
- `missions/04-ui-maturity/mission.md` — UPDATED (F4 flight checked off)
- Possibly: `the_one/agents.md`, CSS files, JS files — only if HAT discovers issues that need inline fixes (separate commits)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:flight]`:**

- [ ] All HAT verification steps completed and acceptance criteria checked off
- [ ] Flight log updated with the `### hat-and-comprehensive-review` block (verification steps performed, issues + fixes, F5 diversions, user approval)
- [ ] Any inline-fix commits pushed to the flight branch
- [ ] Leg 06 status set to `completed`
- [ ] Leg 06 checked off in flight.md
- [ ] Flight.md status flipped to `landed`
- [ ] F4 flight checked off in mission.md
- [ ] PR body updated to mark leg 06 done
- [ ] PR marked ready for review (`gh pr ready 16`)
- [ ] Signal `[COMPLETE:flight]`
