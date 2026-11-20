# Behavior Test: GleepGlorp Attaches an MCP Server, and the Open Editor Follows

**Slug**: `gleepglorp-proposal-attach-mcp`
**Status**: draft
**Created**: 2026-11-19 (Mission 36 Flight 2 Leg 6)
**Last Run**: never

## Intent

Verifies, with a real model in a real chat, that GleepGlorp can propose attaching an existing MCP
server to an existing agent, that Approve applies it to the agent, and that an agent editor the
operator already has open on that agent follows the approval (Leg 7): the attached server shows
in the Tools tab with the note that a change the operator approved in a GleepGlorp chat made it,
with no unsaved-edit prompt.

Unit tests prove the apply and the editor's rebase. They cannot prove that a real model finds an
existing server by name from `read_app_config`, proposes only the `mcp_servers` field, and that
the card and the editor agree in one browser window.

## Preconditions

- A dev instance built from the flight branch, on a dedicated non-default port (8486 or higher,
  assigned per run; never 8484 or 8485) with a **scratch data directory** under `$HOME`. Start it
  from a scratch working directory with `THE_ONE_DEV_MODE=true`. Follow CLAUDE.md
  "Behavior-test credential convention" for the credential file and the browser handoff.
- A real Claude provider (`Claude Plan (Token)`, token from
  `~/.config/the-one-evals/plan-token`, model `claude-haiku-4-5`) and GleepGlorp set to it, so
  `GET /api/gleepglorp` answers `"state": "ready"`.
- An agent `bt-agent` exists on that provider with no MCP servers attached.
- An MCP server `bt-docs` exists (Library > MCP servers), for example a streamable-http server at
  `http://127.0.0.1:9/mcp` (it never needs to connect: attaching is a stored change). It is
  attached to no agent.
- A browser apparatus can reach the dev instance.

## Observables Required

- **browser**: the Chats transcript and the proposal card, and the agent editor's Tools tab.
- **http**: `GET /api/gleepglorp/proposals?session_id={SESSION}`, `GET /api/agents/bt-agent`.

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | In the browser, open Agents, then `bt-agent`, then its Tools tab. Leave the editor open on that route. | The Tools tab shows `bt-docs` as an available server, not attached. The editor shows no unsaved-change caption. |
| 2 | Open Chats, choose New chat, pick **GleepGlorp**, and send: "Attach the MCP server bt-docs to the agent bt-agent. Do not change anything else." Record the session id as `{SESSION}`. Wait up to 120 s for the turn to end. | One `proposal-card` after the reply, `data-state="pending"`, titled "Change agent “bt-agent”". Its table has two columns (Now, Proposed) and one row, "MCP servers", reading None and `bt-docs`. The footer reads "Only this field changes." |
| 3 | Read `GET /api/gleepglorp/proposals?session_id={SESSION}` and `GET /api/agents/bt-agent`. | The route lists one `pending` proposal whose `changes` name `bt-docs` and no other field. `bt-agent`'s `mcp_source_ids` is still empty. |
| 4 | Click `proposal-approve`. Wait up to 120 s for the continuation turn to end. | The card folds to `data-state="applied"` with a summary that names MCP servers. One `chat-approval-line` shows. No bubble begins "Approved proposal". |
| 5 | Read `GET /api/agents/bt-agent`. | `mcp_source_ids` holds the id of `bt-docs`. No other field of the agent changed (its description, prompt, model and tools are as before). |
| 6 | Click the applied card's `proposal-open-agent` link. | The browser goes to `#agents/bt-agent`. The editor for `bt-agent` is showing, without a reload. |
| 7 | Open the Tools tab. (If the editor from step 1 is still mounted in the same window, it is the one shown; do not reload.) | `bt-docs` is shown attached. A note beside it reads "Changed by a change you approved in a GleepGlorp chat" with a time and an "Open chat" link. The editor has no unsaved-change caption and no leave prompt appears when navigating away. |
| 8 | Click the note's "Open chat" link. | The browser goes to the chat `{SESSION}` and the applied card is shown. |

## Out of Scope

- Creating an agent through a proposal (`gleepglorp-proposal-create-agent`).
- Editors for rules and routines following an approval, and the placement of the note under the
  General fields, the model picker and the Knowledge tiles. The HAT checks those.
- The stale, failed and withdrawn card states (`tests/browser/test_flow_chat_proposals.py`).
- What GleepGlorp says, and whether it asks which server first.

## Variants

- **Edit before approving**: after step 1, type in the editor's Description field without saving,
  then approve in the chat. The unsaved Description edit is kept and the MCP change shows (Leg 7's
  rebase rules); the editor stays dirty only for the Description.
