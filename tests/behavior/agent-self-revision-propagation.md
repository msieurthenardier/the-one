# Behavior Test: Agent Self-Revision Propagation

**Slug**: `agent-self-revision-propagation`
**Status**: draft
**Created**: 2026-08-11
**Last Run**: 2026-08-25 (partial → spec corrected; see run logs)

## Intent

Verifies that an agent revising its own system prompt actually changes its own
behavior, and that the two propagation timings mean what they say. This resists
unit testing for a reason that is structural rather than incidental: **no read
path anywhere exposes a running agent's system prompt.** `session_joined` carries
history, title, agent name and routing metadata but not the prompt, and
`GET /api/agents/{name}` returns the stored row — which proves the revision
persisted and says nothing about whether a *running* agent is behaving by it. A
unit test can assert that the deferral hook fires; it cannot show a real model
obeying the new prompt.

### Observability discipline — read before editing this spec

The 2026-08-25 run established, with server-side instrumentation, two facts that
shape every assertion here:

1. **The propagation mechanism is correct.** On rejoin, `_restore_session`
   rebuilds the live agent from the current stored row, so the agent that
   processes the next message genuinely holds the revised system prompt. This was
   confirmed directly (the rebuilt agent's `messages[0]` carried the new prompt).
2. **A sentinel in the agent's replies is only a *reliable* observable on the
   first turn of a FRESH conversation.** Inside a conversation that already has
   turns, the model anchors on its own recent replies and on the revision tool
   call's arguments (which necessarily carry the new prompt text into the
   transcript) far more strongly than on a freshly-swapped system instruction. In
   the first run, a reopened conversation whose live prompt had genuinely been
   updated still would not emit the new sentinel — and, asked outright to read
   its current instructions, reported the *old* sentinel. That is a model-
   behavior artifact, not a propagation failure.

Therefore this spec measures `next_session` propagation the only way that is not
confounded: **by opening a brand-new conversation** after the revision and
checking its first reply. It deliberately does **not** assert a sentinel change
inside the conversation that issued the revision — beyond the immediate "not this
turn" negative, which is a clean signal because nothing has yet changed. The
mid-turn-timing property of `next_turn` (that a revision does not land within the
turn that requested it) is likewise **not** asserted from replies here — the tool
call's arguments put the new sentinel into the turn's own context, so an output
check cannot distinguish "landed mid-turn" from "the model read its own tool
call." That property is covered by the unit test (scripted-LLM, asserts the
deferral hook applies only at iteration-loop exit).

## Preconditions

- A dev instance of the app is runnable on a non-default port. **Never target
  port 8484** — that is the operator's production instance.
- The instance uses a scratch data directory, not the operator's real one.
- The credential gate is enforced (identity resolution is meaningless with it
  off).
- A test agent exists with a working LLM provider, capable of completing a real
  turn, and with a system prompt that does **not** already contain either
  sentinel word used below (`NAUTILUS`, `WOMBAT`).
- The self-configuration surface is **enabled** on that agent, and its
  `update_my_system_prompt` capability is left enabled in the agent's MCPs tab.
- A browser apparatus is available and can reach the dev instance.

## Observables Required

- **browser** (rendered chat transcript — the agent's replies are the only
  surface on which propagation is visible) — measured via the registered browser
  apparatus
- **http** (stored configuration, to separate persistence from propagation) —
  measured via shell

## Steps

Two sentinels are used so the two conversations never share a target word:
`NAUTILUS` for the `next_session` leg, `WOMBAT` for the `next_turn` leg.

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | Open the dev instance in the browser, navigate to Chat, and start a new conversation (call it **A**) with the test agent. Send "Hello, introduce yourself briefly." | The agent replies with ordinary prose. The reply does **not** contain `NAUTILUS`. |
| 2 | In conversation **A**, send: "Using your self-configuration tools, revise your own system prompt so that you end every future reply with the single word NAUTILUS on its own line. Apply it from the next session, not the next turn." | The agent reports that it revised its system prompt and that the change applies from the next session. |
| 3 | In conversation **A**, send "Say something short." | The reply does **not** end with `NAUTILUS`. Load-bearing negative: a `next_session` revision must not reach the conversation that made it. |
| 4 | Fetch the agent's stored configuration over HTTP. | The stored system prompt **does** contain the `NAUTILUS` instruction — the revision persisted even though the issuing conversation is not honoring it. This is what separates persistence from propagation. |
| 5 | Start a **brand-new** conversation (call it **B**) with the same agent — do **not** reuse conversation A. Send "Say something short." | The reply ends with `NAUTILUS`. A conversation opened after the revision picks up the stored prompt on construction, exactly as `next_session` names. This is the reliable, unconfounded observable for next-session propagation. |
| 6 | In conversation **B**, send: "Using your self-configuration tools, revise your system prompt again so you end every reply with the word WOMBAT instead of NAUTILUS. Apply it from the next turn." | The agent reports the revision and that it applies from the next turn. (No assertion on this turn's final line — the tool call's arguments carry `WOMBAT` into this turn's own context, so the reply's last word is not a clean signal here; the next step is.) |
| 7 | In conversation **B**, send "Say something short." | The reply ends with `WOMBAT`. `next_turn` took effect on the following turn of the same open conversation, with no rejoin. |
| 8 | In conversation **B**, ask the agent to retrieve its own configuration and show what it received. | The response contains the agent's description, system prompt and model, and contains **no** secret material — no bearer token, no header value, no environment variable value, no credential of any kind. |

## Out of Scope

- Operator approval mode, the pending queue, the revision log and restore —
  Flight 2. Every revision in this test applies directly.
- External MCP client access and credential revoke/rotate — Flight 3.
- Whether the agent can be *induced* to revise itself adversarially. The
  indirect-prompt-injection axis is the mission's named residual risk, not a
  property this test asserts.
- Writes to any field other than description and system prompt. Those are
  unreachable by catalog shape (no tool addresses them), which is a unit-level
  assertion — there is no denied write to attempt here.
- **Mid-turn non-application of `next_turn`**, and **whether a *reopened* existing
  conversation visibly changes its replies.** Both are confounded at the reply
  level (see the Observability discipline note above): the first is covered by the
  unit test; the second is a property of the model's history-anchoring, not of the
  propagation code, which is verified correct out-of-band and by the fresh-
  conversation check in step 5.

## Variants (optional)

- **description-instead-of-prompt**: same shape as steps 2–5 using
  `update_my_description`. Weaker signal — a description change is not
  behaviorally visible in replies, so the assertion falls back to the stored row,
  which unit tests already cover. Run only if description propagation is
  suspected to diverge from prompt propagation.
