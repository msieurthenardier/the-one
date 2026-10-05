# Behavior Test: Jump-to Palette — Ctrl K and the rail control reach anything

**Slug**: `jump-to-palette`
**Status**: draft
**Created**: 2026-10-05
**Last Run**: never

> **Draft (Mission 25 Flight 4 planning).** The step table fixes the observables and the
> flow. It is finalized against the shipped build in leg 6.

## Intent

Verify Mission 25 SC5 and the jump-to half of SC2:
- a keyboard shortcut (Ctrl K) and a visible rail control open a jump-to palette;
- it finds agents, conversations, the New chat action, Library items (knowledge bases, MCP
  servers, connectors) and Settings pages, and opens the one chosen;
- a pick made from a dirty editor asks first.

This is a behavior test because it needs:
- real key events, reaching the page from inside text fields;
- the modal's focus and active-row keyboard model;
- landing on the right item across all four destinations, through the leave guard.

It runs in both themes and creates data prefixed `jtp-`.

## Preconditions

- **Instance under test.** A dedicated dev instance with a non-default port AND a scratch
  data directory, with dev mode on.
  - **Never** port 8484, and never the operator's default data directory.
  - The orchestrator states `{base}` at run time.
- **Probes:** `GET {base}/api/live` returns 200, and `GET {base}/api/providers/types` lists
  `mock`.
- **Credential.** As CLAUDE.md describes.
- **Clean start.** Nothing prefixed `jtp-` exists.
- **Browser apparatus.** A headless Chromium driven over CDP with **real key events**:
  `Input.dispatchKeyEvent` or the Playwright keyboard, never synthetic `dispatchEvent`.
  Each variant uses a fresh context.

## Observables Required

- browser: DOM, accessibility tree (`aria-activedescendant`), `location.hash`,
  `document.activeElement`, `dialog[open]` count and screenshots
- http: seed and teardown

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | **Seed (setup).** Create:<ul><li>a mock provider `jtp-mock`;</li><li>12 agents `jtp-agent-01`…`12`;</li><li>a knowledge base `jtp-kb`;</li><li>an MCP server `jtp-mcp` (stdio, the repo's `hello_server.py`);</li><li>a session titled `jtp chat about tiles` for `jtp-agent-02`;</li><li>a disabled Discord connector `jtp-conn` (seeded through the API, as the Flight 3 checkpoint did).</li></ul> | (setup row, no judgment) |
| 2 | Open `{base}/#agents` cold. Press **Ctrl+K**. | One dialog "Jump to" is open, with focus in its input. With the empty query it shows at most 8 results (the board's order). The footer reads "Ctrl K from anywhere" and "Enter to open". [a11y] |
| 3 | Type `tiles`. | A result "jtp chat about tiles" shows, with the where text "Chat · jtp-agent-02". The first result is the active row (`aria-activedescendant`). [a11y] |
| 4 | Press **Enter**. | The palette closes. The hash is `#chats/{that id}`, Chats is current, and the conversation is open. |
| 5 | Click the rail's **Jump to** control (`rail-jump-to`). Type `jtp-kb`, then press ↓ or ↑ as needed so the knowledge-base result is active, and press Enter. | The rail control opens the palette. The result reads "jtp-kb", with the where text "Library · Knowledge base". After Enter, the hash is `#library/knowledge/{id}`, with `jtp-kb` open beside the Library list. |
| 6 | Press Ctrl+K, type `mcp`, and open `jtp-mcp`. Then press Ctrl+K, type `jtp-conn`, and open it. | The MCP server lands on `#library/mcp/{id}`, with that server open. The connector result reads "jtp-conn", with the where text "Library · Connector", and lands on `#library/connectors/{id}`, with that connector open. |
| 7 | Press Ctrl+K, type `knowledge indexing`, and open it. | It lands on `#settings/knowledge-indexing`, with that page current in the Settings nav. |
| 8 | Press Ctrl+K, type `new chat`, and open "New chat…" (where "Action"). | It lands on Chats with the **agent picker** open. Exactly one dialog is open, and focus is in the picker's search. |
| 9 | Close the picker. Go to Agents, open `jtp-agent-03`, then type `jtp-agent-1` in the filter. Type into the agent's Description without saving, and press **Ctrl+K** while focus is in that field. | The palette opens even though focus was in a text field. The field keeps its text, because Ctrl+K inserted nothing. |
| 10 | Type `jtp-agent-07` and press Enter. | The palette closes first. Then exactly **one** "Unsaved changes" dialog opens, and the palette is not stacked under it. [a11y] |
| 11 | Click **Stay**. | The dialog closes. The hash is still `#agents/jtp-agent-03/…`, and the Description edit is kept. Focus returns to the palette's opener, the Description field that was focused at Ctrl+K, and not BODY. [a11y] |
| 12 | Press Ctrl+K, type `jtp-agent-07`, Enter, then choose **Continue**. | It lands on `#agents/jtp-agent-07/general`, with the editor showing. **The Agents filter is cleared**, so the row is visible and current. |
| 13 | Press Ctrl+K, then press **Escape**. | The palette closes, and focus returns to where it was before. [a11y] |
| 14 | **Teardown (setup row).** Delete the `jtp-` session, agents, knowledge base, MCP server, connector and provider, and restore the theme. | (setup row, no judgment) |

## Out of Scope

- **The picker and the pending-chat flow:** `start-a-chat`.
- **Palette ordering edge cases and the cap:** the contract and flow tests
  (`test_ui_search_list_contract`, `test_flow_jump_to*`).
- **The desktop shells** (WebKitGTK and WebView2 accelerators): the leg 5 probe and Flight 5.

## Variants

- **Theme.** Run the table in Light and in Dark, switching inside the variant's own fresh
  context before step 2. In both themes:
  - the palette's active row is distinguishable from the other rows;
  - the "where" text is legible;
  - the scrim reads as a scrim.
