# Flight Log: List and Detail

**Flight**: [List and Detail](flight.md)

## Summary

*(written at landing)*

---

## Reconnaissance Report

Source: the Flight 3 research digest (read-only reconnaissance of `4828d53`), plus the Flight 2 debrief and flight-close observations.

| Item | Classification | Evidence | Recommendation |
|---|---|---|---|
| Squawk 0101 (knowledge-base create lands on the grid) | confirmed-live | `studio.js:490` ignores `kb` in `onCreateSuccess` | Fix in L4a (DD8). |
| Provider-create route announcer stays on "— New" (Flight 2 observation) | confirmed-live | `router.js` `sync` 556–577 never announces | Fix in L2 (DD8): `sync` announces the create→item transition. |
| Connectors empty-state CTA unstyled | confirmed-live | `connector-editor.js:243` lacks `btn-outlined-primary` | It goes away with the list rebuild (L4); no separate squawk. |
| Tile title runs under the badge | confirmed-live | `components.css:842` `.entity-tile-badge` is absolutely positioned | It goes away with list-pane rows (L3–L5). |
| Section-nav items are `<button>`s | confirmed-live | `section-nav.js:70` | Replaced by the grouped list and `navGroups` links (L4–L5). |
| `listPane` gaps against the reference spec (title count, intro, title style, per-group empty) | confirmed-live | `ui/list-pane.js:67`; `components.css:576` | Fixed in L1. |

---

## Leg Progress

---

## Flight Director Notes

- 2026-10-01: **Flight drafted** by the Flight Director, autonomously, without an operator
  interview.
  - **Inputs:**
    - the Flight 3 research digest;
    - the Flight 2 debrief (Architect input) and its flight-close observations;
    - reference spec §3–§8, §13 and §15.
  - **Draft shape:** 14 DDs and 6 legs.
- 2026-10-01: **Architect cycle 1** returned "approve with changes": 3 high, 6 medium and 4
  low issues, plus 6 questions.
  - **Applied:**
    - DD1 width mechanism: `aside.dataset.destination` plus CSS placed after the media
      query; the list body is the scroller.
    - Create routes move into their destination legs; L2 is narrowed to
      `data-and-announcer`.
    - The General split moves wholly into L5a, with every `settings/general` reference
      enumerated, the `admin/system` redirect retargeted, admin sub ids and a
      `lastRoutes` check.
    - DD2: the editors keep their own header and the breadcrumb is added inside it, so
      there is one `<h1>` and no duplicate testids.
    - DD8: save-create keeps each editor's render path, and `sync()` announces on an
      item-key change. A dirty clear precedes URL writes, and each type gets a
      per-type preservation check.
    - DD3 guards (d) single-closure races and (e) list-pane lifetime owned by
      `setActiveSection`.
    - DD10 focus preservation across `setItems`.
    - DD11 guard allow-list and explicit shared-lane ownership.
    - L4 and L5 each split, making 8 legs.
    - DD7 acceptance for scroll, toggle and focus.
    - The ratio-based filter gate with throttled Chromium.
    - Connector counts include `channel_map`.
    - Add-menu clipping check.
    - Prerequisites: branch-stack check, `/proc` environ, CDP apparatus default from L3.
    - Citation line fixes.
  - **Substantive changes**, so a second cycle follows (the methodology cap is two).
- 2026-10-01: **Architect cycle 2** returned "approve with changes": 2 high and 4 medium
  issues.
  - **Applied:**
    - L4a now carries every route it links to: connector routes and the hosting of all
      three editors, with interim Back to the section root. L4b is breadcrumbs, Back
      removal and checks.
    - One `sync` announce rule: only `~new` to an item in the same destination and
      section, compared before `lastAnnounceKey` is overwritten. Chats and agents syncs
      are unit-tested silent.
    - DD9 connector counts aligned with DD5, plus an L2 payload check.
    - One focus rule after Cancel, close or delete.
    - DD2 breadcrumb insertion per editor build style, re-added on the knowledge-base
      re-mount; the knowledge-base `~new` form has its own `<h1>`.
    - Reconnaissance table fixed.
    - Suggestions added to L1 and L2.
  - **The two-cycle cap is reached.** Per-leg design reviews (most legs are high risk)
    re-verify against the code.
  - **Flight set `ready`.**
- 2026-10-01: **Leg 1 `list-controls` designed.**
  - **Risk tier: high.** It touches the shared control library, the shell aside CSS, and
    the shared test guard infrastructure.
  - **Developer design review:** "approve with changes", with 2 high and 4 medium issues.
  - **Applied:**
    - The violator count corrected to 29 and computed live. `test_router_*.py` is not
      exempt.
    - The guard also walks helper modules, with an empty allow-list.
    - Focus preservation goes through `entries[]`, with an explicit tab stop after
      `applyView()` and a synchronous restore.
    - The border selection model is opt-in under `rowStyle` only; the default row is
      unchanged.
    - `padding-top: 0` is deferred to the list legs.
    - `test_shell_rail` is split by destination, and the specificity notes are added.
    - A24 is verify-only, plus the new 11px text pairs.
    - The cache-busting count goes from 72 to 73.
  - These are corrections, not a redesign, so there is no second review. Leg set `ready`.
- 2026-10-01: **Environment.**
  - The operator merged PR #217 (a squash, `3121c2d`), which left #218 conflicting.
  - `flight/02-shell-and-router` was rebased onto `main` (identical tree), force-pushed
    with lease, and its PR body fixed through the REST API. `gh pr edit` failed on a
    Projects-classic GraphQL deprecation.
  - #218 is now mergeable.
  - Flight 3 will branch from the rebased `flight/02`.

---

## Decisions

---

## Deviations

---

## Anomalies

---

## Session Notes
