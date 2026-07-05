# Behavior Test: Connector editor keyboard + screen-reader a11y (M12 F4)

**Slug**: `connector-editor-keyboard-a11y`
**Status**: active
**Created**: 2026-06-04
**Last Run**: 2026-06-04-19-52-56 (pass — 8/8 judged; step 9 optional/skipped)

## Intent

Verify the two accessibility behaviors from Mission-12 Flight 4 that **regress silently and don't fit a unit/DOM-shape test**: (A2) a keyboard-only operator can reorder connector routing rules using the focusable drag handle + arrow keys, with focus retained and the new position announced via a live region; and (A1) the connector live-status region is wired so a screen reader is told when state changes (the `aria-live`/`role` plumbing is present on the persistent nodes, and the live region's text actually updates). These are *interaction + assistive-tech-surface* properties — a sighted unit test can assert an attribute exists but cannot confirm that keyboard reorder actually moves a row, keeps focus, and writes a human-meaningful position announcement. An agent drives the real Studio editor with the keyboard only and judges the observable AT surface (focus, live-region text, DOM order). Run after F4 Legs 1–3 land and the-one is restarted (`make restart` — host-native serves the working tree, so a restart picks up the JS/CSS edits).

## Preconditions

- the-one running host-native and reachable on `http://localhost:8485` (the mission dev instance — **not** 8484); `THE_ONE_DEV_MODE=true`; the-one restarted after any JS/CSS changes so the served working tree is current.
- **A connector with ≥3 routing rules exists on 8485.** The original "Discord Constellation" fixture (`58f1fe5a833f`) is **gone** — do not assume any named connector. Seed a fresh connector (`POST /api/connectors`) or use any existing one, and ensure it has **≥3 routing rules** configured under the editor's **Advanced tab → Routing section** (so reorder has room to move a middle rule both up and down and to exercise the first/last boundaries). If fewer than 3 exist, the run adds rules first (unsaved) and discards on exit (step 2 / step 10) so the persisted set is left unchanged; if a connector was seeded fresh for the run, delete it on teardown.
- A browser MCP apparatus is available (chrome-devtools or goldfinch, per the mission's registered apparatus); not mid-edit on the connector; the operator can observe the editor in the browser session. Never touch 8484.

## Observables Required

- browser (DOM state, focused-element identity, live-region `textContent`, `aria-*`/`role` attributes, rule DOM order — measured via the registered browser MCP, chrome-devtools or goldfinch, against 8485; keyboard driven via the MCP key-press / script-eval surface).

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | Navigate to Studio → open the seeded/target connector's editor → **Advanced tab → Routing section** (the section is labelled "Routing" — the old `// ROUTING` marker prose is retired; there is no tab literally named "Access-and-Routing" in this build). Record the current routing-rule order (rule labels top-to-bottom) and rule count. | The routing-rules table renders with ≥3 rows, each with a drag handle (`[data-routing-drag-handle]`). Record the baseline order for later comparison. |
| 2 | (Setup, no judgment) If <3 rules existed, add rules to reach 3 and note that the `finally` must restore the original set. | (empty) |
| 3 | Click into the page, then keyboard-focus the **second** rule's drag handle (Tab to it, or `.focus()` it via the MCP). Inspect the focused element. | The drag handle is in the tab order and receives focus (`document.activeElement` is the row-2 `[data-routing-drag-handle]`). [a11y] The handle has an `aria-label` describing the reorder operation; it does **not** carry a bare `role="button"` promising Enter/Space activation it doesn't implement. |
| 4 | With the row-2 handle focused, press **ArrowDown** once. | The rule that was 2nd is now **3rd** (DOM order changed — `collectRoutingFromContainer`'s order, observable as the table row order). [a11y] **Focus is retained on the moved handle** (`document.activeElement` is still that same rule's handle, NOT `<body>`). [a11y] The persistent live region (`[data-routing-live-region]`, `aria-live="polite"`) `textContent` now reads a human-meaningful position announcement, e.g. "Rule moved to position 3 of N". |
| 5 | Press **ArrowUp** twice (moving the same rule from position 3 → 2 → 1). | The rule moves up two positions to **1st**; focus stays on its handle each time; the live region announces the new position after each press (e.g. "...position 2 of N", then "...position 1 of N"). |
| 6 | With the rule now at the **top**, press **ArrowUp** once more (boundary). | The rule stays 1st (no wrap, no error); focus is retained; the live region announces an "already first" boundary message (NOT a silent no-op, and the handle is NOT `disabled`/removed from focus). |
| 7 | Verify keyboard and mouse paths agree: read the final DOM rule order and confirm it matches what the arrow-key moves should have produced. | The final order reflects exactly the keyboard moves applied (both reorder paths mutate the same DOM order the editor persists — no desync). |
| 8 | Inspect the live-status region plumbing on the General tab (no error needed): the status text span (`connector-live-status`/`connector-live-status-text`) and the error wrap (`connector-live-status-error-wrap`). | [a11y] The status **text span** carries `aria-live="polite"` (and the wrap div that also holds the LED does **not**, so the LED's per-poll `aria-label` churn isn't announced). The error wrap carries `role="alert"`. These are present on the persistent nodes (not created per-poll). |
| 9 | *(Optional — requires a stub.)* With a Playwright/route stub making `GET /api/connectors/{id}/status` return `{state:"error", last_error:"…PrivilegedIntentsRequired…", last_error_link:"…"}`, reload and observe the error wrap. | The error wrap becomes visible with the actionable message + portal link inside it; because it carries `role="alert"`, that content is in an assertive live region (a screen reader would announce it on reveal). Skip if the stub isn't wired — steps 4–8 are the live-drivable core. |
| 10 | (Teardown) Restore the routing rules to the baseline order/set recorded in step 1 (and remove any rules added in step 2). | The connector's routing configuration is left exactly as found. |

**Row conventions:** one row = one checkpoint. `[a11y]`-marked expectations are the assistive-tech surface for the optional Accessibility Validator. **Locators:** drag handle `[data-routing-drag-handle]`; live region `[data-routing-live-region]`; live status `data-testid="connector-live-status"` (+ `-error-wrap`/`-error-link`). Keyboard reorder (steps 3–6) is the live-drivable core; step 9 (error announcement) needs the route-stub as in `connector-editor-ux` step 8 — skip if unavailable.

## Out of Scope

- The visual/interaction acceptance of the editor (live status text, save-warm, Validate button) — see `connector-editor-ux`.
- The attach-toggle accessible name (A3), presence-control labels (A4), section-heading structure (A5), dropdown focus contrast (A6), reduced-motion (A7) — these are DOM-shape/visual and are covered by each leg's browser-test assertions, not this Witnessed flow.
- Real screen-reader audio output — the observable here is the AT-facing DOM (focus, `aria-live` text, `role`), which is what a screen reader consumes.
