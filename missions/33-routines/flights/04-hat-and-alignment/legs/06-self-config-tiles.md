# Leg: self-config-tiles

**Status**: completed
**Flight**: [HAT and Alignment](../flight.md)

## Objective

Rebuild the agent editor's **Self-configuration** tab on the layout the
operator chose at the HAT, mockup **SC2**
(https://claude.ai/artifact/ADMrdaR59SSTHgWdV6CbVe, artboard "SC2. Tiles,
settings inline, two expanders"): one card per item (**Agent prompt**,
**Routines**) with its enable switch, title, a "Require approval" switch on
the title row, a one-line description, and two expanders, **Waiting for
approval (n)** and **History**; **External access** moves to the bottom of the
tab as a page-level section. (The approval default and the drawer refresh,
first planned here, were split into leg 05 at design review.)

## Context

- **Operator decisions at the HAT** (flight log, E1/E2): C8 reversed ("we
  should switch the default to match the other setting"); the two items are
  organized differently (Agent prompt's approval has its own section,
  Routines' does not) and the operator prefers the compact Routines form;
  "the whole self-configuration tab could use a clean up and compaction";
  SC2 chosen over SC1; external access goes at the bottom. Letting an
  external client manage routines is **out of scope**: a follow-up to the
  mission (recorded for the mission debrief).
- **Today's tab** (`static/js/areas/studio/self-configuration-tab.js`
  assembles section modules):
  - `self-config-status.js`: the Agent prompt section (h3 "Agent prompt",
    description, status line, the enable switch "Let this agent edit its
    description and system prompt") and a separate h3 "Prompt approval"
    section with its description and the "Require approval for prompt edits"
    switch;
  - `self-config-revisions.js`: h3 "Pending revisions" (Current/Proposed,
    Approve/Dismiss, the stale 409 with "Overwrite and approve");
  - `self-config-history.js`: h3 "Revision history" (with Restore, M21 F2
    L3);
  - `self-config-external.js`: h3 "External access" (grants list, Grant
    access, the shown-once token, Rotate/Revoke);
  - `self-config-routines.js` and `self-config-routines-queue.js`: h3
    "Routines" with both switches, h4 "Waiting for approval" and h4 "Changes
    by the agent" (20 a page).
  The tab handle has `activate` (refetches both queues on a tab switch
  back); M31 F2 rules: a self-configuration write never re-selects the agent,
  unsaved General edits are kept, the token reveal clears on disable, tab
  leave and a new identity.
- **The approval default:** `AgentConfig.routines_require_approval = True`
  (`agent/config.py` ~:156; `save` never writes it) and the v46 column
  `agents.routines_require_approval INTEGER NOT NULL DEFAULT 1`
  (`db/schema.py` ~:3191). Mission 33 is not in any release
  (`docs/releases/` has no routines entry), so no shipped install has
  stored values to preserve.
- **The drawer refresh:** `areas/chat/turn-frames.js` ~:126 calls
  `agentDrawer.refreshNotes()` when a live tool result belongs to a note
  tool (`NOTE_TOOLS`); routines refresh only on `session_joined`
  (`agent-drawer.js` `refreshRoutines`).

### Design decisions (leg-level)

**L6-DD1. The tab (SC2).**
- A page-level eyebrow ("What this agent can change", the DD13 section
  style), then the two cards, then the "External access" section (eyebrow,
  description, grants, Grant access): existing behaviour, moved, unchanged.
- **Each card**, built from `App.ui` controls (prefer `App.ui.groupTile` as
  the Routines list does, composing what it lacks; `App.ui.disclosure` for
  the two expanders if groupTile's single expander cannot hold both):
  - title row: the enable switch (named "Let this agent edit its description
    and system prompt" / "Let this agent manage its routines" for assistive
    tech; testids `self-config-toggle` / `self-config-routines-toggle` kept),
    the bold title ("Agent prompt" / "Routines"), and on the right the
    "Require approval" switch with a visible label "Require approval"
    (accessible name "Require approval for prompt edits" / "… for routine
    changes"; testids kept). The approval switch is disabled while the item
    is off, as today;
  - the one-line description (the existing sentences, trimmed to one line
    each as in the mockup);
  - the status line where today's tab shows one (enable/disable progress,
    errors), kept compact;
  - **Waiting for approval (n)**: an expander whose label carries the count
    (a count chip when n > 0; a muted, non-expanding label "Waiting for
    approval (0)" when empty); its body is today's queue for that item
    (Agent prompt: the Current/Proposed revision items with Approve, Dismiss,
    the stale path; Routines: today's routine queue). Opens automatically
    when n > 0 on first render? **No**: collapsed by default; the count is
    the cue (FD call; the operator can reverse at the re-check);
  - **History**: an expander with today's history for that item (Agent
    prompt: revision history with Restore; Routines: "Changes by the agent",
    20 a page).
- The separate "Prompt approval" section and its long description go; the
  card's switch replaces it. The headings: page eyebrow (h2-level styling per
  the tab's structure), card titles h3, expander labels are buttons; the
  h3/h4 asymmetry (L3) disappears.
- Behaviour kept exactly: every switch's API call and refusal handling,
  `activate` refetching both queues, focus rules after Approve/Dismiss (next
  Approve or the empty state), the stale/gone/422 paths, the token reveal
  clearing, "a write never re-selects the agent".
- Testids: keep every testid whose element keeps its meaning; retire the
  ones that go (registry retired table + `RETIRED_SELECTORS`); register new
  ones (the cards, the two expanders and their counts).

**L6-DD2. The card (design review).**
- Extend `App.ui.groupTile` with an opt-in `expand: false` that omits its
  expand button and body (catalogue row in `docs/ui-control-inventory.md`
  and its contract test in `tests/browser/test_ui_tile_contract.py`, run with
  `THE_ONE_REQUIRE_WEBKIT=1`). Each card: `master` for the enable switch
  (`tristate: false`), `actions: [approvalToggle.el]`, `subtitle` for the
  description, then two `App.ui.disclosure` children appended under
  `tile.el` with `variant: 'bordered'` (its `meta` holds the count chip, read
  as part of the name).
- **n = 0**: "Waiting for approval (0)" is plain muted text (a non-`details`
  element), since a disclosure has no disabled state; it becomes the
  disclosure when a change arrives.
- **An action that produces an error or the stale state inside a collapsed
  expander opens it**, so the message is visible.
- **Counts fetch on mount** (as the queues do today); never a lazy
  first-open fetch, which would break the count.
- New card builder in its own small module (e.g.
  `areas/studio/self-config-card.js`, loaded in `index.html` before the tab).
- **Module wiring:** each section module's `build(ctx)` appends to a target
  container (`ctx.cards.prompt` / `ctx.cards.routines` expander bodies) and
  reports counts through a `ctx.setWaitingCount(item, n)` hook (the Agent
  prompt count from `fetchRevisions`' pending rows; Routines from its queue
  or `pending-count`). The history module's own "Revision history"
  disclosure goes: its content is the card's History body (no nested
  disclosures). `setAgent`/`destroy` tear both cards down; `activate`
  refreshes the counts too.
- **Testids:** keep both switches' testids; reuse `pending-count` and
  `self-config-routine-pending-count` as the two count chips; list every
  retired id (section headings, the "Prompt approval" description and the
  like) in the registry's retired table and `RETIRED_SELECTORS`.

**Order of work:** the groupTile change with its contract test; the card
module; move each section module into its card (updating its browser tests
alongside); External access to the bottom; docs and registry.

## Acceptance Criteria

- [ ] AC1. The tab renders SC2: page eyebrow, the Agent prompt and Routines
      cards (enable switch, title, Require approval switch on the title row,
      description, Waiting for approval (n) and History expanders), then
      External access at the bottom; no separate "Prompt approval" section.
- [ ] AC2. Every existing behaviour of the tab works from its new place:
      both items' enable/approval switches, the Agent prompt queue (approve,
      dismiss, stale override) and history (Restore), the Routines queue
      (approve, dismiss, stale "Approve anyway", gone, 422) and history
      paging, external grants (grant, token once, rotate, revoke), `activate`.
- [ ] AC3. The waiting count updates when a change arrives or is resolved
      (on `activate` and after each action), and the expanders are keyboard
      operable with correct `aria-expanded`.
- [ ] AC4. An error or stale state from an action inside a collapsed
      expander opens it; turning an item off with changes pending drops its
      count to 0 at once (withdrawn).
- [ ] AC5. `App.ui.groupTile` `expand: false` has its catalogue note and
      contract tests (Chromium and WebKit).
- [ ] AC6. Retired and new testids are registered; `tests/test_nav_helper.py`,
      the static guards, `tests/test_area_module_size.py` and
      `tests/test_ui_ownership.py` pass; the Accessibility Reviewer confirms
      (labels, heading order, switch names, expanders).
- [ ] AC7. `THE_ONE_TEST_NETNS=1 make test-unit` (15 skipped) and the lanes
      `agent-tabs`, `agent-routines` and `contracts-controls` (with
      `THE_ONE_REQUIRE_WEBKIT=1`) pass.

## Verification Steps

- AC1-AC3, AC6: browser tests in `tests/browser/test_studio_self_configuration_*`
  and `test_flow_agent_routines_self_config.py` (updated for the new
  structure, not deleted: every behaviour they pin stays).
- AC4: browser tests. AC5: the tile contract tests.

## Edge Cases

- The `~new` agent keeps the save-first empty state; the `default` agent's
  existing handling is not regressed.
- Both items off: both cards show, approval switches disabled, expanders
  available (history may still have entries).
- A queue with 20+ pending changes (the pending cap): the count shows the
  number; the body scrolls within the page, not a nested scroller.
- The `default` agent and `~new`: today's empty states are kept.
- Narrow widths (1024 px): the title row wraps the approval switch under the
  title rather than overflowing.

## Files Affected

- `static/js/areas/studio/self-configuration-tab.js`, `self-config-status.js`,
  `self-config-revisions.js`, `self-config-history.js`,
  `self-config-external.js`, `self-config-routines.js`,
  `self-config-routines-queue.js`, a new `self-config-card.js`,
  `static/index.html`; `static/css/studio.css`; `static/js/ui/tile.js`
  (`expand: false`).
- Tests: `tests/browser/test_studio_self_configuration_*`,
  `test_flow_agent_routines_self_config.py`, `test_ui_tile_contract.py`.
- Docs: `docs/ui-testid-registry.md`, `docs/ui-control-inventory.md`,
  `tests/test_nav_helper.py`, `the_one/agents.md` (Self-configuration
  section), CLAUDE.md's Self-configuration paragraph.

## Citation Audit

Verified at planning: `self-config-status.js` (Agent prompt section ~:33,
"Prompt approval" section ~:70-97), `self-config-revisions.js` ("Pending
revisions" ~:79), `self-config-history.js` ("Revision history" ~:45),
`self-config-external.js` ("External access" ~:34),
`self-config-routines.js` (~:42-100), `self-config-routines-queue.js`
(~:176-300); `agent/config.py` ~:152-156; `db/schema.py` ~:3189-3191;
`turn-frames.js` ~:18, ~:126; the module sizes (all under 800 lines; largest 438).
