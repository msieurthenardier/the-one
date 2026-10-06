# Behavior Test: Extended Thinking + Tool Turn Round-Trips

**Slug**: `extended-thinking-tool-turn`
**Status**: active
**Created**: 2026-07-02
**Last Run**: 2026-07-03-12-14-26 (PASS 6/6 — see `runs/2026-07-03-12-14-26.md`)
**Updated**: 2026-10-05 (M25 F4 leg 8: step 1 starts the chat through New chat and the agent picker, as a pending chat with no telemetry; step 5's baseline is the first joined reading)

## Intent

Verify the one thing unit tests cannot: that a **real Anthropic model** with extended
thinking enabled can complete a turn that both emits thinking **and** calls a tool, and that
the **follow-up turn** (carrying the tool result back) *also* completes without an API error —
which only happens if the captured signed thinking blocks were replayed correctly, in the
right order, on the second request. This is a live, multi-turn, cross-component flow (web
chat → agent loop → Anthropic adapter → real API → tool dispatch → replay) that a fixtured
unit test cannot exercise end-to-end. It also confirms the operator-facing surface: the
thinking renders as a collapsed disclosure and survives a chat reopen (history replay). This
is the acceptance gate for Mission 16's extended-thinking criterion.

## Preconditions

- The app is running and reachable on a **dedicated dev instance, non-default port**
  (e.g. `:8485`) with a scratch data directory — never the operator's default `:8484`
  instance (see CLAUDE.md's "Behavior-test credential convention" safety rule).
- An **Anthropic API key** is stored in the credential store.
- **Credential**: this instance is gated (Mission 20 Flight 1). Follow CLAUDE.md's
  "Behavior-test credential convention" — read the long-lived credential from the
  instance's data directory and mint a handoff URL for the Step-1 navigation
  (single-use; re-mint if navigating again).
- An agent exists (or is created during setup) that: uses the **Anthropic** provider, targets
  an **adaptive-thinking-capable** Claude model (**Sonnet 4.6 or newer**), has the **Extended
  thinking** toggle **ON** (the provider-editor checkbox — enablement is adaptive-only, no token
  budget), and has **at least one tool enabled** whose invocation is easy to induce (e.g. a time/
  math/read tool — something the model will reach for on a direct question).
- The tool chosen is one the model reliably calls for the Step-2 prompt (pick the prompt to
  match the enabled tool).

## Observables Required

- **browser** (DOM state, streamed chat content, the thinking `<details>` disclosure, error
  bubbles, tool-trace shells — measured via chrome-devtools).
- **browser** again for persistence (post-reload DOM after history replay).
- *(optional corroboration)* **shell** — server log tail to confirm no Anthropic 400/error was
  swallowed, and/or **http**/DB read of the session's persisted messages. Not required if the
  DOM assertions are unambiguous.

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | Navigate the browser to the Chats destination (rail "Chats", `#chats`). Start a new chat with the thinking-enabled Anthropic agent described in Preconditions (create it first if needed): click the Chats list's **New chat** (`chats-new-btn`), type the agent's name in the agent picker's search (`agent-picker-search`), and press Enter. | A pending new chat with the thinking-capable Anthropic agent: the chat header (`chat-header`) reads "New chat" with "with {agent}", the new-chat state (`chat-new-state`) names the agent, and the transcript is empty. **No telemetry readout shows** (a pending chat has none; it appears once the first send joins the chat). |
| 2 | (Setup) Confirm the agent's **Extended thinking** toggle is ON and a tool is enabled (via the agent/provider editor if needed). | (empty — setup only) |
| 3 | Send a message that induces a single tool call and benefits from reasoning — e.g. a question the model must think through and then answer using the enabled tool (matched to that tool). | Within a reasonable time, the turn completes: an **answer bubble** is rendered, a **tool-call trace** appears for the turn, and **no error bubble** is shown. The turn's `done` fires. This completing at all is the primary witness — the tool round-trip is the follow-up turn, which the API rejects if thinking replay was wrong. |
| 4 | Locate the thinking disclosure for that assistant turn. Expand it. | A collapsed-by-default **`Thinking` `<details>` disclosure** is present **with the turn's assistant output** (it renders interleaved per reasoning step on a multi-tool turn — Thinking→Tool→…→answer — not necessarily a single block above the answer); expanding it reveals non-empty reasoning text. `[a11y]` the disclosure is keyboard-focusable and toggles via Enter/Space — a native `<details>`/`<summary>` that is focusable satisfies this (native summary keyboard toggling is guaranteed by the HTML spec; empirical trusted-keypress actuation requires an apparatus with trusted-key injection, which goldfinch lacks). |
| 5 | (Wait/observe) Confirm the full turn settled — answer present, tool trace present, thinking present, no error, telemetry usage updated. | All four present together for the same turn; the telemetry readout (`.telemetry-overlay` token meter in the row above the composer — reads `in/out/ctx/max`) shows a **non-zero used/max**, i.e. a delta up from its first joined reading (0%, reset when Step 3's send joined the chat, before the turn's usage arrived; Step 1's pending chat showed no readout at all) — thinking tokens are billed. |
| 6 | Reload the page (or leave and re-open this chat) so history replays from persistence. | After history replay, the same turn re-renders **with** its thinking disclosure (collapsed) and its answer + tool trace — i.e. the thinking round-tripped through persistence, not just the live turn. No error bubble on replay. |
| 7 | Send one more follow-up message in the same chat that again induces reasoning + a tool call. | The second thinking+tool turn also completes with no API error — confirming multi-turn replay is stable across an accumulating history, not just the first turn. |

**Row conventions**: Step 2 is pure setup (no judgment). Step 5 is an observation/settle
point. `[a11y]` marks the disclosure accessibility check.

## Out of Scope

- **Live token-by-token thinking streaming** — v1 reveals thinking whole after the answer
  (flight DD2); this test does not assert streaming deltas.
- **OpenAI / Ollama reasoning** — Anthropic-only this flight (DD5).
- **The `reasoning_effort` knob** — backlog A4, a separate flight.
- **Redacted-thinking-specific rendering** — if a redacted block appears it must not break the
  turn, but inducing one reliably is not part of this test.
- Provider-editor field mechanics (covered by the browser provider-editor unit/flow test).

## Variants (optional)

- **Thinking OFF (disabled), fresh chat:** the same prompt in a new chat with the **Extended
  thinking toggle OFF** → the turn still completes, no thinking disclosure appears, and behavior
  matches a normal non-thinking turn (regression guard that the toggle truly gates enablement).
- **Mixed session (thinking on → off, DD8):** in a chat that already has thinking+tool turns
  (steps 3–7), turn the **Extended thinking toggle OFF** and send another tool-inducing message
  → the turn completes with **no API error** (the stored signed thinking blocks are stripped
  from the thinking-off request, not replayed onto it) and no new thinking disclosure appears
  for that turn. Guards the DD8 strip-when-off replay contract that a fixtured test can only
  approximate.
- **Plan provider (M19 F01):** input deltas — the agent uses an **Anthropic (Plan)**
  (`anthropic-plan`) provider that is connected (`oauth_active: true`, real Pro/Max sign-in)
  instead of the API-key provider; the "Anthropic API key stored" precondition is replaced by
  "the plan provider shows connected in Settings › Providers". Everything else (steps, observables,
  expected results) is identical — this variant is the extended-thinking half of Mission 19's
  chat-parity criterion, run during the M19 F01 HAT session.
