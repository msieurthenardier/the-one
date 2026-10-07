# Leg: mcp-error-message

**Status**: completed
**Flight**: [Alignment](../flight.md)

## Objective

When an MCP server cannot be reached, say so in plain words, and keep the technical
detail one click away (flight DD19). Two surfaces change:
- the agent editor's MCPs tab, where a source's tools fail to load;
- the Library MCP editor's connection result (Test connection, Refresh, the auto-run
  after create).

## Context

- **The operator's report** (2026-10-06). An enabled source on the agent MCPs tab shows:
  "Error loading tools: MCPConnectionError: MCP connect failed: cancelled during
  initialize (cross-task cleanup deadlock; original cause likely transport error or
  malformed initial response): Cancelled via cancel scope 29abb186b90". The operator
  called it "far from friendly".
- **Where the text comes from.** `POST /api/mcp-sources/{id}/test/connect`
  (`the_one/interfaces/web/api.py`, the `except` blocks at about lines 2963–2975 and
  3055–3066) returns `{"status": "error", "error": "{ExceptionClass}: {message}"}`. The
  classes are `MCPConnectionError`, `MCPVersionMismatch`, `MCPCapabilityMissing`,
  `MCPAuthRequired`, `SandboxError`, or anything else from the catch-all.
  - `MCPConnectionError`'s messages come from `the_one/mcp/client.py`, for example the
    timeout ("did not respond within N seconds during initialize") and the cancelled
    path (about line 399).
- **The two renderers:**
  - **The MCPs tab.** `studio.js` `fetchMcpSourceTools` (about line 2166) throws
    `new Error(data.error)`, or `'fetchMcpSourceTools: HTTP {status}'` on a non-OK
    response. `areas/studio/mcps-tab.js` (about lines 347 and 473, two copies) renders
    `'Error loading tools: ' + err.message` into `div.mcp-tools-error`
    (`mcp-tools-error-{id}`).
  - **The Library MCP editor.** `mcp-server-editor.js` (about line 2100) renders
    `'✗ Error: ' + escapeHtml(data.error)` through `innerHTML`. Its non-OK path (about line
    2016) builds "Server error {status} {statusText}: {body snippet}".
- **No backend change.** The API contract and the client's messages stay as they are.
  Recovering the original cause that the cancelled path hides is GitHub issue
  [#226](https://github.com/msieurthenardier/the-one/issues/226).
- **`MCPAuthRequired` and `auth_required`** keep their existing sign-in notice. This leg
  does not touch them.

## Acceptance Criteria

- [ ] **One shared helper** turns the raw error text into a plain message (for example
  `App.mcpErrorMessage(raw) -> {headline, detail}`, in an existing shared module or a
  small new script loaded before both renderers).
  - **The headline** is chosen by the leading class name, then by known phrases. The
    Flight Director's draft copy follows; adjust only for accuracy:
    - `MCPConnectionError` with "did not respond within": "The server didn't respond in
      time. Check that it's running, then try Refresh."
    - any other `MCPConnectionError`: "Couldn't connect to this server. Check that it's
      running and that its address and key are right, then try Refresh."
    - `MCPVersionMismatch`: "This server uses a protocol version the app doesn't support."
    - `MCPCapabilityMissing`: "This server doesn't offer the tools capability."
    - `SandboxError`: "The server couldn't start in its sandbox."
    - a non-OK HTTP response (`fetchMcpSourceTools: HTTP …`, `Server error …`): "The app
      couldn't check this server (the request failed)."
    - anything else: "Couldn't load this server's tools."
  - **The detail** is the raw text, unchanged.
- [ ] **Both surfaces render the same shape:**
  - the headline in the existing error colour;
  - a collapsed `<details>` labelled "Technical details" holding the raw text in a
    selectable, wrapping monospace block.
  - The MCPs tab keeps its `mcp-tools-error-{id}` testid on the error root, and its two
    copies share one builder.
  - The Library MCP editor's error is DOM-built (no `innerHTML`; the `test_ui_guards.py`
    sink baseline for `mcp-server-editor.js` can only go down, so update it if the guard
    requires).
  - The "Error loading tools:" and "✗ Error:" prefixes go.
- [ ] **Tests:**
  - **The helper:** a browser test evaluates it in the page for each class above, plus
    the operator's exact string and an unknown string.
  - **The MCPs tab:** intercept `**/api/mcp-sources/*/test/connect` to return
    `{"status":"error","error":"MCPConnectionError: MCP connect failed: cancelled during
    initialize (…)"}`. Assert:
    - the headline shows;
    - the raw text is inside a collapsed `details`, and its text is present when
      expanded;
    - no "Error loading tools:" prefix remains.
  - **The Library MCP editor:** the same, through its Test connection or Refresh.
  - **Existing pins** of the old text are updated in place and noted in the flight log
    (grep `tests/` for `Error loading tools`, `✗ Error`, `mcp-tools-error`).
- [ ] **Docs.** `the_one/agents.md`'s MCP error-translation section gains a short note
  that the UI shows a plain headline and keeps the raw `"{Class}: {message}"` text under
  "Technical details".
- [ ] **Gates:**
  - the static guards;
  - `ruff`, and `TEST_TIMEOUT=3000 make test-unit`;
  - the `agents` and `library` lanes (`test_mcp_*` and `test_studio_mcps_tab` sit in
    `agents`; the MCP editor files sit in `library`);
  - `shared` (`TEST_TIMEOUT=3600`).

  All with `THE_ONE_TEST_NETNS=1`.

## Verification Steps

- The tests above, then the lanes.
- A screenshot of both surfaces with the operator's error string intercepted, in both
  themes, details closed and open (flight-log evidence only, never committed).

## Implementation Guidance

1. Read the two renderers, `fetchMcpSourceTools`, and the API's error envelope.
2. Write the helper and one DOM builder for the headline-plus-details block.
3. Switch both surfaces to it.
4. The tests and pins, then the docs.
5. The lanes; then mark the leg `landed` and signal `[LAND:leg]`.

## Edge Cases

- **A very long raw message:** the details block wraps (`overflow-wrap: anywhere`) and
  never widens the pane.
- **An empty or missing `error`:** the fallback headline, and no details block.
- **A Refresh that succeeds after an error:** the error block is replaced by the tool
  list, as today.

## Files Affected

- `the_one/interfaces/web/static/js/areas/studio/mcps-tab.js`,
  `areas/studio/mcp-server-editor.js`, the helper's home (and `index.html` plus the
  script-count pin in `tests/test_index_asset_cache_busting.py` if a script is added),
  and CSS in `studio.css`.
- Tests in the `agents` and `library` lanes, plus any pins.
- `the_one/agents.md`; the flight log.

## Citation Audit

Checked on 2026-10-06 in the working tree (legs 1a–2 landed):
- `api.py` envelopes: lines 2963–2975 and 3055–3066.
- `client.py`: the cancelled path, line 399.
- `studio.js`: `fetchMcpSourceTools`, line 2166.
- `mcps-tab.js`: lines 347 and 473.
- `mcp-server-editor.js`: lines 2016 and 2100.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
