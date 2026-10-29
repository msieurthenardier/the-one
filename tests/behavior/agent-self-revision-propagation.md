# Behavior Test: Agent Self-Revision Propagation

**Slug**: `agent-self-revision-propagation`
**Status**: active
**Created**: 2026-08-11
**Last Run**: 2026-10-14 (pass, 8/8: corrected spec re-run fresh on a new instance; see runs/2026-10-14-15-57-27.md)
**Updated**: 2026-10-14 (M30 F2 live check: the conversation's persisted system message is named as the live-prompt observable; steps 3, 5, 6 and 7 assert on it or on the stored tool result; preconditions name a dedicated port and the model; re-run: step 7 allows the date to roll over, since the settle recomputes the date line)

## Intent

Verifies that an agent revising its own system prompt actually changes its own
behavior, and that the two propagation timings mean what they say. This resists
unit testing: a unit test can assert that the deferral hook fires; it cannot show
a real model obeying the new prompt.

`GET /api/agents/{name}` returns the stored row, which proves the revision
persisted and says nothing about whether a *running* agent holds it. The one read
path to the prompt a conversation's agent actually holds is that conversation's
**persisted system message**: `GET /api/chat/sessions/{id}` returns `messages`,
and `messages[0]` is the system message the conversation's agent carries (the
self-revision settle replaces `agent.messages[0]`, and `_session_notes_map` in
`interfaces/web/api.py` reads the same field as "the open chat's CURRENT system
prompt"). It is written when a turn is persisted, which happens **before** a
`next_turn` revision settles at the end of that turn — so after a `next_turn`
revision the persisted `messages[0]` shows the new prompt only once the
**following** turn has been persisted. It never shows a prompt mid-turn.
(`session_joined` carries history, title, agent name and routing metadata but not
the prompt.) The 2026-10-14 run is the first to use this observable; before it,
this spec wrongly said no read path existed.

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
3. **The anchoring confound also reaches the "not this turn" negative.** In the
   2026-10-14 run (gpt-oss:20b) the agent wrote the new sentinel into its own
   step-2 reply, in the very turn that made the `next_session` revision, and then
   ended its step-3 reply with it too — while conversation A's persisted
   `messages[0]` provably still lacked it. A reply-level negative inside the
   issuing conversation is therefore not clean either; step 3 asserts on the
   persisted system message instead.

Therefore this spec measures `next_session` propagation the only way that is not
confounded: **by opening a brand-new conversation** after the revision and
checking its first reply, and corroborates every propagation claim (steps 3, 5,
7) with the conversation's persisted system message (see Intent), which does not
depend on model output. It deliberately does **not** assert a reply sentinel
inside the conversation that issued the revision. The
mid-turn-timing property of `next_turn` (that a revision does not land within the
turn that requested it) is likewise **not** asserted from replies here — the tool
call's arguments put the new sentinel into the turn's own context, so an output
check cannot distinguish "landed mid-turn" from "the model read its own tool
call." That property is covered by the unit test (scripted-LLM, asserts the
deferral hook applies only at iteration-loop exit).

## Preconditions

- A dedicated dev instance of the app on a non-default port (8486 or higher,
  assigned per run). **Never target port 8484 or 8485** — 8484 is the operator's
  production instance, 8485 the Flight Director's preview.
- The instance uses a scratch data directory, not the operator's real one.
- The credential gate is enforced (identity resolution is meaningless with it
  off).
- A test agent exists with a working, tool-capable LLM provider, capable of
  completing a real turn (the 2026-10-14 run used local Ollama `gpt-oss:20b`; any
  tool-capable model will do), and with a system prompt that does **not** already contain either
  sentinel word used below (`NAUTILUS`, `WOMBAT`).
- The self-configuration surface is **enabled** on that agent, and its
  `update_my_system_prompt` capability is left enabled in the agent's Tools tab.
- A browser apparatus is available and can reach the dev instance.

## Observables Required

- **browser** (rendered chat transcript — the agent's replies are the only
  surface on which propagation is visible) — measured via the registered browser
  apparatus
- **http** (stored configuration, to separate persistence from propagation; a
  conversation's persisted messages, whose `messages[0]` is the system prompt the
  conversation's agent holds, and whose tool messages carry the self-revision
  tool results) — measured via shell

## Steps

Two sentinels are used so the two conversations never share a target word:
`NAUTILUS` for the `next_session` leg, `WOMBAT` for the `next_turn` leg.

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | Open the dev instance in the browser, navigate to Chats, and start a new conversation (call it **A**) with the test agent: click the Chats list's **New chat** (`chats-new-btn`), pick the test agent in the agent picker, and send "Hello, introduce yourself briefly." (this first send creates **A**). | The agent replies with ordinary prose. The reply does **not** contain `NAUTILUS`. |
| 2 | In conversation **A**, send: "Using your self-configuration tools, revise your own system prompt so that you end every future reply with the single word NAUTILUS on its own line. Apply it from the next session, not the next turn." | The agent reports that it revised its system prompt and that the change applies from the next session. |
| 3 | In conversation **A**, send "Say something short." When the turn completes, fetch conversation **A**'s stored session over HTTP (`GET /api/chat/sessions/{A id}`). | A's persisted system message (`messages[0]`) does **not** contain `NAUTILUS`. Load-bearing negative: a `next_session` revision must not reach the conversation that made it. (The reply's last line is **not** asserted: the agent may have written the sentinel into its own step-2 reply, and then anchors on it — see Observability discipline, point 3.) |
| 4 | Fetch the agent's stored configuration over HTTP. | The stored system prompt **does** contain the `NAUTILUS` instruction — the revision persisted even though the issuing conversation is not honoring it. This is what separates persistence from propagation. |
| 5 | Start a **brand-new** conversation (call it **B**) with the same agent — do **not** reuse conversation A: click **New chat** again and pick the same agent (a pick always starts a new pending chat). Send "Say something short." (this first send creates **B**). When the turn completes, fetch B's stored session over HTTP. | The reply ends with `NAUTILUS`, and B's persisted system message (`messages[0]`) contains the `NAUTILUS` instruction. A conversation opened after the revision picks up the stored prompt on construction, exactly as `next_session` names. This is the reliable, unconfounded observable for next-session propagation. |
| 6 | In conversation **B**, send: "Using your self-configuration tools, revise your system prompt again so you end every reply with the word WOMBAT instead of NAUTILUS. Apply it from the next turn." When the turn completes, fetch B's stored session over HTTP. | The agent acknowledges that it revised its system prompt, and the turn's stored `update_my_system_prompt` call has `apply: "next_turn"` with a result reporting `applied_to_store: true` and `effective: "next_turn"`. (The reply need not restate the timing — a terse model may not. No assertion on this turn's final line or on B's `messages[0]` yet: the tool call's arguments carry `WOMBAT` into this turn's own context, and the settle runs after this turn is persisted.) |
| 7 | In conversation **B**, send "Say something short." When the turn completes, fetch B's stored session over HTTP. | The reply ends with `WOMBAT`, and B's persisted system message (`messages[0]`) now carries the `WOMBAT` instruction and no longer the `NAUTILUS` one, with the platform-prompt part before the persona unchanged from step 6, and the date line after it unchanged apart from the date itself (the settle recomputes the date line, so a run that crosses midnight in the operator's time zone legitimately shows the new date). `next_turn` took effect on the following turn of the same open conversation, with no rejoin. |
| 8 | In conversation **B**, ask the agent to retrieve its own configuration and show what it received. Capture the reply scrolled into view. | The response contains the agent's description, system prompt and model, and contains **no** secret material — no bearer token, no header value, no environment variable value, no credential of any kind. |

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
- **The tool-free (degraded) system prompt** that a `next_turn` settle also
  rebuilds (Mission 30 Flight 2: `self_configuration/pending.py` refreshes both the
  tool-capable and the tool-free prompt). It is sent only to a model without tool
  support, which cannot drive this test's self-configuration tools, and it is
  never persisted in `messages[0]`; unit tests cover it.

## Variants (optional)

- **description-instead-of-prompt**: same shape as steps 2–5 using
  `update_my_description`. Weaker signal — a description change is not
  behaviorally visible in replies, so the assertion falls back to the stored row,
  which unit tests already cover. Run only if description propagation is
  suspected to diverge from prompt propagation.
