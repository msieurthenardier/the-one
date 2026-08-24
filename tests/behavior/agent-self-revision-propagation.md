# Behavior Test: Agent Self-Revision Propagation

**Slug**: `agent-self-revision-propagation`
**Status**: draft
**Created**: 2026-08-11
**Last Run**: never

## Intent

Verifies that an agent revising its own system prompt actually changes its own
behavior, and that the two propagation timings mean what they say. This resists
unit testing for a reason that is structural rather than incidental: **no read
path anywhere exposes a running agent's system prompt.** `session_joined` carries
history, title, agent name and routing metadata but not the prompt
(`app.py:1199-1220`), and `GET /api/agents/{name}` returns the stored row — which
proves the revision persisted and says nothing about whether the live
conversation picked it up. A unit test can assert that a deferral hook fires; it
cannot distinguish "the prompt was written to the database" from "the running
agent is now behaving by it."

The distinction matters most in the negative direction. `next_session` must
**not** take effect in the open conversation, and `next_turn` must **not** take
effect mid-turn — the operator ruled out immediate application specifically
because a prompt changing underneath a turn in progress produces incoherent
output. Both are assertions that something did *not* happen while the
conversation stayed live, which only a live conversation can make.

## Preconditions

- A dev instance of the app is runnable on a non-default port. **Never target
  port 8484** — that is the operator's production instance.
- The instance uses a scratch data directory, not the operator's real one.
- The credential gate is enforced (identity resolution is meaningless with it
  off).
- A test agent exists with a working LLM provider, capable of completing a real
  turn, and with a system prompt that does **not** already contain the sentinel
  phrase used below.
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

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | Open the dev instance in the browser, navigate to Chat, and start a new conversation with the test agent. Send "Hello, introduce yourself briefly." | The agent replies with ordinary prose. The reply does **not** contain the word `PELICAN`. |
| 2 | In the same conversation, send: "Using your self-configuration tools, revise your own system prompt so that you end every future reply with the single word PELICAN on its own line. Apply it from the next session, not the next turn." | The agent reports that it revised its system prompt and that the change applies from the next session. Its reply in this turn does **not** end with `PELICAN`. |
| 3 | In the same conversation, send "Say something short." | The reply does **not** end with `PELICAN`. This is the load-bearing negative: a `next_session` revision must not reach the conversation that made it. |
| 4 | Fetch the agent's stored configuration over HTTP. | The stored system prompt **does** contain the `PELICAN` instruction — the revision persisted even though the live conversation is not honoring it. Persistence and propagation are separable, and this step is what separates them. |
| 5 | Leave the conversation (navigate to another agent or another view) and rejoin the same conversation. Send "Say something short." | The reply now ends with `PELICAN`. The revision took effect on session rebuild, exactly as `next_session` names. |
| 6 | In this conversation, send: "Using your self-configuration tools, revise your system prompt again so you end every reply with the word WALRUS instead of PELICAN. Apply it from the next turn." | The agent reports the revision and that it applies from the next turn. Its reply for **this** turn still ends with `PELICAN`, not `WALRUS` — the revision must not land mid-turn, even though the tool call happened inside this turn. |
| 7 | In the same conversation, send "Say something short." | The reply ends with `WALRUS`. `next_turn` took effect on the following turn of the same open conversation, with no rejoin. |
| 8 | In the same conversation, ask the agent to retrieve its own configuration and show what it received. | The response contains the agent's description, system prompt and model, and contains **no** secret material — no bearer token, no header value, no environment variable value, no credential of any kind. |

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

## Variants (optional)

- **description-instead-of-prompt**: same shape as steps 2–5 using
  `update_my_description`. Weaker signal — a description change is not
  behaviorally visible in replies, so the assertion falls back to the stored row,
  which unit tests already cover. Run only if description propagation is
  suspected to diverge from prompt propagation.
