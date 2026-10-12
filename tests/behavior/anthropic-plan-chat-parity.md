# Behavior Test: Anthropic Plan Provider Chat Parity

**Slug**: `anthropic-plan-chat-parity`
**Status**: active
**Created**: 2026-07-28
**Last Run**: 2026-07-30-17-10-08 (PASS 5/5 on claude-haiku-4-5 — see `anthropic-plan-chat-parity/runs/2026-07-30-17-10-08.md`; Sonnet/Opus blocked account-side per mission known issue)
**Updated**: 2026-10-05 (M25 F4 leg 8: steps 2 and 5 start the chat through New chat and the agent picker)

## Intent

Verify that an agent bound to an authenticated Anthropic individual-plan provider completes real chat turns — plain response, streaming, and tool use — indistinguishably from an agent on the API-key Anthropic provider. This needs a behavior test because it exercises live inference against Anthropic's API with subscription OAuth credentials through the full agent loop and rendered chat UI — the parity claim is about real-environment behavior no mocked test can establish.

## Preconditions

- the-one dev instance is running on a **non-default port with a scratch data
  directory** and the web UI loads in a browser — never the operator's default `:8484`
  instance (see CLAUDE.md's "Behavior-test credential convention" safety rule).
- An authenticated `anthropic-plan` provider (labelled "Claude Plan (OAuth)" in the type list) exists and shows as connected in Library › Model providers (active probe: run this test only after `anthropic-plan-signin` passed in the same session, or the operator confirms the connected state in the editor immediately before the run).
- An agent exists (or is created on the Agents destination at run time) bound to the plan provider with a current Claude model selected, with at least one built-in tool enabled that produces a deterministic, observable result. The operator names the chosen tool before the run (recorded in the run log); step 4's prompt targets that tool.
- **Credential**: this instance is gated (Mission 20 Flight 1). Reach it per CLAUDE.md's
  "Behavior-test credential convention" — a handoff-authenticated navigation for the
  browser session (single-use; re-mint per navigation) and `Authorization: Bearer
  <credential>` for the shell restart-verification in step 5.

## Observables Required

- browser (rendered Studio and Chat UI — measured via chrome-devtools or goldfinch MCP)
- shell (app restart in step 5 — measured via Bash / operator terminal)

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | On the Agents destination, open (or create) the test agent; set its provider to the plan provider and pick a model from the model dropdown. | The model dropdown for the plan provider is populated with Claude models; the selection saves without error. |
| 2 | On Chats, start a new chat with the test agent (the Chats list's **New chat**, `chats-new-btn`, then pick the agent in the agent picker) and send: "Reply with exactly the word PONG." (this first send creates the chat). | A reply appears in the chat transcript containing "PONG". No error banner or failed-turn indicator appears. |
| 3 | Send a prompt that elicits a longer response (e.g. "Explain in ~150 words why the sky is blue."). Capture the transcript at least twice while the reply is being produced, then once after it completes. | Two successive in-flight captures show strictly growing reply text, OR at least one mid-generation capture shows a rendered streaming/typing indicator (accepted alternative when the reply completes quickly); the final capture shows a complete assistant turn with no truncation or error indicator. |
| 4 | Send a prompt that requires the tool named in the preconditions. | The transcript shows the agent invoking that tool and a final reply consistent with the tool's result; no tool-call failure is shown. |
| 5 | Restart the app (operator runs the restart from the terminal), reopen Chats, start a new chat with the same agent through **New chat** and the agent picker, and send: "Reply with exactly the word AGAIN." | After restart, the reply containing "AGAIN" appears without any re-authentication prompt — stored credentials survived the restart. `[mixed-frame]` — the restart is a shell action verifying an internal persistence contract with a browser-observable outcome. |

## Out of Scope

- Sign-in flow and credential storage/leak checks — covered by `anthropic-plan-signin`.
- Extended thinking — covered by the plan-provider variant of `extended-thinking-tool-turn` (run alongside this spec at HAT); per-feature request-parameter coverage stays with the unit conformance suites.
- Plan usage limits / rate-limit behavior — explicitly out of mission scope.
- Side-by-side output comparison with the API-key provider — parity here means the same capabilities complete successfully, not identical text.
