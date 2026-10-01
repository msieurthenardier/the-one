# Leg: item-history-and-exact-rendering

**Status**: completed
**Flight**: [Shell and Router](../flight.md)

## Objective

Finish the router migration that `router-core` started. `router-core` turned every
`replaceSub` into an explicit-area `sync` (replace) and preserved same-section close.
This leg:
- assigns every URL-writing call path its disposition (intent `go()` push, bypass
  `go()`, `sync`, or delete);
- **deletes each converted path's inline `App.confirmDialog` gate**, so the router's
  guard is the only prompt;
- make section-root routes render exactly the root, closing open items and create
  forms;
- resolve dead item ids to the section root;
- make item opens push history, so Back steps between items;
- route the Chats session row through `go()`;
- move in-app links and the MCP tab onto the router.

## Context

- **Flight decisions:** DD3(d) and the "section-root routes render exactly the root"
  rule, DD4 (item-level push, Chats history, dead ids), and DD5 path 4 (item selection
  is an intent). Read them in `flight.md`.
- **What `router-core` already delivered:**
  - the router;
  - explicit-area `sync` at every former `replaceSub` site;
  - the interim guard on every `go()` and traversal;
  - the deleted section-nav and `setCategory` gates;
  - `closeOpenItem()`, preserving same-section close;
  - the `dirty` reset on Continue, and `_createMode` in `inEditor`;
  - the flipped tests.

  Read its flight-log entry.
- **The inline gates still present after `router-core`:** `selectAgent` (studio.js
  ~:1863), `handleBack` (~:2048), the KB, MCP and connector `onBack` (~:618, ~:772,
  ~:996), and the admin provider and tools `onBack` (~:318, ~:452). In `router-core`
  they were safe because their writes were `sync`. Once a callback here becomes `go()`,
  the router's guard prompts, so **its inline gate must be deleted in the same change**,
  or Continue would prompt twice.
  - `enterCreateMode` and connector open stay **inline gates**, because create mode and
    connectors are URL-less in this flight. They do not become `go()` calls.
- **Pre-decided dispositions** (`router-core` design review):

  | Call path | Disposition |
  |---|---|
  | post-delete navigation | bypass `go({replace: true})` |
  | KB-404 poll bounce (studio.js:~690) | bypass `go({replace: true})` |
  | KB detail 404 (studio.js:~581) | dead-id `sync` to root. It is a detail *load* finding the item gone, so the URL is healed in place. The poll bounce above is a *navigation* away from a detail that disappeared while open |
  | connector writes (studio.js:~991, ~1067, ~1074) | **delete**: URL-less in this flight; Flight 3 adds connector routes |
  | `startSessionWith` (new chat, chat.js:~486) | `sync` (Flight 4 redesigns Chats) |
  | `doSelect` completion | `sync` |
  | `setActiveTab`, `onSelectedMcpSourceChange` | `sync` (tab and focus refinements replace) |
  | `doHandleBack` | intent `go()` push |
  | save rename, save→delete race | bypass `go({replace: true})` |

- **`writeUrl_` (studio.js:~1143)** is shared by 9 callers with different
  dispositions, and admin 417, 428, 537 and studio 914, 927, 1067, 1074 mix intent with
  completion. The table is therefore **per call path** (about 40 rows), not per
  `replaceSub` line. The intent entry points include:
  - agent tiles (studio.js ~1750);
  - the grid `onSelect*` callbacks;
  - the chat session row (`_sessionCallbacks.onJoin`, chat.js:1130 →
    history-buckets.js:90);
  - section nav.

  None of these are `replaceSub` sites today.

## Inputs

- `static/js/router.js` (from `router-core`), `app.js`.
- `areas/studio.js`, `areas/admin.js`, `areas/chat.js`, `areas/chat/history-buckets.js`,
  `areas/studio/knowledge-tab.js` (:93), `areas/studio/mcps-tab.js` (:42-66, :76, :590,
  :606-615), `areas/chat/welcome.js` (:9, :32-42).
- `tests/browser/_nav.py` and the router tests.

## Outputs

- **Call paths.** Every URL-writing call path in chat, studio and admin uses `go()`
  (intent, push), `go({bypassGuard})` (push or replace, per the table), or `sync`, or
  stops writing. Each path converted to `go()` loses its inline gate.
- **Item opens push.** Agent tile, KB tile, MCP and provider rows, tools rows and Back
  buttons are intent `go()`s.
  - Hydrate consumes a cached pending item **before** rendering the section root, so
    there is no grid flash and no list refetch.
- **Section-root exact rendering.** In studio and admin, `hydrateState` of a section-root
  route closes any open item or create form, including the URL-less connector
  edit/create and agent create. It also resets `dirty` (the bare-agents branch at
  studio.js:163 doesn't today).
  - The same-section close lives in the section-root branch, **not** in
    `setActiveSection`.
- **Dead ids.** Each area resolves a pending item against a **fresh** fetch; if the item
  is not found, it `sync`s to the section root. This covers providers
  (`_tryConsumePendingProvider`), tools (`selectTool`'s 404 at admin.js:541-544 now
  fixes the URL), MCP sources, KBs and agents.
- **Hydrate origin.** `hydrateState(sub, {fresh})`.
  - The router passes `fresh: true` for traversals, boot and typed hashes; these resolve
    pending items against a **fresh** fetch, which dead-id handling needs.
  - It passes `fresh: false` for intent `go()`s; these use the cached list, with no
    refetch.
- **Chats.** The session row calls `go('#chats/{id}')` (push), and `hydrateState` joins
  exactly once. The row no longer also calls `joinSession`. `session_joined` and the
  reconnect auto-join are `sync`.
- **Links.** The knowledge-tab, mcps-tab and welcome links are built with
  `App.router.href` (new scheme).
- **MCP tab.**
  - Studio's `hydrateState` applies the tab and source for the **same** agent. A typed
    or linked `#agents/x/mcps/s2` while on `s1` re-renders.
  - `mcps-tab.js` reads `_selectedMcpAgentSourceId || _pendingMcpAgentSourceId` from
    studio. Its URL parsing and private `hashchange` listener are removed, which also
    removes the leak.
- **Flight log:** the **per-call-path disposition table** (file:function, before, after,
  reason).

## Acceptance Criteria

- [x] **AC1 — The disposition table** is in the flight log: every call path that writes
  a URL, about 40 rows, each with one disposition. It includes the pre-decided rows from
  Context. The skeleton is generated by grepping `writeUrl_`, `sync(`, the grid
  `onSelect*` callbacks and the Back/Cancel handlers. The Reviewer diffs the table
  against a fresh grep.
- [x] **AC2 — Item history.** Open agent A, then agent B: Back returns to A, and Back
  again returns to the Agents root. The same holds for two providers in Settings and two
  KBs in Library. Tab switches and MCP focus changes **replace**: Back from A's tools tab
  goes to the item before A, not to A's general tab.
- [x] **AC3 — Exact rendering (clean).**
  - Open a provider, press Back, and the list renders with the editor closed and
    `dirty` false.
  - The same for Library › MCP.
  - Opening the connector editor (URL-less), then clicking Library's Connectors section,
    closes the editor.
  - Agent create, then clicking the Agents top bar button (current destination → root),
    closes create mode.
  - Each of these, when **dirty**, prompts once (the `router-core` guard) and closes on
    Continue.
- [x] **AC4 — No grid flash** (for intent `go()`, `fresh: false`). An intent `go()` to an
  item in the current section consumes the cached item **without** re-rendering the
  section root.
  - For **providers and agents**, a test asserts the list endpoint is not refetched.
  - A `MutationObserver` on `.entity-tile-grid`, armed before the click, records no
    empty state and no "Loading…" text between the click and the editor.
  - **Knowledge and MCP** are tested separately: their list loads differ. If a refetch is
    inherent there, record it and assert only the no-flash part.
- [x] **AC5 — Dead ids** (traversal, `fresh: true`).
  - Create a provider, open it (pushed), Back, delete it **through the API** while its
    entry is still in history, then Forward: the router lands on `#settings/providers`
    with no editor and no endless pending state.
  - The same for an MCP source.
  - A unknown tool name (`#settings/tools/nope`) ends at `#settings/tools`.
- [x] **AC5b — One dialog per intent.** For each converted intent (agent tile, agent
  Back, KB Back, MCP Back, provider Back, tool Back), when dirty there is exactly
  **one** dialog: its inline gate is deleted. Continue proceeds without a second
  prompt. `enterCreateMode` and connector open keep their inline gate, and are tested
  to prompt once.
- [x] **AC6 — Chats.**
  - A session-row click is pushed, and exactly one join request is sent (count the
    WebSocket `join` frames, or the server-side join log).
  - Back returns to the previous session.
  - The reconnect auto-join while in Settings does not move the user, as `router-core`
    already tested.
- [x] **AC7 — Links and the MCP tab.**
  - The in-app links use new-scheme hrefs.
  - Typing `#agents/x/mcps/s2` while on `#agents/x/mcps/s1` focuses s2.
  - `mcps-tab.js` has no `hashchange` listener and no `location.hash` read (grep).
- [x] **AC8 — Gates pass.**
  - `make lint`;
  - `make test-unit`;
  - all five lanes, one at a time;
  - every `test_ui_*` in both engines.

  The flight log records the counts.

## Verification Steps

- AC1: the flight-log table plus the grep.
- AC2–AC7: the new tests (in `tests/browser/test_router_items.py` or similar) and the
  lanes.
- AC8: the commands listed.

## Implementation Guidance

1. **The per-call-path table first.** Walk every caller of `writeUrl_`, every
   `replaceSub`, every grid `onSelect*`, and every Back/Cancel. Fill in the table before
   coding.
2. **Studio:** intents → `go()`; completions → `sync`; exact rendering; dead ids; the
   MCP-tab state hand-off.
3. **Admin:** the same.
4. **Chat:** the row → `go()`; a single join.
5. **Links.**
6. **The tests and the gates.**

## Edge Cases

- **Back after a Back-button press** (pushed) re-opens the item. This is the DD4
  push-on-Back behaviour; note it in `agents.md`.
- **Save-create** (a new agent or provider) is a bypass `go()` that **replaces** the
  create entry with the item route, so Back does not return to a stale create form.
- **An item opened while the list is still loading:** the pending item is consumed after
  the fetch, with no double render.

## Files Affected

- `static/js/router.js` (`fresh` origin flag), `areas/studio.js`, `areas/admin.js`,
  `areas/chat.js`, `areas/chat/history-buckets.js`, `areas/studio/knowledge-tab.js`,
  `areas/studio/mcps-tab.js`, `areas/chat/welcome.js`
- `tests/browser/test_router_items.py` (new), plus any tests whose history expectations
  change
- `the_one/agents.md` (router contract: item history, dead ids, the hydrate origin flag, push-on-Back)
- `missions/25-workbench-navigation/flights/02-shell-and-router/flight-log.md`

## Citation Audit

From the `router-core` design review (2026-10-01):
- `studio.js:~1143 writeUrl_` and its 9 callers;
- `chat.js:1130` row → `history-buckets.js:90`;
- `admin.js:541-544` `selectTool` 404;
- `mcps-tab.js:42-66` listener;
- `studio.js:2931` `tryConsumePendingSelect` no-op on the same agent.

Re-check after `router-core` lands, because line numbers will drift.

Design review (Developer, cycle 2 together with `router-core`, 2026-10-01) — "approve
with changes". Applied:
- converted paths delete their inline gates (one-dialog ACs);
- `enterCreateMode` and connector open stay inline;
- the `fresh` hydrate origin separates no-refetch intents from fresh traversals;
- the no-flash assertion defined (MutationObserver), with Knowledge and MCP tested
  separately;
- the KB 404 vs poll-bounce reason stated;
- a grep-generated table skeleton.

---

## Post-Completion

Completion steps — status transitions, flight-log update, checking off in the parent
flight, and commit — are Flight Control protocol, driven by the execution workflow. Not
repeated here.
