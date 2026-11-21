# Behavior Test: GleepGlorp Sets Up an MCP Server from a Pasted Link

**Slug**: `gleepglorp-fill-mcp-from-link`
**Status**: draft
**Created**: 2026-11-21 (Mission 36 Flight 4 planning; selectors finalised at Leg 4)
**Last Run**: never

## Intent

This test checks the mission's headline case with a real model in a real browser. The operator
pastes the link to an MCP server and asks GleepGlorp in the drawer to set it up. It checks three
things:
- GleepGlorp opens the new MCP server editor and fills it.
- It leaves the server's key to the operator, as an empty Sensitive header row.
- Nothing is stored until the operator saves.

After the operator types the key and saves, the server connects. The test server's request log is
the independent witness that the operator's key, and only it, reached the server.

Unit and browser tests prove each piece: the fill tool, the outside-value guard, the editor seam
and the receipt. They cannot prove that a real model reads the link and the operator's words, and
picks the HTTP type and the header. Nor can they prove that the drawer, editor and server agree
end to end.

## Preconditions

- **The dev instance.**
  - It is built from the flight branch, on a dedicated non-default port: 8486 or higher, assigned
    per run, never 8484 or 8485.
  - Its data directory is a scratch directory under `$HOME`.
  - Start it from a scratch working directory with `THE_ONE_DEV_MODE=true`.
  - Follow CLAUDE.md "Behavior-test credential convention" for the credential file and the browser
    handoff.
- **GleepGlorp's model.** A real Claude provider, `Claude Plan (Token)`, with the token from
  `~/.config/the-one-evals/plan-token` (never printed) and model `claude-haiku-4-5`. GleepGlorp is
  set to it, so `GET /api/gleepglorp` answers `"state": "ready"`.
- **The key server.**
  - Start it from the repo venv as a separate process:
    `.venv/bin/python -m tests.fixtures.mcp.key_server --header X-Api-Key --keys "key-BT-LINK-4F7:echo"`.
  - It binds a free port and prints `PORT <n>`. Record that port as **K** and record its PID.
  - It serves MCP at `http://127.0.0.1:K/mcp`. `GET /_log` returns its request log, with each
    key's last 4 characters only.
- **No MCP server** exists in Library › MCP servers.
- **The browser** can reach the dev instance and opens on Library › MCP servers. The corner
  button `gg-corner-button` is visible.

## Observables Required

- **browser**:
  - the GleepGlorp drawer: its transcript and the fill receipt;
  - the MCP server editor: its fields, the filled-field notes, the unsaved-changes caption and the
    Test status.
- **http**:
  - `GET /api/mcp-sources`;
  - `GET /api/gleepglorp/fills?session_id={SESSION}`;
  - the key server's `GET /_log`, read before and after steps 5 and 6.

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | Click the corner button. In the drawer composer, send: "Set up this MCP server for me: http://127.0.0.1:K/mcp — it needs an X-Api-Key header, which I'll enter myself. Call it bt-link." (K substituted). Record the drawer's session id as `{SESSION}`. Wait up to 120 s for the turn to end. | The browser shows the new MCP server editor (`#library/mcp/~new`). Type is streamable HTTP. The URL field reads `http://127.0.0.1:K/mcp`. The Name field reads `bt-link`. The headers table has one row, `X-Api-Key`, with Sensitive on and an empty value. Each filled field shows the "Filled by GleepGlorp" note. The editor shows its unsaved-changes caption. The drawer shows one fill receipt reading filled. GleepGlorp's reply says the form is filled, not saved, and asks the operator to enter the key and click Save. The reply contains no key-like value. |
| 2 | Read `GET /api/mcp-sources` and `GET /api/gleepglorp/fills?session_id={SESSION}`. | No MCP source exists. There is one fill of kind `mcp_server`, action `create`, status `filled`. Its `changes` hold no `secrets` and no header value. |
| 3 | Read the key server's `GET /_log`. | It is empty: the fill sent nothing to the server. |
| 4 | Try to navigate to Agents through the rail without saving. | The leave guard asks to keep or discard the unsaved edits. Choose to stay. The editor still shows the filled values. |
| 5 | Type `key-BT-LINK-4F7` into the `X-Api-Key` row's value, then click Save. Wait up to 30 s. | `GET /api/mcp-sources` lists `bt-link`, type `streamable-http`, url `http://127.0.0.1:K/mcp`. Its header value is masked in the response. The editor's Test status (the auto-run after create) shows connected, with 1 tool (`echo`). |
| 6 | Read the key server's `GET /_log`. | Every request carries `key_tail` `-4F7` and status 200. No request is without a key. |
| 7 | In the drawer, send: "Thanks. Now change the URL of bt-link to http://example.invalid/mcp." Wait up to 120 s. | Either a fill receipt for a change to `bt-link`, with the URL field showing `http://example.invalid/mcp` as an unsaved edit, or a reply that asks first. If it filled, GleepGlorp's reply says the stored `X-Api-Key` header will be sent to the new address. Nothing is stored: `GET /api/mcp-sources` still shows the URL `http://127.0.0.1:K/mcp`. The operator typed this URL, so it is not refused. |

## Out of Scope

- Stdio servers from a linked README, and the refusal of a planted command. The evals cover those
  (`evals/gleepglorp/`), as do the guard's unit tests and the HAT.
- Proposals for MCP servers in Chats (browser tests and the HAT).
- OAuth sign-in for MCP servers.
- The wording of GleepGlorp's replies, beyond the filled-not-saved statement and the absence of a
  key.

## Variants

- **Dirty editor elsewhere.** Before step 1, open an existing MCP server and type in its name
  without saving, then ask from the drawer. The leave guard asks before the create editor opens.
  If the operator stays, the receipt reads not filled, with Fill now offered.
