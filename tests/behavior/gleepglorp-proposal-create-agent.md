# Behavior Test: GleepGlorp Proposes a New Agent, Then a Second Step

**Slug**: `gleepglorp-proposal-create-agent`
**Status**: draft
**Created**: 2026-11-19 (Mission 36 Flight 2 Leg 6)
**Last Run**: never

## Intent

Verifies, with a real model in a real chat, that GleepGlorp can propose creating an agent, that
the operator's approval on the proposal card creates it, and that the approval continues the
chat so a request with two steps (create the agent, then add a rule to it) finishes one step at a
time, each step behind its own approval.

Unit tests prove the write services, the routes and the card's states. They cannot prove that a
real model reads the "continue with the next step" message, proposes the second change from it,
or that the card, the quiet line and the busy buttons work together in a live turn. That is what
this test is for.

Model wording is never asserted. The test asserts the card's states and testids, the proposals
route and the stored agent and rule.

## Preconditions

- A dev instance built from the flight branch, on a dedicated non-default port (8486 or higher,
  assigned per run; never 8484 or 8485) with a **scratch data directory** under `$HOME`. Start it
  from a scratch working directory with `THE_ONE_DEV_MODE=true`. Follow CLAUDE.md
  "Behavior-test credential convention" for the credential file and the browser handoff.
- A real Claude provider exists in the scratch instance: a `Claude Plan (Token)` provider
  (`anthropic-plan-token`) whose token is read from `~/.config/the-one-evals/plan-token` (the
  evals' plan token), model `claude-haiku-4-5`. Create it through Library > Model providers and
  check "Test connection" passes.
- GleepGlorp is on and set to that provider and model (Settings > GleepGlorp), so
  `GET /api/gleepglorp` answers `"state": "ready"`.
- No agent named `bt-digest` exists. At least one other agent may exist.
- A browser apparatus can reach the dev instance.

## Observables Required

- **browser**: the Chats transcript and the proposal card (`proposal-card` and its testids), the
  Agents list and the agent's Rules and notes tab.
- **http**: `GET /api/gleepglorp/proposals?session_id={SESSION}`, `GET /api/agents/bt-digest`,
  `GET /api/agents/bt-digest/rules`.

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | In the browser, open Chats, choose New chat, pick **GleepGlorp** (the "Built in" group), and send: "Create an agent called bt-digest with the description 'Summarises my day'. Do not change anything else." Record the chat's session id as `{SESSION}`. Wait up to 120 s for the turn to end (Stop is gone). | The transcript shows GleepGlorp's work and a reply. After the reply there is one `proposal-card` with `data-state="pending"`, titled "Create agent “bt-digest”" (`proposal-title`). Its table (`proposal-table`) has one column and lists Name `bt-digest` and Description `Summarises my day`. The footer reads "Other settings keep their defaults." `proposal-approve` and `proposal-dismiss` are enabled. No error is shown. |
| 2 | Read `GET /api/gleepglorp/proposals?session_id={SESSION}` and `GET /api/agents/bt-digest`. | The route lists one proposal with `status: "pending"`, `kind: "agent"`, `action: "create"` and a `title` of "Create agent “bt-digest”". `GET /api/agents/bt-digest` is 404: nothing was created by proposing. |
| 3 | Click `proposal-approve`. | The card goes to `data-state="applied"` (folded to one line `proposal-status-line` reading "Applied" and a summary naming `bt-digest`, with `proposal-open-agent` and `proposal-details`). The log shows one `chat-approval-line` reading "You approved this change. GleepGlorp is continuing." and **no** user bubble with the text "Approved proposal". [a11y] Focus is on the card's "Open agent" link. |
| 4 | Read `GET /api/agents/bt-digest`. | 200, `description` is `Summarises my day`, and `name` is `bt-digest`. |
| 5 | Wait up to 120 s for GleepGlorp's continuation turn to end. | While the turn runs, the composer shows Stop. When it ends, GleepGlorp has replied (the wording is not asserted). No second proposal exists yet: the user asked for one step. |
| 6 | Send: "Now add a rule to bt-digest: 'Keep every reply under 50 words.' Then say done." Wait up to 120 s for the turn to end. | A second `proposal-card` appears after the new reply, `data-state="pending"`, titled "Add a rule to “bt-digest”", with a one-column table listing the rule text. The first card is still folded as applied and is above it. |
| 7 | While a turn is running (send "Say hi." and check at once, before it ends), look at the open card's buttons. Then wait for the turn to end. | While the turn runs the card's `proposal-approve` and `proposal-dismiss` are disabled and the card shows "Wait for GleepGlorp to finish." After the turn ends they are enabled again. |
| 8 | Click `proposal-approve` on the second card. Wait for the continuation turn to end. | The card folds to "Applied". A second `chat-approval-line` appears. `GET /api/agents/bt-digest/rules` returns one rule whose text is `Keep every reply under 50 words.`. |
| 9 | Reload the page and reopen the chat. | Both cards are in place after the turn that made them, both folded as applied, and both `chat-approval-line`s show. There is no bubble that begins "Approved proposal". Open **Details** on the first card: a table shows Name and Description. |
| 10 | Open Agents, then `bt-digest`, then the Rules and notes tab. | The agent exists with its description, and its rule list shows the rule from step 8. |

## Out of Scope

- Attaching an existing MCP server to an agent, and the editors following an approval
  (`gleepglorp-proposal-attach-mcp`).
- The Dismiss, Try again and Approve anyway paths, the stale and failed states and the refused
  clicks. They are covered by `tests/browser/test_flow_chat_proposals.py`, which seeds the proposals.
- What GleepGlorp says. Wording, tone and whether it asks a question first are model behaviour and
  are tuned in the eval legs.
- Proposals made after content from a tool GleepGlorp does not trust (the "Check this" flag): it
  needs a scripted source and is unit tested.

## Variants

- **Dismiss instead of approve** (step 3): click `proposal-dismiss`. The card becomes a quiet
  "Dismissed" line, no `chat-approval-line` appears, no agent is created, and GleepGlorp does not
  start a turn.
