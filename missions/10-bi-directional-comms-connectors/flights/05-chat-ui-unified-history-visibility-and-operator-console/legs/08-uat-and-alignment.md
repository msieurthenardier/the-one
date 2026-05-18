# Leg: uat-and-alignment

**Status**: completed
**Flight**: [Chat UI — Unified History, Visibility Distinction, Operator Console](../flight.md)

## Objective

Guided HAT walkthrough of every F5-introduced operator-facing surface
on a live system. The operator drives the Chat UI through real
scenarios — session list with connector-attached entries, opening a
connector-attached session, observing the unified-history rendering,
typing into the operator console, watching the operator-only marker
appear on the persisted-and-refreshed view, triggering a platform-
send via the agent's tool call, observing the platform-visible
result. The leg cannot land without the operator's sign-off.

Per the agentic-workflow HAT protocol: the Flight Director guides the
operator through verification steps ONE AT A TIME, waits for the
operator to perform each step and report results, fixes issues inline
(spawning a Developer agent if code changes are needed), and re-
verifies that step before moving on.

## Context

- **Flight slot**: F5 L8 — the REQUIRED HAT closer. User-directed at
  planning time (per flight.md L82-86) — making this leg required,
  not optional. F5 is the first end-to-end operator-visible exercise
  of the connector subsystem (F1-F4 were pre-UI scaffolding); the
  HAT catches design-language drift, two-layer rendering ambiguity,
  and operator-mental-model gaps that automated tests can't surface.
- **Legs 1-7 have committed.** All seven autonomous legs landed under
  `flight/05-chat-ui-unified-history-visibility-and-operator-console`,
  reviewed and committed. The system is now ready for operator HAT.
- **Known limitation carried into HAT**: live-broadcast visibility
  tagging is NOT yet in place on the WS-typed operator-input path
  (L5 documented this; the persisted view on refresh shows the
  marker correctly, but the LIVE typing moment doesn't). The
  operator should refresh their browser after each turn during HAT
  to verify the marker. Inbound-side live broadcast IS tagged
  correctly (L6).

## Inputs

- Container running on this branch's HEAD (commit `646748c` or
  whatever the current HEAD is after the leg-1-7 commit).
- Operator's web browser pointed at the container's host.
- A connector-attached `chat_sessions` row seeded for the HAT
  scenarios (the Flight Director will guide creation via the Admin
  Connector-Accounts surface from F2, then trigger a stub-connector
  inbound via the dispatcher to create the session).

## Acceptance Criteria

ALL of the following must be operator-confirmed before the leg
can be marked completed:

- [ ] **Session list source badge**: a connector-attached session
      shows a `[stub]` badge (or whatever connector type is in
      play) in the Chat sidebar; web-native sessions do not.
- [ ] **Unified history rendering**: opening a connector-attached
      session shows the platform-visible peer messages WITHOUT
      the operator-only marker AND the operator-only assistant
      replies / tool calls WITH the marker (left border + small
      `[operator-only]` label).
- [ ] **Operator console — local typing**: typing into the chat
      composer in a connector-attached session, the typed message
      is sent. After refreshing the browser, the operator's user
      message AND the agent's reply both render with the
      operator-only marker — confirming the message is logically
      operator-console-only.
- [ ] **Operator console — platform-send carve-out**: the operator
      asks the agent (in the connector-attached session) to send
      a specific message to the platform via the platform-send
      tool. After refresh, the operator's request bubble has the
      operator-only marker; the agent's `send_to_platform_channel`
      tool-call bubble has the operator-only marker; the
      tool-result bubble (the success record of the platform send)
      does NOT have the operator-only marker (peer-visible, the
      operator can confirm peers saw this content).
- [ ] **Inbound + live observation**: while the operator is
      viewing a connector-attached session in chat, a new peer-
      inbound message arrives via the stub connector's
      `dispatch_inbound` (the Flight Director will trigger this).
      The new message AND the agent's reply appear in real time
      WITH visibility correctly applied (peer message: no marker;
      agent reply: operator-only marker UNLESS it triggers a
      platform-send, in which case the success tool_result is
      peer-visible).
- [ ] **Design-language fit**: the operator confirms the visual
      treatment of the source badge, the operator-only marker,
      and the inline label matches the M04/M06 bar without
      jarring drift.
- [ ] **Concurrent same-session lock**: the operator types a
      message AND a peer-inbound arrives at the same time on
      the same session. The two turns SERIALIZE (do not
      interleave) — the operator sees one complete turn render
      before the other starts.
- [ ] **No leakage**: messages the operator types into the
      operator console DO NOT propagate to the platform. The
      operator verifies this by checking the stub platform's
      message log (or wherever the stub records platform-side
      writes) after typing operator-console messages without
      asking the agent to platform-send. Should be empty.
- [ ] **Operator sign-off**: the operator confirms all the above
      with a "HAT passed" message, OR documents any blocking
      issue.

## Verification Steps

The Flight Director (you) will guide the operator through these
steps ONE AT A TIME. After each step, wait for the operator's
report. If a step fails, fix the issue inline (spawning a
Developer agent for any code changes), `make rebuild` to pick up
the change, and re-verify the step before moving on.

### Step 1: Preflight (Flight Director sets up)
- Container is running on this branch.
- Operator has a browser pointed at the container.
- A stub-connector account exists in the Admin surface OR the
  Flight Director will guide creating one.
- A connector-attached chat session exists OR the Flight
  Director will trigger one via the dispatcher.

### Step 2: Session-list source badge
- **Operator action**: Open the Chat area in the browser.
- **Expected**: A connector-bound session shows a badge with the
  connector type (e.g. `[stub]`) next to the agent name. A web-
  native session does NOT show this badge.
- **Operator reports**: pass / specific failure.

### Step 3: Open a connector-attached session
- **Operator action**: Click the connector-bound session in the
  sidebar.
- **Expected**: The chat history loads. The unified timeline
  shows BOTH platform-visible bubbles (no marker) AND operator-
  only bubbles (left border + `[operator-only]` label).
- **Operator reports**: pass / specific failure.

### Step 4: Type into the operator console
- **Operator action**: Type "what's been going on?" (or any
  message) and press Send.
- **Expected (live, may NOT show marker yet — known L5
  limitation)**: the user bubble appears immediately; the agent
  responds.
- **Then operator action**: Refresh the browser (Cmd-R or F5).
- **Expected after refresh**: the just-typed user bubble AND
  the agent's reply both render with the operator-only marker.
- **Operator reports**: pass / specific failure.

### Step 5: Trigger a platform-send
- **Operator action**: Ask the agent to send a specific message
  to the platform (e.g. "Please tell the channel hello from
  the bot."). Wait for the agent to reply (it should invoke
  `send_to_platform_channel`).
- **Then operator action**: Refresh the browser.
- **Expected after refresh**: operator's request → operator-only;
  agent's `send_to_platform_channel` tool_call → operator-only;
  agent's tool_result (the platform-send success record) → NO
  marker (peer-visible).
- **Operator reports**: pass / specific failure.

### Step 6: Inbound observation
- **Flight Director action**: trigger a stub-connector inbound
  via `dispatch_inbound` with the operator viewing the session.
- **Expected**: the new peer-visible USER message AND the agent's
  operator-only reply both appear in real time, with correct
  visibility markers applied immediately (L6 dispatcher
  broadcast carries visibility).
- **Operator reports**: pass / specific failure.

### Step 7: Design-language sanity check
- **Operator action**: scan the Chat UI's visual surfaces — the
  source badge, the operator-only marker (border + label), the
  bubble spacing.
- **Expected**: nothing jarring; the M04/M06 design-language bar
  is met.
- **Operator reports**: pass / list specific drift.

### Step 8: Concurrent-turn serialization
- **Flight Director action**: while the operator types a message
  into the connector-attached session, trigger a stub-connector
  inbound at the same time.
- **Expected**: the two turns SERIALIZE — the operator does NOT
  see interleaved per-message bubbles from both turns.
- **Operator reports**: pass / specific failure.

### Step 9: No-leakage verification
- **Operator action**: type two or three operator-console
  messages WITHOUT asking the agent to platform-send. Confirm
  via the stub platform's message log (the stub records platform-
  side writes; the Flight Director will guide where to look)
  that NONE of these operator-typed messages or the agent's
  responses to them appeared on the platform.
- **Operator reports**: pass / specific failure.

### Step 10: Sign-off
- **Operator action**: declare "HAT passed" OR list blocking
  issues.

## Files Affected

- `missions/10-bi-directional-comms-connectors/flights/05-.../flight-log.md`
  — HAT outcomes appended (per-step results + sign-off).
- `missions/10-bi-directional-comms-connectors/flights/05-.../flight.md`
  — leg 8 checkbox; flight status flips to `landed`.
- Mission artifact — flight 5 checkbox ticked.
- **(Conditional)** any production source files touched by inline
  HAT fixes — committed as part of the HAT commit.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:flight]`:**

- [ ] All acceptance criteria operator-confirmed.
- [ ] Flight-log updated with HAT outcomes.
- [ ] Leg 8 status → `completed`.
- [ ] Flight status → `landed`.
- [ ] Flight 5 checkbox ticked in mission artifact.
- [ ] Commit (single HAT commit, separate from the legs-1-7
      commit so the HAT outcomes + inline fixes are traceable).
- [ ] PR opened (or updated to ready-for-review).
