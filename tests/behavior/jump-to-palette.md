# Behavior Test: Jump-to Palette — Ctrl K and the rail control reach anything

**Slug**: `jump-to-palette`
**Status**: active
**Created**: 2026-10-05
**Updated**: 2026-10-06 (M25 F6 leg 3, squawk 0122: wording only, no expectation changed: step 8's hash, step 9's Description selector, step 12's dialog count, the Variants' scrim alpha and the element the legibility check reads); 2026-10-06 (M25 F4 leg 9: step 2's empty-query expectation re-authored for the recent-chats/New chat…/recent-agents mix); 2026-10-05 (M25 F4 leg 8: finalized against the shipped build: testids, copy, routes, seeding and apparatus)
**Last Run**: 2026-10-06-14-00-21 — pass (a targeted re-run of steps 1, 2 and 14 in Light and Dark after M25 F4 leg 9, the empty-query mix; the full run 2026-10-06-06-01-26 passed 24/24)

## Intent

Verify Mission 25 SC5 and the jump-to half of SC2:
- a keyboard shortcut (**Ctrl K**) and a visible rail control (**Jump to**) open a jump-to
  palette, from any destination and from inside text fields;
- with an empty query it lists a useful starting mix (recent chats, New chat…, recently used agents);
- it finds agents, conversations, the New chat action, Library items (knowledge bases, MCP
  servers, connectors) and Settings pages, moves its active row with ↑ and ↓, and opens the
  one chosen with Enter;
- a pick made from a dirty editor closes the palette first and asks exactly once; Stay keeps
  the edit and returns focus to where it was.

This is a behavior test because it needs:
- real key events, reaching the page's `keydown` from inside text fields;
- the modal's focus and active-row keyboard model;
- landing on the right item across all four destinations, through the leave guard.

It runs in both themes (see Variants) and creates data prefixed `jtp-`.

## Preconditions

- **Instance under test.** A dedicated dev instance with a non-default port AND a **fresh**
  scratch data directory, with dev mode on, for example:

  ```
  THE_ONE_PORT=8488 THE_ONE_DATA_DIR=/tmp/the-one-jtp-scratch THE_ONE_DEV_MODE=true <repo>/.venv/bin/the-one serve
  ```

  Start it from a scratch working directory, not the repo root (`mkdir -p <scratch>/cwd && cd <scratch>/cwd`; CLAUDE.md "SAFETY RULE"), detached with the PID recorded; stop it by that PID.

  **Never** port 8484, and never the operator's default data directory (CLAUDE.md,
  "Behavior-test credential convention"). The orchestrator states `{base}` and the scratch
  directory at run time. The expectations are exact for a fresh instance: before step 1 it
  holds **no agents, chat sessions, knowledge bases, MCP servers or connectors** (the empty
  query's mix, and each typed query's matches, depend on it).
- **Probes:** `GET {base}/api/live` returns 200, and `GET {base}/api/providers/types` (with
  the credential) lists `mock`.
- **Credential.** As CLAUDE.md describes: the bearer for the API, and a handoff mint for each
  fresh browser context.
- **Browser apparatus.** A headless Chromium driven over CDP with **real key and pointer
  events**: Playwright's `page.keyboard` / `page.mouse`, or CDP `Input.dispatchKeyEvent` /
  `Input.dispatchMouseEvent`. Never a synthetic `dispatchEvent` or an `element.click()` from
  an eval: Ctrl K must reach the page as a trusted `keydown`. This is the project's behavior
  apparatus (Mission 25 Flight 3 DD12); goldfinch is not used while its input delivery is
  unverified. One fresh context per variant, viewport 1440×900. Press Ctrl K as the
  `Control+k` chord (on a macOS host the palette answers Meta K instead, and its copy reads
  "⌘ K"; run this spec on Linux or Windows).
- **Evidence notes.**
  - **Focus** is `document.activeElement` identity (tag, `data-testid`, `data-field`, `id`)
    through an eval, never a visible ring.
  - **Dialogs** are counted as `document.querySelectorAll('dialog[open]').length`. The
    palette is `[data-testid="jump-to"]`; the agent picker `[data-testid="agent-picker"]`;
    the leave-guard confirm `[data-testid="confirm-dialog-overlay"]`, with Stay
    `modal-cancel-btn` and Continue `modal-confirm-btn`.
  - **Results** are the `[data-testid="jump-to-result"]` rows in order, each with its
    label, its "where" text, `data-kind` and `data-id`. The active row is the one with
    `aria-selected="true"`, and the input's `aria-activedescendant` names its `id`.
  - Read `aria-current`, `aria-activedescendant`, field values and `location.hash` through
    DOM evals; the accessibility-tree dumps may omit them.
  - The palette refreshes as its data loads (it re-reads the chat list on every open), so
    wait until the expected rows render before reading a step's results.
  - Report only **rendered** error banners. No toast is expected; if one appears, its
    evidence is a screenshot, not `offsetParent` (a `position: fixed` element has a null
    `offsetParent`).
  - Screenshots: the palette with the empty query (step 2) and with an active row moved
    (step 3), per variant.

## Observables Required

- browser: DOM, accessibility tree (`aria-activedescendant`, `aria-selected`),
  `location.hash`, `document.activeElement`, the `dialog[open]` count and screenshots
- http: seed, the saved-value check (step 12) and teardown

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | **Seed (setup).** With the credential, expecting 201 for each POST: <ul><li>`POST {base}/api/providers` `{"name":"jtp-mock","type":"mock","base_url":"","config":{"models":["mock-default"]}}`; keep `{provId}`;</li><li>12 agents, `POST {base}/api/agents` `{"name":"jtp-agent-NN","provider_config_id":"{provId}","llm_model":"mock-default","system_prompt":"mock"}` for NN = 01…12 (zero-padded);</li><li>`POST {base}/api/knowledge-bases` `{"name":"jtp-kb"}`; keep `{kbId}`;</li><li>`POST {base}/api/mcp-sources` `{"name":"jtp-mcp","type":"stdio","config":{"command":"x","_cache":{"tools":[{"name":"echo","description":""}]}},"secrets":{}}`; keep `{mcpId}`;</li><li>a disabled Discord connector, `POST {base}/api/connectors` `{"name":"jtp-conn","type":"discord","config":{"enabled":false},"secrets":{}}` (it never reaches Discord); keep `{connId}`;</li><li>a session, `POST {base}/api/chat/sessions` `{"agent_name":"jtp-agent-02","title":"jtp chat about tiles","updated_at":U,"created_at":U,"platform":null}`, `U` an ISO-8601 UTC instant five minutes ago (the `seed_session` shape); keep `{chatId}`.</li></ul> | (setup row, no judgment) |
| 2 | In the variant's fresh context (its theme already set, see Variants), navigate to `{base}/#agents` and reload (cold). With nothing focused, press **Ctrl+K**. | Exactly one dialog is open: the palette (`jump-to`), named "Jump to" by `aria-label`, with no visible title. Focus is in its input (`jump-to-input`, placeholder "Jump to an agent, chat, library item or setting"), and the input bar ends with an "Esc" button (`jump-to-close`, accessible name "Close (Esc)"). With the empty query it shows exactly **8** results, in this order: "jtp chat about tiles" (`data-kind="chat"`, where text "Chat · jtp-agent-02"), "New chat…" (where text "Action"), `jtp-agent-02` (the one recently used agent), then `jtp-agent-01`, `jtp-agent-03`, `jtp-agent-04`, `jtp-agent-05`, `jtp-agent-06` (`data-kind="agent"`, where text "Agent"). The first (the chat) is active. The footer reads "Ctrl K from anywhere" and "Enter to open". [a11y] |
| 3 | Type `jtp-agent-1`. Press ↓ twice, read the active row; press ↑ once, read it; press ↓ three times, read it. Then select the whole query and type `tiles` in its place. | `jtp-agent-1` shows exactly 3 results, `jtp-agent-10`, `jtp-agent-11`, `jtp-agent-12`, with the first active. After ↓↓ the third (`jtp-agent-12`) is active; after ↑ the second (`jtp-agent-11`); after ↓↓↓ the third again: the active row stops at the last result, with no wrap. Each time `aria-activedescendant` names the row with `aria-selected="true"`, and focus stays in the input. `tiles` shows exactly one result, "jtp chat about tiles" with the where text "Chat · jtp-agent-02" (`data-kind="chat"`, `data-id` `{chatId}`), and it is active. [a11y] |
| 4 | Press **Enter**. | The palette closes. The hash is `#chats/{chatId}`, Chats is the current rail link, and the conversation is open: the chat header (`chat-header`) shows the `h1` "jtp chat about tiles" with "with jtp-agent-02", and its row (`chat-row[data-id="{chatId}"]`) has `aria-current="page"`. |
| 5 | Click the rail's **Jump to** control (`rail-jump-to`, accessible name "Jump to (Ctrl K)"). Type `jtp-kb` and press **Enter**. | The rail control opens the palette with focus in its input. `jtp-kb` shows one result, "jtp-kb" with the where text "Library · Knowledge base". After Enter the palette is closed, the hash is `#library/knowledge/{kbId}`, Library is the current rail link, and `jtp-kb` is open (its editor heading reads `jtp-kb`) beside the Library list, whose `jtp-kb` row (`knowledge-base-card`) has `aria-current="page"`. |
| 6 | Press Ctrl+K, type `jtp-mcp`, and press Enter. Then press Ctrl+K, type `jtp-conn`, and press Enter. | `jtp-mcp` shows "jtp-mcp" with the where text "Library · MCP server", and it lands on `#library/mcp/{mcpId}` with that server open and its row (`mcp-source-card`) current. `jtp-conn` shows "jtp-conn" with the where text "Library · Connector", and it lands on `#library/connectors/{connId}` with that connector open and its row (`connector-card`) current. No dialog other than the palette ever opens. |
| 7 | Press Ctrl+K, type `knowledge indexing`, and press Enter. | The result reads "Knowledge indexing" with the where text "Settings · Defaults for agents". It lands on `#settings/knowledge-indexing`, Settings is the current rail link, and "Knowledge indexing" (`settings-nav-knowledge-indexing`) is the current link (`aria-current="page"`) in the Settings navigation. |
| 8 | From Settings, press Ctrl+K, type `new chat`, and press Enter. | The result reads "New chat…" with the where text "Action" (`data-kind="action"`). After Enter it lands on Chats (the hash is `#chats/{chatId}`, the last chat open, with the picker over it) with the **agent picker** open (`agent-picker`, "Start a chat with…"): exactly one dialog is open (the palette is gone), and focus is in the picker's search (`agent-picker-search`). [a11y] |
| 9 | Press Escape to close the picker. Click the rail's **Agents** link and click the `jtp-agent-03` row. Type `jtp-agent-1` in the Agents filter (`agents-filter`). Click into the editor's Description (the field with `id` `studio-description`; it has no `data-testid`, so select it by `#studio-description`), type `unsaved jtp edit`, and, with focus still in Description, press **Ctrl+K**. | After the filter: the `jtp-agent-03` row is hidden and its editor stays open (`#agents/jtp-agent-03/general`). After the typing the editor shows "Unsaved changes" (`editor-unsaved`). Ctrl+K opens the palette even though focus was in a text field: one dialog, focus in `jump-to-input`. Description still holds exactly `unsaved jtp edit`: Ctrl+K inserted nothing. |
| 10 | Type `jtp-agent-07` and press Enter. | The palette closes first. Then exactly **one** dialog is open, the "Unsaved changes" confirm ("You have unsaved changes. Continue without saving?", Stay and Continue), with focus on Stay; the palette is not open beneath it. The hash is still `#agents/jtp-agent-03/general`. [a11y] |
| 11 | Click **Stay**. | No dialog is open, and the palette stays closed. The hash is still `#agents/jtp-agent-03/general`, and Description still holds `unsaved jtp edit`. Focus returns to the palette's opener, the Description field (`id` `studio-description`), not BODY. [a11y] |
| 12 | Press Ctrl+K, type `jtp-agent-07`, press Enter, and count the open dialogs while the confirm is open; then choose **Continue**. Then `GET {base}/api/agents/jtp-agent-03`. | Exactly one confirm opened (one dialog open while it showed), and after Continue it lands on `#agents/jtp-agent-07/general` with the editor showing `jtp-agent-07`. **The Agents filter is empty**, and the `jtp-agent-07` row is visible with `aria-current="page"`. The API returns `jtp-agent-03` with an empty or absent `description` (the edit was discarded). |
| 13 | Click into the Agents filter (`agents-filter`), press Ctrl+K, then press **Escape**. Then click the rail's **Jump to** control and click the palette's **Esc** button (`jump-to-close`). | After Escape: no dialog, and focus is back in the Agents filter, which is still empty (Ctrl+K typed nothing into it). After the Esc button: no dialog, and focus is back on the rail's Jump to control (`rail-jump-to`). [a11y] |
| 14 | **Teardown (setup row).** With the credential: `DELETE {base}/api/chat/sessions/{chatId}`; `DELETE {base}/api/agents/jtp-agent-NN` for all 12; `DELETE {base}/api/knowledge-bases/{kbId}`, `DELETE {base}/api/mcp-sources/{mcpId}`, `DELETE {base}/api/connectors/{connId}` and `DELETE {base}/api/providers/{provId}`. Close the variant's browser context. | (setup row, no judgment) |

## Out of Scope

- **The picker and the pending-chat flow:** `start-a-chat`.
- **Palette ordering edge cases, the cap with mixed kinds,
  macOS (Meta K), IME and modifier variants, and the picker-open and confirm-open no-ops:**
  the flow and contract tests (`test_flow_jump_to`, `test_ui_search_list_contract`,
  `test_ui_modal_contract`).
- **The desktop shells** (WebKitGTK and WebView2 accelerators): the leg 7 WebKitGTK probe
  (`scripts/webkitgtk_probe.py --press-keys ctrl+k`) and Flight 5.

## Variants

- **Theme.** Run steps 2–13 in **Light** and in **Dark**, each in its **own fresh browser
  context** (a new handoff mint). Before step 2, inside that context, open
  `{base}/#settings/appearance`, choose the variant's option in the theme radiogroup, and
  confirm `aria-checked="true"` on it and `data-theme` on `<html>`. The choice lives in the
  context (`localStorage`), so it must be made in the variant's own context before the first
  checkpoint; closing the context restores the operator's setting. The seed can be reused
  across variants: nothing in steps 2–13 changes the seeded data (step 12 discards its edit).
  In both themes:
  - the palette's active row is distinguishable from the other rows;
  - the "where" text is legible (read the computed `color` of the muted "where" text inside a `jump-to-result` row, against that row's own background);
  - the input bar shows its focus ring;
  - the scrim reads as a scrim: the computed scrim colour's alpha is **0.3 in Light and 0.5 in Dark**.

  Evidence is screenshots plus computed colours; the report says which.
