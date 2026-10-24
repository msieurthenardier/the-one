# Leg: date-and-time

**Status**: landed
**Flight**: [Settings on the library](../flight.md)

## Objective
Finish moving Settings › Date and time onto the library:
- the mismatch hint becomes a `banner` with its "Use {zone}" button;
- the status, error and load lines become `App.ui.status`;
- the section titles become `App.ui.section`;
- the preview becomes `App.ui.facts`;
- the zone list becomes the inline `searchList` (04d), and the `admin.css` overrides of library classes are deleted;
- module `GEN` becomes `latest()` with the same semantics;
- after "Use {zone}", focus lands on the chosen-zone line (DD8-13);
- B8-B10 are fixed.

## Context
- **Flight decisions:** DD6 (Date and time), DD8-13, DD12 (the inline variant's CSS duplication ends here), DD3 (`latest()`), DD7 (rows 32-34).
- **Today** (`date-time-page.js`, 509 lines, already DOM-built, `fetchJson`):
  - **the page header:** through `App.admin.renderPage` (now `pageHeader` since 08a);
  - **errors:** `p.field-error.date-time-load-error` (`:62`), `p.field-error` "could not be loaded" (`:382`) and `p.field-error.date-time-error[role=alert]` (`:437-442`), which use the owned `field-error` class;
  - **titles and status:** `div.section-title` × 2 (`:462`, `:467`); `p.date-time-status[role=status]` (`:431-436`);
  - **banner and preview:** the hand-built `div.banner.banner-info.date-time-mismatch` (`:424-429`) with an `App.ui.button` "Use {zone}"; the preview `dl.date-time-preview` with `code.date-time-chip`;
  - **the zone list:** an `App.ui.searchList`, with its hand-rolled scroll keep, describedby, chosen-check lead and active-row sync (`:117-120`, `:258-272`, `:371-381`), and 13 `admin.css` overrides (about `:632-715`);
  - **saving:** module `GEN` (`:18`, `:304-345`, `:487`): latest wins, and an unmounted instance only updates `App.time`;
  - **DD8-13:** `patchHint` hides the whole hint, including the focused "Use {zone}" button (`:231-232`).
- **After:**
  - the mismatch hint is `App.ui.banner({tone: 'info', role: 'note', children: [text, useButton]})`;
  - the three error lines are `App.ui.status` (`danger`, `role=alert` for the save error, as today);
  - the status line is `App.ui.status` (polite);
  - the sections are `App.ui.section({title, layout: 'stack'})`;
  - the preview is `App.ui.facts` with `mono` values;
  - the list is `searchList({inline: true, keepScroll, describedBy, scrollActive: 'center'})` with `selected` items, and the hand-rolled code goes;
  - `GEN` → `App.ui.util.latest()`, same semantics;
  - DD8-13: after a successful "Use {zone}", focus moves to the chosen-zone line ("Selected: …", `tabindex=-1`, its testid kept).
- **B8:** the selected zone is centred in the list (the inline variant's programmatic centring); zone ids and offsets use one font in the list and the "Selected:" line (pick the list's mono or the line's body font; say which).
- **B9:** the mismatch hint leads with city names ("Your browser is in Paris; agents use Tokyo."). The raw zone ids stay available in `title`, or in the "Selected:" line.
- **B10:** the status line takes no space while empty (a hidden `App.ui.status`, or the section stack's hidden-child rule).
- **Timing-sensitive tests** (17 in `test_flow_settings_date_time.py`, including `test_a_late_load_never_overrides_a_newer_save`, `test_an_unmounted_instances_late_answer…`, `test_a_fast_double_pick…`): they must pass unchanged in behaviour, and wait on released requests, never fixed timeouts (DD10).

## Inputs
- Legs 03a (`latest`), 04a (`banner`), 04b (`facts`), 04d (the inline `searchList`, the `radioGroup` slot option), 08a (`pageHeader`) landed.

## Outputs
- `date-time-page.js` on the library: no `field-error`, `section-title` or `ui-search-list-listbox` names (its 3 `OWNERSHIP_ALLOWANCE` rows gone); the `radioGroup` slot with `slotIndent`.
- `admin.css`: the `.date-time-page` overrides of library classes deleted (`ui-search-list*`, `ui-radio-slot`, `section-title`); page-only rules kept (`date-time-chosen` etc.). `admin.css` loses its 13+ uses here.
- Tests: DD8-13 test-first; B8 (the centred row; one font), B9 (the city names), B10 (no gap); the existing 17 tests pass, retargeted only for the removed classes.
- Ledger rows 32-34 confirmed by captures; `agents.md` "Date and time page".

## Acceptance Criteria
1. **DD8-13:** after "Use {zone}", focus is on the chosen-zone line. The test fails on today's code.
2. The **GEN semantics hold:** the three timing tests pass, and `latest()` replaces `GEN`, with no module-level counter left.
3. **B8, B9 and B10** are each asserted (the bounding box of the centred active row; the computed font families; the hint text; zero height while there is no status).
4. `date-time-page.js` has no `OWNERSHIP_ALLOWANCE` rows. `admin.css` has no rule naming a library-owned class for this page.
5. The capture compare shows only ledger rows 32-34.
6. The unit tier, the static guards, and the `settings` and `shared` lanes pass (`shared` holds the Jump to tests that reach this page).

## Verification Steps
- The date-time test file alone, twice, under netns; the `settings` and `shared` lanes; `.venv/bin/python -m pytest tests/test_ui_ownership.py tests/test_ui_guards.py -q -x --timeout 120`; the capture compare; `make test-unit` once.

## Edge Cases
- **A zone chosen and then filtered out** of the list by the query: the "Selected:" line still names it (as today).
- **The browser and effective zones becoming equal** after a save made in another tab: the hint hides on the next render. Focus is unaffected, because it wasn't in the hint.

## Files Affected
- `static/js/areas/admin/date-time-page.js`, `static/css/admin.css`.
- `tests/browser/test_flow_settings_date_time.py`.
- `the_one/agents.md`, `docs/ui-control-inventory.md`, the flight log.

## Citation Audit
- From the pages survey (`f4-survey-pages.md` §1.2), not re-read: `date-time-page.js:18`, `:62`, `:117-120`, `:231-232`, `:258-272`, `:371-382`, `:424-442`, `:462-472`; `admin.css` about `:632-715`.

## Design Review Amendments (cycle 1, 2026-10-23)
These override the body where they conflict.
- **`GEN` becomes ONE module-level `latest()`** (`var gen = App.ui.util.latest();` at module scope), not one per render. `GEN` is deliberately shared across mounts: a scratch mount's older answer must be stale against the visible page's newer save, while the latest token still updates `App.time` when its instance is gone. AC2 reads: "no hand-rolled counter; one module-level `latest()` instance". The call sites stay: `next()` in reload, save and the first load, and `isCurrent(token)` in the handlers.
- **B9 changes two pinned assertions, test-first:** `test_zone_mode_hint_names_the_chosen_zone` ("agents are set to Asia/Kolkata", "Asia/Tokyo") and `test_mismatch_hint_and_its_one_step_fix` (`KIRITIMATI`, "the machine running the-one reports").
  - The city names come from the existing `cityOf(zoneId)`, applied after `canon()`, so an alias like `Asia/Calcutta` reads "Kolkata". `App.time.browserZone()` and `s.effective.zone` feed it.
  - Zones with no real city (`Etc/GMT+5`, `UTC`) fall back to the raw id.
  - The raw ids stay in the banner's `title`, and the tests assert on it.
  - Two cities with the same name are not told apart (record this).
- **`syncActive` stays as page code** (the variant does not know the stored zone). The scroll rule:
  - centre only on the first render, or when the stored zone changes from outside the list (another tab or a reload);
  - **after a pick, the list does not scroll**;
  - typing does not call `syncActive` (as today).

  This needs `setActive(id, {scroll: 'center' | 'nearest' | 'none'})` from leg 04d (amended there). Test: pick a row low in the list, and `scrollTop` is unchanged.
- **The selected mark** comes from the variant's `selected: true`. The page's `checkLead` and `date-time-lead-spacer` are deleted. Test 273 (exactly one `svg` in the stored alias row) still holds.
- **DD8-13:** a `focusChosenAfter` flag on the "Use {zone}" save path only. Focus moves after `applySettings` has shown the slot, and only for the current token. If the save fails, the button stays visible and keeps focus; test that too. `p.date-time-chosen` gets `tabindex=-1` and a visible focus ring.
- **B10:** the status stays a persistent `role=status` region (toggling `hidden` on a live region announces unreliably). It sits as the last child of the "Time zone" `section({layout: 'stack'})`, with zero height when empty, and `admin.css`'s `.date-time-status { min-height: 20px }` goes. The hint, radio group, status and error all move inside that section. The empty status costing one stack gap (12px) is accepted, against today's 60px.
- **The preview `facts`** needs node values and per-row testids (leg 04b, amended): the "A new chat starts with" value is two nodes (the prompt text and the muted line). The tool line's bordered `code` chip becomes a `mono` value. The chip's border goes (ledger row 33's note). The `date-time-preview-*` testids and `.date-time-muted` (test 298, retargeted to a testid) survive.
- **B8:** ids and offsets use the list's mono font in both places.
- **`zonesError`** (`:382`) is the fourth `field-error` and converts too.
- **The existing short settle waits** (300-500 ms after a release, for negative assertions) are absence checks: keep them, noting why, or wait on a `data-built` marker the page sets. Recorded per test.
- **The banner's DOM order:** the text, then the Use button (last child).

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
