# Flight Log: Knowledge and connectors on the library

**Flight**: [Knowledge and connectors on the library](flight.md)

## Summary
Planned 2026-10-22 from `main` at `08562ec`. The branch is `flight/03-knowledge-and-connectors-on-the-library`.

---

## Planning Notes

- **The split.** The mission's Flight 3 ("Library and Settings on the library") was two independent clusters of decisions, about 20 legs. On 2026-10-22 the operator chose to split it:
  - this flight is the Library half (knowledge bases and connectors);
  - Settings is Flight 4;
  - the MCP server editor moves to 5, Chats and the close to zero to 6, and Alignment to 7.
- **Operator decisions, 2026-10-22:**
  - the library switch replaces the legacy iOS switch (here, the connector's Enabled row; in Flight 4, the Settings uses);
  - squawk 0100 gets an explicit × clear button;
  - squawk 0192's label is "Knowledge bases" everywhere;
  - a HAT closes the flight (standing choice: a HAT per flight).
- **Planning surveys at `08562ec`** (three read-only surveyors):
  - Settings (carried to Flight 4);
  - Library;
  - cross-cutting: the catalogue, alias counts, the contracts lane, the capture tool, squawks, behavior specs, the testid registry.
- **Flight Director calls, made out loud** (each follows an earlier decision or keeps today's look):
  - patch in place on Save (Flight 2 DD6);
  - a value-model dirty state (Flight 2 debrief recommendation 3, applied to these editors only);
  - the key-value table's core built here, with the masked column in Flight 5;
  - the admission lists and the channel map's agent column keep their inputs;
  - knowledge-base Create stays enabled before typing (`enabledWhenClean`);
  - one header error surface per editor;
  - the danger-zone, status-line and sentence-case canonical forms from Flight 1 DD8.

### Debt at the start (`08562ec`)

| File | Reuse rows / uses | Sinks |
|---|---|---|
| `knowledge-section.js` | 27 / 62 | 0 |
| `connector-editor.js` | 26 / 40 | 3 |
| `knowledge-glue.js` | 0 / 0 | 3 |
| `connector-glue.js` | 0 / 0 | 1 |
| `mcp-glue.js` | 0 / 0 | 1 |
| `css/studio.css` (knowledge, connector, confirm-on-summary rows) | part of 7 / 12 | n/a |
| **Whole app** | 187 / 409 | 46 |

## Reconnaissance Report

Squawks and debrief items sourced into this flight, checked against `08562ec`:

| Item | Classification | Evidence | Recommendation |
|---|---|---|---|
| 0100 KB search has no clear button | confirmed-live | `knowledge-section.js` about `:1378-1382`: only an input and a button | Fold in (DD4, leg 05) |
| 0191 duplicate Library group lists | partially-satisfied / drifted | `hydrateState`'s copy is gone; `library-pane.js:114-117` `isLibrarySection` and `studio-route.js` about `:186` still hand-list beside `LIBRARY_GROUPS:60` | Fold in at the drifted sites (leg 08) |
| 0192 "Knowledge" vs "Knowledge bases" | confirmed-live | `router.js:440` | Fold in, operator label "Knowledge bases" (leg 08) |
| 0093 same-named KBs indistinguishable | confirmed-live | Rows show name plus agent count (`library-pane.js` about `:206-244`); the list API has no folder path | Keep open: needs an API change (DD9) |
| 0233 exact script-count pin | confirmed-live | `test_index_asset_cache_busting.py:99` `== 93` | Fold in, first (leg 01) |
| 0235 editor contracts undocumented | confirmed-live | No tab-handle, `mountSlot` or `state` section in `agents.md` | Fold in, first (leg 01) |
| Flight 2 debrief: `App.ui.disclosure` | confirmed-live | Native `<details>` built in `knowledge-section.js` (folder panels, Other items), `self-config-history.js:80`, `tile.js` toolRow, `mcp-error.js`, `trace-shell.js`, `mcp-server-editor.js` | Build in leg 03 |
| Flight 2 debrief: split `contracts` | confirmed-live | 1010 tests in 27 files | Leg 01 |
| Flight 2 debrief: snapshot model | confirmed-live | Connector sticky `markDirty` (`connector-editor.js:591`); KB JSON-from-DOM snapshot | DD5 for these editors |
| 0222 / 0234 profile the unit tier | duplicates | Both ask for a `--durations` profile | Not in this flight; merge when one is done |
| 0228, 0229, 0230, 0232 | confirmed-live | Agent editor and tests | Not in this flight's path |

## Visible-differences ledger

Every leg appends one row for each visible difference it causes (DD7, DD11). The HAT reads this ledger.

| Leg | Surface | Difference | Allowed by | Notes |
|---|---|---|---|---|

---

## Leg Progress

### Flight Director Notes
- 2026-10-22: the flight was planned. The Architect review follows.
- 2026-10-22: Architect review, cycle 1: **approve with changes**. All of it was incorporated:
  - **High findings:**
    - `save.enabledWhenClean` is a new `editorShell` option, added to DD4 and leg 03b;
    - DD8-6's mechanism is `@layer areas` outranking `@layer components`, not a specificity tie, so the fix narrows the area rules with a `chipList` marker class (DD4 gains the layer rule, and so does DD11).
  - **Medium findings:**
    - the glue mount paths move to legs 05a and 07a;
    - legs 03, 05 and 06 are split into a and b;
    - the merge variations are dropped;
    - the testid shapes for the LED and the pairing code are decided (DD6);
    - the connector token's masked round-trip is pinned in 07a, tiered high;
    - DD3's pins include `test_store_static.py`;
    - `clearable`'s return shape is specified;
    - budgets are measured in a full `--parallel 3` netns and WebKit run, and each leg lists the lanes it runs.
  - **Low findings:** `.admin-loading` dropped from DD10; the `LIBRARY_GROUPS` hoist; the DD8-1 and DD8-4 sequences restated; the hoisting-trap note corrected; the prerequisite branch unchecked; the mission's Flight 1 key-value text corrected; disclosure variants; 0088 on summaries; dynamic class prefixes in the selector report; frozen capture text; a `destroy` frame check.
  - **Flight Director answers to the Architect's questions:**
    - 0192 does not rename the agent editor's Knowledge tab; that becomes a HAT question;
    - the × clear also clears the results;
    - actions stay inside `<summary>`, as an accepted pattern;
    - the LED keeps its testid on a status LED-only variant;
    - the danger-zone labels keep their title case, matching the other editors.
- 2026-10-22: Architect review, cycle 2 (the last allowed): **approve with changes**, no high findings. It confirmed every cycle-1 resolution against the code, and every change was incorporated with no third cycle:
  - **the connector header** keeps its visible status text, as a `status` line with `ledTestid`, so both testids stay and there is no visible change. This is the Flight Director's call, keeping today's look; the cycle-1 "LED-only" text was stale and is gone;
  - **lanes:** `routing` and `shared` are added to legs 05a, 05b, 06a, 07a and 07b, and `agent-tabs`, `settings` and `mcp` to the chip fix;
  - **computed-style checks** run under an area ancestor, so they can fail first;
  - **the poll-driven status lines** take `live:'off'`, `led:false` where there is none today, and are set only on a change;
  - **the host clears** become `replaceChildren()` on an identity change, after `destroy`;
  - **the pairing code:** `copyField` `buttonLabel`, and both test changes named;
  - **the create form** keeps `kb-create-error` as its one error surface;
  - **`clearable` became its own factory,** `App.ui.clearableInput` with `{el, input, clear, setValue, destroy}`, so `textInput`'s return type never depends on an option;
  - **pin retargets** are per leg;
  - **the disclosure** owns `ui-disclosure-*` and never reuses `mcp-tool-*`, and the DD10 `.kv-remove-row-btn` note is corrected;
  - **the automatic doctor probe** handles a non-OK response;
  - **the channel map's dirty state** compares raw rows;
  - **leg 03c** (the chip cascade) is split from 03b;
  - **`library` lane headroom** is reported at each surface leg;
  - **the capture folder** sits beside the data directory, and the CI comment is updated.
- Planning complete. The flight is `ready` for execution. The operator asked to plan and implement through to the HAT, so execution starts with `/mission-control:agentic-workflow`.
- 2026-10-22: **Execution started.**
  - Branch `flight/03-knowledge-and-connectors-on-the-library` was created from `main` at `08562ec`, and the flight set to `in-flight`.
  - The crew file `leg-execution.md` is loaded: Developer Sonnet; Reviewer Sonnet for security-sensitive diffs, otherwise Haiku. This flight's Reviewer is **Sonnet**, because leg 07a carries the connector token's masked round-trip. An Accessibility Reviewer (Sonnet) runs at the flight review, since the flight changes user-facing UI.
- **Leg 01 tiered high.** The lane split changes a shared interface with existing consumers: CI's `--parallel 1` over the canonical lanes, `tests/test_run_tests_lanes.py`, CLAUDE.md, and the `THE_ONE_REQUIRE_WEBKIT=1` convention. Design review: one Sonnet Developer.
