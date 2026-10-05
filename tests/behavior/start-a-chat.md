# Behavior Test: Start a Chat — New chat picker, pending chat, first send and agent drawer

**Slug**: `start-a-chat`
**Status**: draft
**Created**: 2026-10-05
**Last Run**: never

> **Draft (Mission 25 Flight 4 planning; revised after both flight design review cycles).** The step table fixes the observables and the
> flow. Testids follow the flight's DD12 list and may be adjusted when leg 6 finalizes the
> spec against the shipped build.

## Intent

Verify Mission 25 SC3 end to end against a live instance seeded with a realistic history.
- **The picker.** From Chats, one **New chat** action opens an agent picker: search,
  Recently used, then All agents A–Z.
- **Starting.** Choosing an agent starts a new chat with no further step, as a pending
  conversation. Picking again replaces it, and opening another conversation discards it.
- **The first message** creates exactly one session, and the URL becomes `#chats/{id}`.
- **The history** interleaves conversations across agents, grouped by recency.
- **The drawer** shows the chat's agent read-only, including what it can use. **Open agent
  settings** reaches the agent in one step.
- **The agent editor's Chat** action starts a pending chat with that agent, and asks first
  from a dirty editor.

This is a behavior test, because the observables span a real browser and the server:
- the modal's focus and keyboard;
- the pending row that must **not** create a server session (a WebSocket frame count and a
  REST session count);
- the drawer's push-versus-overlay layout at two widths;
- the leave-guard dialog across destinations.

It runs in both themes and creates data, all named with the prefix `sac-`.

## Preconditions

- **Instance under test.** A **dedicated dev instance** with a non-default port AND a
  scratch data directory together, with dev mode on (the mock provider). For example:

  ```
  THE_ONE_PORT=8486 THE_ONE_DATA_DIR=/tmp/the-one-sac-scratch THE_ONE_DEV_MODE=true make up
  ```

  **Never** port 8484, and never the operator's default data directory (CLAUDE.md,
  "Behavior-test credential convention"). The orchestrator states `{base}` and the
  scratch directory at run time.
- **Probes:**
  - `GET {base}/api/live` returns 200;
  - `GET {base}/api/providers/types` lists `mock`.
- **Credential.** Per CLAUDE.md: the bearer for the API, and a handoff mint for each fresh
  browser context.
- **Clean start.** There are no agents, providers or sessions prefixed `sac-`.
- **Browser apparatus.** A headless Chromium driven over CDP with real input, in a fresh
  context per variant. Concurrent Executors use their own scratch subdirectories. The
  apparatus must be able to read WebSocket frames (CDP `Network.webSocketFrameSent`).
- **Evidence notes:**
  - **Focus** is asserted as `document.activeElement` identity through an eval.
  - **Dialogs** are counted as `dialog[open]`.
  - **Server sessions** are counted with `GET {base}/api/chat/sessions`.

## Observables Required

- browser: DOM, accessibility tree, screenshots at 1440×900 and 1024×768,
  `location.hash`, `history.length`, and WebSocket frames sent (CDP)
- http: the seed and teardown calls, and the session count, via curl or the apparatus's
  request context

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | **Seed (setup).** Create:<ul><li>a mock provider `sac-mock`;</li><li>32 agents `sac-agent-01`…`sac-agent-32`, with distinct descriptions and two models;</li><li>sessions through `POST /api/chat/sessions` for six agents (`sac-agent-02`, `-03`, `-04`, `-06`, `-08`, `-10`), spread over today (now minus a few minutes, so the groups are stable near midnight), yesterday, 5 days ago and 20 days ago. `-05`, `-07` and `-09` have no sessions;</li><li>one session with `platform:"discord"` for `sac-agent-32`, newest overall;</li><li>a knowledge base `sac-kb`, attached to `sac-agent-03`.</li></ul>Record the session count. | (setup row, no judgment) |
| 2 | At 1440×900, open `{base}/#chats` in a fresh context and reload it cold. | The rail's Chats is current. The list column titled "Chats" has a full-width **New chat** button (`chats-new-btn`) and **no agent dropdown**. History rows from several agents are grouped under Today, Yesterday, Last 7 days and Last 30 days. Each row shows a title and a time on line 1 and the agent name on line 2; the Discord row also shows a platform badge. The most recent session is open: the header `<h1>` shows its title, with "with {agent}". No error banners. |
| 3 | Click **New chat**. Read the dialog, its groups and `document.activeElement`. | Exactly one dialog, titled "Start a chat with…", is open. **Focus is in the search field** ("Find an agent…"). **Recently used** lists up to 5 agents by most recent non-connector use, so `sac-agent-32`'s Discord session does not count. **All agents** lists all 32, A–Z. The footer reads "Picking an agent starts a new chat with it" and "Enter to start". [a11y] |
| 4 | Type `agent-1` in the search. Press ↓ once. | One group, "{n} matching", lists only the matching agents, A–Z. The active row moves with ↓ and is announced through `aria-activedescendant`. [a11y] |
| 5 | Press **Escape**. | The dialog closes and focus returns to **New chat**. The URL and the open chat are unchanged. [a11y] |
| 6 | Click **New chat**, then click `sac-agent-05`. Record the WebSocket frames sent and `GET /api/chat/sessions` before and after. | The picker closes. The hash is `#chats/~new/sac-agent-05`. The top of Today shows a selected pending row: "New chat · now · sac-agent-05". The header reads "New chat" with "with sac-agent-05". The pane shows the new-chat state (`chat-new-state`: a model badge, the name `sac-agent-05`, its description, "Pick a different agent"). The composer placeholder is "Message sac-agent-05…". **A `leave` frame is sent, and no `start_session`, `new_session` or `message` frame.** The server session count is unchanged. |
| 7 | Click **Pick a different agent**, then pick `sac-agent-07`. | There is still exactly **one** pending row, now "New chat · now · sac-agent-07", and the header and new-chat state show `sac-agent-07`. The server session count is still unchanged. |
| 8 | Type `hello from sac` in the composer and press **Enter**. | Exactly **one** `start_session` frame is sent. The user message shows, then the mock reply. The hash becomes `#chats/{id}` by replace (`history.length` unchanged). The pending row becomes a real row titled "hello from sac". The server session count is exactly one higher. No error. |
| 9 | Click **New chat**, pick `sac-agent-09`, then click any older conversation row. | The pending `sac-agent-09` row disappears. The clicked conversation opens, and the server session count is unchanged. |
| 10 | Open a conversation of `sac-agent-03`. Read the drawer. Click the drawer toggle twice. | At 1440 the drawer ("This chat's agent") is open by default and **pushes** the chat pane, with no overlap. It shows:<ul><li>`sac-agent-03` with its provider-type badge;</li><li>the description;</li><li>Model, Provider `sac-mock` and a Chats count;</li><li>**What it can use**, listing `sac-kb` under Knowledge bases plus the built-in tool categories;</li><li>**Open agent settings**.</li></ul>The toggle's `aria-pressed` follows the open state. [a11y] |
| 11 | Resize to 1024×768 and reload. Open the drawer, Tab into it and press Escape. | Below 1280 the drawer starts **closed**. When opened it **overlays** the right of the chat pane, without pushing it. Tab into the drawer, then press Escape: it closes, and focus returns to the toggle. [a11y] |
| 12 | At 1440 in Chats, open a `sac-agent-03` conversation. Go to Agents and type `sac-agent-1` in the filter, so that `sac-agent-03` is hidden. Go back to Chats with the rail, and click **Open agent settings** in the drawer. | No dialog appears: no dirty source exists on Chats. It lands on `#agents/sac-agent-03/general` with the editor showing, and **the Agents filter is cleared**, so the `sac-agent-03` row is visible and current. |
| 13 | In the `sac-agent-03` editor, type into Description without saving. Click **Chat** in the header, and choose **Stay**. Then click **Chat** again, and choose **Continue**. | **The first Chat** opens exactly one "Unsaved changes" dialog. Stay keeps the edit, and the hash stays on the agent editor. **The second Chat** with Continue lands on `#chats/~new/sac-agent-03`, with a pending `sac-agent-03` row and the new-chat state. The server session count is unchanged. [a11y] |
| 14 | Hover the `sac-` conversation created in step 8, and delete it through its row action, arm then confirm. | It is removed from the list and from `GET /api/chat/sessions`. Focus lands on a neighbouring row. [a11y] |
| 15 | **Teardown (setup row).** Delete the `sac-` sessions, agents, knowledge base and provider, and restore the original theme option. | (setup row, no judgment) |

## Out of Scope

- **The jump-to palette:** `jump-to-palette`.
- **Streaming, cancel, images and the composer's attach flow:** `chat-roundtrip`,
  `vision-round-trip`, and the chats lane.
- **The router and leave guard in general:** `workbench-navigation`.
- **Connector reply loops:** `stub-connector-round-trip`.

## Variants

- **Theme.** Run the table in **Light** and in **Dark**. Switch through Settings ›
  Appearance inside the variant's own fresh context, before step 2. In both themes:
  - the picker, the pending row's selected wash, the drawer and the composer's focus ring
    are legible;
  - the scrim reads as a scrim.
