# Behavior Test: Start a Chat — New chat picker, pending chat, first send and agent drawer

**Slug**: `start-a-chat`
**Status**: active
**Created**: 2026-10-05
**Updated**: 2026-10-24 (M31 F4 L11: the theme options are native radios, so the Theme variant checks `checked`, not `aria-checked`); 2026-10-06 (M25 F6 leg 4b, DD14: step 2 Today time reads local 12-hour `h:mm AM/PM`; M25 F6 leg 3, squawk 0122: wording only, no expectation changed: frames judged per step with each step's frame actions listed, a recorder restart's reload sequence, step 11's geometric criterion, step 13's Description selector); 2026-10-05 (M25 F4 leg 8: finalized against the shipped build: testids, copy, routes, seeding and apparatus)
**Last Run**: 2026-10-28-02-32-16 — pass (26/26; Light + Dark; M31 F6 close sweep, port 8499; re-author list in the run log)

## Intent

Verify Mission 25 SC3 end to end against a live instance seeded with a realistic history, and
the reachable half of SC2:
- **The picker.** From Chats, one **New chat** action opens an agent picker: search,
  Recently used, then All agents A–Z.
- **Starting.** Choosing an agent starts a new chat with no further step, as a *pending*
  conversation (`#chats/~new/{agent}`) that creates nothing on the server. Picking again
  replaces it, and opening another conversation discards it.
- **The first message** creates exactly one session, and the URL becomes `#chats/{id}`.
- **The history** interleaves conversations across agents, grouped by recency.
- **The drawer** shows the chat's agent read-only, including what it can use. **Open agent
  settings** reaches the agent in one step, with the Agents filter cleared.
- **The agent editor's Chat** action starts a pending chat with that agent, and asks first
  from a dirty editor (SC2).
- **Delete** from a row.

This is a behavior test, because the observables span a real browser and the server:
- the modal's focus and keyboard model;
- the pending row that must **not** create a server session (the WebSocket frames sent and
  the REST session count);
- the drawer's push-versus-overlay layout at two widths;
- the leave-guard dialog across destinations.

It runs in both themes (see Variants) and creates data, all named with the prefix `sac-`.

## Preconditions

- **Instance under test.** A **dedicated dev instance** with a non-default port AND a
  **fresh** scratch data directory together, with dev mode on (the mock provider). For
  example:

  ```
  THE_ONE_PORT=8487 THE_ONE_DATA_DIR=$HOME/the-one-behavior-test-scratch/sac/data THE_ONE_DEV_MODE=true <repo>/.venv/bin/the-one serve
  ```

  A fresh data directory has no `api-credential`: create it first with `THE_ONE_DATA_DIR=$HOME/the-one-behavior-test-scratch/sac/data the-one rotate-api-credential`.

  Start it from a scratch working directory, not the repo root (`mkdir -p <scratch>/cwd && cd <scratch>/cwd`; CLAUDE.md "SAFETY RULE"), detached with the PID recorded; stop it by that PID.

  **Never** port 8484, and never the operator's default data directory (CLAUDE.md,
  "Behavior-test credential convention"). The orchestrator states `{base}` and the scratch
  directory at run time; both apply to every step. The expectations below are exact for a
  fresh instance: it holds **no agents, providers or chat sessions** before step 1 (the
  recency groups, Recently used and the auto-opened chat all depend on it).
- **Probes:**
  - `GET {base}/api/live` returns 200;
  - `GET {base}/api/providers/types` (with the credential) lists `mock`.
- **Credential.** Per CLAUDE.md: the bearer for every API call, and a handoff mint
  (`POST {base}/api/session/handoff`) for each fresh browser context.
- **Clock.** The recency groups are local calendar days (the browser's timezone). Do not
  run steps 1–3 within 15 minutes after local midnight.
- **Browser apparatus.** A headless Chromium driven over CDP with **real input**
  (Playwright's `page.mouse` / `page.keyboard`, or CDP `Input.dispatchMouseEvent` /
  `Input.dispatchKeyEvent`), never a synthetic `dispatchEvent` or an `element.click()` from
  an eval. This is the project's behavior apparatus (Mission 25 Flight 3 DD12); goldfinch is
  not used while its input delivery is unverified. One fresh browser context per variant,
  viewport **1440×900** unless a step says otherwise. The apparatus must record the
  WebSocket frames the page sends (CDP `Network.webSocketFrameSent`, or Playwright's
  `page.on('websocket')` → `framesent`), **attached before the page loads**, because the
  socket opens on load.
- **Evidence notes.**
  - **Focus** is asserted as `document.activeElement` identity (tag, `data-testid`, `id`)
    through an eval, never a visible ring.
  - **Dialogs** are counted as `document.querySelectorAll('dialog[open]').length`. The
    picker is `[data-testid="agent-picker"]`; the leave-guard confirm is
    `[data-testid="confirm-dialog-overlay"]`, with Stay `modal-cancel-btn` and Continue
    `modal-confirm-btn`.
  - **Server sessions** are counted with `GET {base}/api/chat/sessions` (the array length),
    read immediately before and after each step that names the count.
  - **Frames**: report the `action` of every frame sent during the step (`leave`, `join`,
    `start_session`, `message`, `list_sessions`, …). `list_sessions` refreshes are
    expected throughout and are not session-creating. **Frames are judged per step**: the
    report lists the frame actions sent during each step (not a running line count, which
    breaks when the recorder restarts). If the recorder or the browser is restarted
    mid-run, the recovery adds a reload sequence (a reload, then its `join`/`list_sessions`
    frames) to the step it falls in; judge that step's frame expectation against the frames
    its own Actions sent, and say what the recovery added.
  - Read `aria-current`, `aria-pressed`, `aria-selected`, `aria-activedescendant`,
    `location.hash` and `history.length` through DOM evals; the accessibility-tree dumps
    may omit them. The chat area's state machine can corroborate:
    `App.areas.find((a) => a.id === 'chat')._sessionState()` gives `{name, id, agent}`.
  - A row's delete action (`chat-row-delete`) is `display: none` until its row is hovered
    or focused: move the real pointer over the row first.
  - A cold load means navigate to the URL, then reload; confirm with
    `performance.getEntriesByType('navigation')[0].type === 'reload'`.
  - Report only **rendered** error banners (non-empty text, laid out). No toast is expected;
    if one appears, its evidence is a screenshot, not `offsetParent` (a `position: fixed`
    element has a null `offsetParent`).
  - Screenshots: the picker (step 3), the pending chat (step 6), the drawer at 1440 (step
    10) and at 1024 (step 11), per variant.

## Observables Required

- browser: DOM, accessibility tree, screenshots at 1440×900 and 1024×768, `location.hash`,
  `history.length`, `document.activeElement`, and the WebSocket frames sent (CDP)
- http: the seed and teardown calls, and the session count (curl in the shell, or the
  apparatus's request context)

## Steps

Notation: `t(Δ)` is the UTC instant `Δ` before the seed ran, as an ISO-8601 string
(`(datetime.now(timezone.utc) - Δ).isoformat()`, the format `seeders.seed_session` sends).

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | **Seed (setup).** With the credential, expecting 201 for each POST: <ul><li>`POST {base}/api/providers` `{"name":"sac-mock","type":"mock","base_url":"","config":{"models":["mock-default","mock-alt"]}}`; keep `{provId}`;</li><li>`POST {base}/api/knowledge-bases` `{"name":"sac-kb"}`; keep `{kbId}`;</li><li>`POST {base}/api/mcp-sources` `{"name":"sac-mcp","type":"stdio","config":{"command":"x","_cache":{"tools":[{"name":"alpha","description":""},{"name":"beta","description":""},{"name":"gamma","description":""}]}},"secrets":{}}`; keep `{mcpId}` (the cached tool list means no server is ever started);</li><li>32 agents, `POST {base}/api/agents` `{"name":"sac-agent-NN","provider_config_id":"{provId}","llm_model":"<model>","system_prompt":"mock","description":"Start-a-chat seed agent NN"}` for NN = 01…32 (zero-padded), `<model>` `mock-default` for 01–16 and `mock-alt` for 17–32. `sac-agent-03` also carries `"kb_ids":["{kbId}"]`, `"mcp_source_ids":["{mcpId}"]` and `"disabled_tools":["shell"]`;</li><li>8 sessions, each `POST {base}/api/chat/sessions` `{"agent_name":A,"title":T,"updated_at":U,"created_at":U,"platform":P}` (the `seed_session` shape; `P` is `null` unless stated): `sac-agent-32` "sac discord thread" `t(1 min)` `P="discord"`; `sac-agent-02` "sac today two" `t(5 min)`; `sac-agent-03` "sac today three" `t(10 min)`; `sac-agent-04` "sac yesterday four" `t(24 h 5 min)`; `sac-agent-03` "sac yesterday three" `t(24 h 10 min)`; `sac-agent-06` "sac five days six" `t(5 days)`; `sac-agent-08` "sac twenty days eight" `t(20 days)`; `sac-agent-10` "sac twenty-one days ten" `t(21 days)`. Keep every id.</li></ul> Record `GET {base}/api/chat/sessions` (8). | (setup row, no judgment) |
| 2 | In the variant's fresh context (its theme already set, see Variants), with frame recording attached, navigate to `{base}/#chats` and reload (cold). | **Rail.** Chats is the only `aria-current="page"` rail link. **List column** (`chats-list`, titled "Chats"): a full-width **New chat** button (`chats-new-btn`, enabled) and **no agent dropdown**. Rows (`chat-row`) from several agents, grouped in this order: **Today** ("sac discord thread", "sac today two", "sac today three"), **Yesterday** ("sac yesterday four", "sac yesterday three"), **Last 7 days** ("sac five days six"), **Last 30 days** ("sac twenty days eight", "sac twenty-one days ten"); no "Older" group. Each row shows its title with a time on line 1 (Today a local 12-hour time such as `3:45 PM`, Yesterday and Last 7 days a weekday such as `Mon`, Last 30 days a month and day such as `Sep 15`) and its agent on line 2; "sac discord thread" also shows a `discord` badge. **Pane.** The newest session, "sac discord thread", is open: the hash becomes `#chats/{its id}`, its row has `aria-current="page"`, and the chat header (`chat-header`) shows the `h1` "sac discord thread" with "with sac-agent-32" (`chat-agent-line`). At 1440 the agent drawer (`chat-drawer`, "This chat's agent") is open beside the pane, naming `sac-agent-32`. No error banners. |
| 3 | Click **New chat** (`chats-new-btn`). Read the dialog, its groups and `document.activeElement`. | Exactly one dialog is open: the agent picker (`agent-picker`), titled "Start a chat with…", with an "Esc" button (`agent-picker-close`, accessible name "Close (Esc)"). **Focus is in the search field** (`agent-picker-search`: label "Find an agent", placeholder "Find an agent by name, model or provider"). **Recently used** lists exactly 5 agents, most recent first: `sac-agent-02`, `sac-agent-03`, `sac-agent-04`, `sac-agent-06`, `sac-agent-08`. `sac-agent-32` is absent although its Discord session is the newest (a connector session is not the operator's use), and `sac-agent-10` is sixth, so it is left out. **All agents** lists all 32, `sac-agent-01` … `sac-agent-32`, A–Z. Each row (`agent-picker-row`, `data-agent`) shows the name, its description and its model. The first row is active (`aria-selected="true"`, named by the input's `aria-activedescendant`). The footer reads "Picking an agent starts a new chat with it" and "Enter to start". [a11y] |
| 4 | Type `agent-1` in the search. Press ↓ once. | One group, "10 matching", lists `sac-agent-10` … `sac-agent-19`, A–Z, and nothing else. Before ↓ the first row (`sac-agent-10`) is active; after ↓ the second (`sac-agent-11`) is, and the input's `aria-activedescendant` names it. Focus stays in the search field. [a11y] |
| 5 | Press **Escape**. | No dialog is open, and focus is back on **New chat** (`chats-new-btn`). The hash and the open chat ("sac discord thread") are unchanged. No frame was sent. [a11y] |
| 6 | Record `history.length` and the session count. Click **New chat**, type `sac-agent-05`, and press **Enter**. Record the frames sent, `history.length` and the session count. | The picker closes. The hash is `#chats/~new/sac-agent-05`, a push (`history.length` one higher). At the top of Today, a selected pending row (`chat-row` with `data-pending`, `aria-current="page"`, no delete action) reads "New chat", "now", `sac-agent-05`. The header reads "New chat" with "with sac-agent-05". The **new-chat state** (`chat-new-state`) shows a `badge--mock` badge reading `mock-default` (the model), the name `sac-agent-05` as a heading, "Start-a-chat seed agent 05", and **Pick a different agent** (`chat-pick-different-btn`). The composer's placeholder is "Message sac-agent-05…" and its model id (`chat-model`) reads `mock-default`; no telemetry readout shows. The drawer names `sac-agent-05` with Chats 0. **Frames: one `leave`, and no `start_session`, `join` or `message`.** The session count is unchanged (8). |
| 7 | Click **Pick a different agent**. In the picker, type `sac-agent-07` and click its row. | There is still exactly **one** pending row, now "New chat", "now", `sac-agent-07`, and the header and the new-chat state show `sac-agent-07`. The hash is `#chats/~new/sac-agent-07`, a replace (`history.length` unchanged from step 6). No frame was sent. The session count is still 8. |
| 8 | Type `hello from sac` in the message box (`chat-input`) and press **Enter**. Wait for the reply. | Exactly **one** `start_session` frame is sent (`agent_name` `sac-agent-07`, `message` `hello from sac`, a 32-hex `session_id`), and no `message` frame. The user message shows, then the mock reply "Mock response from the mock provider." The hash becomes `#chats/{that session_id}` by replace (`history.length` unchanged). The new-chat state is gone and the telemetry readout shows above the composer. The pending row is replaced by a real row with that `data-id`, titled "hello from sac" with `sac-agent-07`, selected; the header's `h1` reads "hello from sac". The session count is exactly **9**. No error banner. |
| 9 | Click **New chat**, type `sac-agent-09`, press Enter. Then click the row "sac five days six". | After the pick: a pending `sac-agent-09` row and a `leave` frame, with the count still 9. After the row click: the pending row is gone, "sac five days six" opens (its row `aria-current="page"`, the header "sac five days six" with "with sac-agent-06", the hash `#chats/{its id}`), one `join` frame is sent, and the session count is still **9**. |
| 10 | Click the row "sac today three" (a `sac-agent-03` conversation). Read the drawer. Then click the drawer toggle (`chat-drawer-toggle`) twice, reading the drawer and the pane after each click. | At 1440 the drawer is open by default and **pushes** the pane: the drawer is 320px wide at the window's right edge and the pane ends where it begins, with no overlap (the pane is 748px). The drawer shows: <ul><li>`sac-agent-03` as its heading, with a provider-type badge reading `mock`;</li><li>the description "Start-a-chat seed agent 03";</li><li>the facts (`chat-drawer-facts`): Model `mock-default`, Provider `sac-mock`, Chats `2`;</li><li>**What it can use** (`chat-drawer-uses`): Knowledge bases `sac-kb`; MCP servers `sac-mcp` with "3 tools"; Built-in tools Filesystem "9 of 9", Execution "5 of 6", Web "4 of 4", Connectors "3 of 3"; Self-configuration "Off";</li><li>**Open agent settings** (`chat-drawer-settings-link`) in its footer.</li></ul> The toggle's `aria-pressed` is `true` and `aria-controls` is `chat-drawer`. After the first click the drawer is hidden, `aria-pressed` is `false` and the pane widens to 1068px; after the second it is back, `aria-pressed` `true`, the pane 748px. [a11y] |
| 11 | Resize to 1024×768 and reload. Read the drawer. Click the toggle to open it. Click into the message box, then press Tab until `document.activeElement` is the drawer's **Open agent settings**. Press **Escape**. | Below 1280 the drawer starts **closed** (`hidden`, `aria-pressed` `false`) and the pane is 652px. Opened, it **overlays** the right of the chat pane (320px, from the top, with a shadow and no scrim) without narrowing it (still 652px), and the toggle stays clickable above it, in the drawer header's right corner (a geometric criterion: the toggle sits in the chat header and is not a DOM descendant of the drawer element, so judge its position by its bounding box against the drawer's top-right corner). Tab reaches **Open agent settings** inside the drawer. Escape closes the drawer, and focus returns to the toggle (`chat-drawer-toggle`), whose `aria-pressed` is `false`. [a11y] |
| 12 | Resize to 1440×900. Click the rail's **Agents** link and type `sac-agent-1` in the Agents filter (`agents-filter`), so the `sac-agent-03` row is hidden. Click the rail's **Chats** link. Click **Open agent settings** in the drawer. | The rail returns to the "sac today three" conversation (`#chats/{its id}`), and the drawer is open (push). After Open agent settings: **no dialog appears** (no dirty source exists on Chats). The hash is `#agents/sac-agent-03/general`, the editor shows `sac-agent-03`, **the Agents filter is empty**, and the `sac-agent-03` row is visible with `aria-current="page"`. |
| 13 | In the `sac-agent-03` editor, type `unsaved sac edit` into Description (the field with `id` `studio-description`; it has no `data-testid`, so select it by `#studio-description`) without saving. Click **Chat** (`agent-chat-btn`) in the editor header and choose **Stay**. Then click **Chat** again and choose **Continue**. Record the session count. | **The first Chat** opens exactly one "Unsaved changes" dialog ("You have unsaved changes. Continue without saving?", Stay and Continue). After Stay: no dialog; the hash is still `#agents/sac-agent-03/general`; Description still holds `unsaved sac edit`; focus is back on **Chat**. [a11y] **The second Chat** opens exactly one dialog, and Continue lands on `#chats/~new/sac-agent-03`: a selected pending `sac-agent-03` row and the new-chat state for `sac-agent-03`. `GET {base}/api/agents/sac-agent-03` still has the description "Start-a-chat seed agent 03" (nothing was saved), and the session count is unchanged (9). |
| 14 | Hover the "hello from sac" row (step 8's conversation) and click its delete action (`chat-row-delete`, "Delete chat: hello from sac") once, then again within 3 seconds. Record the session count. | The first click arms it in place: the row reads "Confirm delete?" and nothing is deleted. The second click removes the row from the list and its id from `GET {base}/api/chat/sessions` (the count is 8). Focus lands on the row that followed it in the list (a `chat-row` link). The pending `sac-agent-03` chat stays open. [a11y] |
| 15 | **Teardown (setup row).** With the credential: `DELETE {base}/api/agents/sac-agent-NN/chat/sessions` for every seeded agent; `DELETE {base}/api/agents/sac-agent-NN` for all 32; `DELETE {base}/api/knowledge-bases/{kbId}`, `DELETE {base}/api/mcp-sources/{mcpId}` and `DELETE {base}/api/providers/{provId}`. Close the variant's browser context (its theme choice goes with it). | (setup row, no judgment) |

## Out of Scope

- **The jump-to palette:** `jump-to-palette`.
- **Streaming, cancel, images and the composer's attach flow:** `chat-roundtrip`,
  `vision-round-trip`, and the chats lane (`test_flow_chat_composer`,
  `test_flow_chat_image_attach`).
- **Reconnects while starting or joined, and frames in flight:** the chats lane
  (`test_flow_chat_start_reconnect`, `test_flow_chat_start_flow`).
- **The router and leave guard in general:** `workbench-navigation`.
- **Connector reply loops:** `stub-connector-round-trip`.

## Variants

- **Theme.** Run steps 2–14 in **Light** and in **Dark**, each in its **own fresh browser
  context** (a new handoff mint). Before step 2, inside that context, open
  `{base}/#settings/appearance`, choose the variant's option in the theme radiogroup, and
  confirm it is `checked` (the options are native radios) and `data-theme` on `<html>`. The choice lives in the
  context (`localStorage`), so it must be made in the variant's own context before the first
  checkpoint; closing the context restores the operator's setting. Re-seed per variant
  (step 15, then step 1); reusing the seed is allowed only when `GET {base}/api/chat/sessions`
  holds exactly the eight seeded sessions and the clock rule still holds. In both themes:
  - the picker's active row is distinguishable from its neighbours;
  - the pending row's selected wash is visible;
  - the drawer's text is legible on its surface;
  - the composer box shows its focus ring while the message box has focus;
  - the scrim behind the picker reads as a scrim.

  Evidence is screenshots plus computed colours; the report says which.
